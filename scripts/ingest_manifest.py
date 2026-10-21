"""Catalog ingestion:  python scripts/ingest_manifest.py data/catalog_manifest.json

Only entries with explicit, evidenced permissions are ingested. Audio goes to private object storage;
the worker then computes peaks and indexes overlapping sections.
Run from the repo root with the .env values exported (see README), using localhost endpoints.
"""
import json, os, subprocess, sys, uuid, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "common"))
import boto3
from botocore.config import Config
from celery import Celery
from resonant_common.config import settings
from resonant_common.db import owner_connection
from resonant_common.manifest import validate_entry

MIN_FULL_LENGTH_S = 90


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    return float(out)


def main(manifest_path):
    entries = json.loads(Path(manifest_path).read_text())
    s3 = boto3.client("s3", endpoint_url=settings.s3_endpoint, aws_access_key_id=settings.s3_access_key,
                      aws_secret_access_key=settings.s3_secret_key, region_name=settings.s3_region,
                      config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, connect_timeout=5))
    celery = Celery("resonant", broker=settings.redis_url)
    conn = owner_connection()
    ok = skipped = 0
    for e in entries:
        errs = validate_entry(e)
        path = Path(e.get("file", ""))
        if not errs and not path.exists():
            errs.append(f"file not found: {path}")
        if not errs:
            d = duration(str(path))
            if d < MIN_FULL_LENGTH_S:
                errs.append(f"only {d:.0f}s long; use a verified full-length recording (>= {MIN_FULL_LENGTH_S}s)")
        if errs:
            print(f"SKIP {e.get('source_id', '?')}: " + "; ".join(errs)); skipped += 1; continue
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        group = e.get("recording_group") or e["source_id"]
        gid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"resonant:group:{group}"))
        p = e["permissions"]
        row = conn.execute("""INSERT INTO tracks (source, source_id, recording_group_id, title, artist, album, duration_s, artwork_url,
                              source_url, license, license_url, attribution)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                              ON CONFLICT (source, source_id) DO UPDATE SET title = EXCLUDED.title RETURNING id""",
                           (e["source"], e["source_id"], gid, e["title"], e["artist"], e.get("album"), d, e.get("artwork_url"),
                            e["source_url"], e["license"], e.get("license_url"), e["attribution"])).fetchone()
        if conn.execute("SELECT 1 FROM audio_assets WHERE track_id = %s", (row["id"],)).fetchone():
            print(f"EXISTS {e['source_id']}"); conn.commit(); continue
        aid, key = str(uuid.uuid4()), f"catalog/{e['source']}/{e['source_id']}{path.suffix.lower()}"
        s3.upload_file(str(path), settings.s3_bucket, key)
        conn.execute("""INSERT INTO audio_assets (id, track_id, visibility, storage_key, sha256, bytes, duration_s,
                        analysis_allowed, playback_allowed, storage_allowed, original_filename)
                        VALUES (%s,%s,'catalog',%s,%s,%s,%s,%s,%s,%s,%s)""",
                     (aid, row["id"], key, sha, path.stat().st_size, d, p["analysis"], p["playback"], p["storage"], path.name))
        job = str(uuid.uuid4())
        conn.execute("INSERT INTO analysis_jobs (id, kind, asset_id) VALUES (%s,'index_asset',%s)", (job, aid))
        conn.commit()
        celery.send_task("resonant.prepare_asset", args=[job], task_id=job)
        print(f"QUEUED {e['source_id']} ({d:.0f}s)"); ok += 1
    print(f"done: {ok} queued, {skipped} skipped")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/catalog_manifest.json")
