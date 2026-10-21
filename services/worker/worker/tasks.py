import json
import logging
import os
import tempfile
from datetime import datetime, timezone

import boto3
import numpy as np
from botocore.config import Config
from resonant_common.config import settings
from resonant_common.db import owner_connection
from resonant_common.timeutil import make_windows

from . import features
from .celery_app import app
from .embed import get_embedder

log = logging.getLogger("resonant.worker")
_s3 = boto3.client("s3", endpoint_url=settings.s3_endpoint, aws_access_key_id=settings.s3_access_key,
                   aws_secret_access_key=settings.s3_secret_key, region_name=settings.s3_region,
                   config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                                 connect_timeout=5, read_timeout=30, retries={"max_attempts": 3}))


class Cancelled(Exception):
    pass


def _now():
    return datetime.now(timezone.utc)


def _set(conn, job_id, **cols):
    sets = ", ".join(f"{k} = %s" for k in cols)
    conn.execute(f"UPDATE analysis_jobs SET {sets} WHERE id = %s", (*cols.values(), job_id))
    conn.commit()


def _check_cancelled(conn, job_id):
    r = conn.execute("SELECT status FROM analysis_jobs WHERE id = %s", (job_id,)).fetchone()
    if not r or r["status"] == "cancelled":
        raise Cancelled()


def _load_audio(asset) -> np.ndarray:
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(asset["storage_key"])[1]) as tmp:
        _s3.download_file(settings.s3_bucket, asset["storage_key"], tmp.name)
        return features.decode(tmp.name)


def _window_features(y48: np.ndarray, start: float, end: float) -> dict:
    seg = y48[int(start * features.EMBED_SR):int(end * features.EMBED_SR)]
    f = features.segment_features(seg)
    f["embedding"] = get_embedder().embed(seg).tolist()
    f.update(start_s=start, end_s=end)
    return f


@app.task(name="resonant.prepare_asset", bind=True, max_retries=1, autoretry_for=(ConnectionError,), retry_backoff=5)
def prepare_asset(self, job_id: str):
    """Waveform peaks for every asset; indexed segments for permission-cleared catalog assets only."""
    conn = owner_connection()
    try:
        job = conn.execute("SELECT * FROM analysis_jobs WHERE id = %s", (job_id,)).fetchone()
        if not job or job["status"] == "cancelled":
            return
        asset = conn.execute("SELECT * FROM audio_assets WHERE id = %s", (job["asset_id"],)).fetchone()
        _set(conn, job_id, status="processing", started_at=_now())
        conn.execute("UPDATE audio_assets SET status = 'processing' WHERE id = %s", (asset["id"],))
        conn.commit()
        y = _load_audio(asset)
        conn.execute("UPDATE audio_assets SET peaks = %s::jsonb WHERE id = %s", (json.dumps(features.peaks(y)), asset["id"]))
        conn.commit()
        if asset["visibility"] == "catalog" and asset["analysis_allowed"]:
            conn.execute("""INSERT INTO feature_versions (preprocess_version, model_name, model_revision, embed_dim, config)
                            VALUES (%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING""",
                         (settings.preprocess_version, settings.clap_model, settings.clap_revision, settings.embed_dim,
                          json.dumps({"windows": settings.windows})))
            dur = len(y) / features.EMBED_SR
            for length, hop in settings.windows:
                for start, end in make_windows(dur, length, hop):
                    _check_cancelled(conn, job_id)
                    f = _window_features(y, start, end)
                    conn.execute("""INSERT INTO segments (asset_id, track_id, scale_s, start_s, end_s, embedding, chroma_mean, chroma_seq,
                                    chroma_conf, tempo, tempo_conf, onset_density, timbre, preprocess_version, model_version)
                                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT DO NOTHING""",
                                 (asset["id"], asset["track_id"], int(length), start, end, np.array(f["embedding"], dtype=np.float32),
                                  np.array(f["chroma_mean"], dtype=np.float32), json.dumps(f["chroma_seq"]),
                                  f["chroma_conf"], f["tempo"], f["tempo_conf"], f["onset_density"], json.dumps(f["timbre"]),
                                  settings.preprocess_version, settings.model_version))
            conn.commit()
        conn.execute("UPDATE audio_assets SET status = 'ready' WHERE id = %s", (asset["id"],))
        conn.commit()
        _set(conn, job_id, status="ready", finished_at=_now())
    except Cancelled:
        conn.rollback()
    except Exception as e:  # report a useful, non-sensitive message; details go to logs
        conn.rollback()
        log.exception("prepare_asset failed")
        conn.execute("UPDATE audio_assets SET status='failed', error=%s WHERE id=(SELECT asset_id FROM analysis_jobs WHERE id=%s)",
                     ("Processing failed. The file may be unsupported or corrupt.", job_id))
        conn.commit()
        _set(conn, job_id, status="failed", error="Processing failed. The file may be unsupported or corrupt.")
    finally:
        conn.close()


@app.task(name="resonant.analyze_query", bind=True, max_retries=1, autoretry_for=(ConnectionError,), retry_backoff=5)
def analyze_query(self, job_id: str):
    """Analyze exactly the user's selection (or the whole song as 12 s windows). Cached by content hash + range + versions."""
    conn = owner_connection()
    try:
        job = conn.execute("SELECT * FROM analysis_jobs WHERE id = %s", (job_id,)).fetchone()
        if not job or job["status"] == "cancelled":
            return
        if conn.execute("SELECT 1 FROM query_features WHERE cache_key = %s", (job["cache_key"],)).fetchone():
            _set(conn, job_id, status="ready", finished_at=_now())
            return
        _set(conn, job_id, status="processing", started_at=_now())
        asset = conn.execute("SELECT * FROM audio_assets WHERE id = %s", (job["asset_id"],)).fetchone()
        y = _load_audio(asset)
        _check_cancelled(conn, job_id)
        if job["start_s"] is None:   # whole song => overlapping windows at the shortest configured scale
            length, hop = min(settings.windows)
            spans = make_windows(len(y) / features.EMBED_SR, length, hop)
        else:
            spans = [(job["start_s"], job["end_s"])]
        wins = []
        for s, e in spans:
            _check_cancelled(conn, job_id)
            wins.append(_window_features(y, s, e))
        conn.execute("""INSERT INTO query_features (cache_key, asset_id, owner_session, start_s, end_s, windows, preprocess_version, model_version)
                        VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT DO NOTHING""",
                     (job["cache_key"], asset["id"], job["owner_session"], spans[0][0], spans[-1][1], json.dumps(wins),
                      settings.preprocess_version, settings.model_version))
        conn.commit()
        _set(conn, job_id, status="ready", finished_at=_now())
    except Cancelled:
        conn.rollback()
    except Exception:
        conn.rollback()
        log.exception("analyze_query failed")
        _set(conn, job_id, status="failed", error="Analysis failed. Try a different selection or upload again.")
    finally:
        conn.close()


@app.task(name="resonant.purge_expired")
def purge_expired():
    """Retention: delete expired private uploads and all derived private features (cascade)."""
    conn = owner_connection()
    try:
        rows = conn.execute("SELECT a.storage_key, t.id FROM audio_assets a JOIN tracks t ON t.id = a.track_id "
                            "WHERE a.visibility = 'private' AND a.expires_at < now()").fetchall()
        for r in rows:
            try:
                _s3.delete_object(Bucket=settings.s3_bucket, Key=r["storage_key"])
            except Exception:
                log.exception("failed to delete object; will retry next run")
                continue
            conn.execute("DELETE FROM tracks WHERE id = %s", (r["id"],))
        conn.commit()
        # Searches whose private query asset is gone (query_asset_id set NULL on cascade) are private history.
        conn.execute("DELETE FROM searches WHERE query_asset_id IS NULL AND created_at < now() - make_interval(hours => %s)",
                     (settings.retention_hours,))
        conn.commit()
        return len(rows)
    finally:
        conn.close()
