import hashlib
import json
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

import httpx
from celery import Celery
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from resonant_common import permissions, retrieval
from resonant_common.config import settings
from resonant_common.db import session_cursor
from resonant_common.timeutil import cache_key, validate_range, make_windows

from . import media, storage
from .security import rate_limit, redis_client, session_id

logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","lvl":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("resonant.api")
celery = Celery("resonant", broker=settings.redis_url, backend=None)
celery.conf.broker_transport_options = {"socket_timeout": 5, "socket_connect_timeout": 5}

app = FastAPI(title="Resonant API", version="0.1.0", description="Audio-similarity search. Scores are experimental and uncalibrated.")
app.add_middleware(CORSMiddleware, allow_origins=[settings.cors_origin], allow_credentials=True,
                   allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])
general = rate_limit("general", settings.rate_per_min, 60)
upload_limit = rate_limit("upload", settings.upload_per_hour, 3600, fail_closed=True)
analysis_limit = rate_limit("analysis", settings.analysis_per_hour, 3600, fail_closed=True)


# ------------------------------ schemas ------------------------------
class Availability(BaseModel):
    audio_analysis: bool
    playback: bool
    message: Optional[str] = None


class TrackOut(BaseModel):
    id: str
    title: str
    artist: str
    album: Optional[str] = None
    duration_s: Optional[float] = None
    artwork_url: Optional[str] = None
    source: str
    source_url: Optional[str] = None
    license: Optional[str] = None
    attribution: Optional[str] = None
    is_private_upload: bool = False
    availability: Availability


class JobOut(BaseModel):
    id: str
    status: Literal["queued", "processing", "ready", "failed", "cancelled"]
    error: Optional[str] = None
    retryable: bool = False
    start_s: Optional[float] = None
    end_s: Optional[float] = None
    whole_song: bool = False


class JobIn(BaseModel):
    track_id: str
    start_s: Optional[float] = None
    end_s: Optional[float] = None
    whole_song: bool = False


class SearchIn(BaseModel):
    job_id: str
    mode: Literal["balanced", "vibe", "harmony"] = "balanced"
    k: int = Field(10, ge=1, le=25)


class Match(BaseModel):
    result_id: int
    track: TrackOut
    start_s: float
    end_s: float
    score: float
    confidence: Literal["ok", "low"]
    coverage: Optional[float] = None
    components: dict
    explanations: list[str]


class SearchOut(BaseModel):
    search_id: str
    mode: str
    weights: dict
    weights_note: str = "Experimental weights. Scores rank candidates; they are not calibrated percentages."
    analysis_versions: dict
    quality: Literal["ok", "weak", "empty"]
    latency_ms: int
    results: list[Match]


class CompareIn(BaseModel):
    job_a: str
    job_b: str
    mode: Literal["balanced", "vibe", "harmony"] = "balanced"


class FeedbackIn(BaseModel):
    result_id: int
    label: Literal["good", "poor"]


class SaveIn(BaseModel):
    track_id: str
    start_s: Optional[float] = None
    end_s: Optional[float] = None


# ------------------------------ helpers ------------------------------
def _track_out(r: dict) -> TrackOut:
    av = permissions.availability(r.get("asset_id") is not None, bool(r.get("analysis_allowed")), bool(r.get("playback_allowed")))
    return TrackOut(id=str(r["id"]), title=r["title"], artist=r["artist"], album=r.get("album"),
                    duration_s=r.get("duration_s"), artwork_url=r.get("artwork_url"), source=r["source"],
                    source_url=r.get("source_url"), license=r.get("license"), attribution=r.get("attribution"),
                    is_private_upload=r["source"] == "upload", availability=Availability(**av))


_TRACK_SQL = """SELECT t.*, a.id AS asset_id, a.analysis_allowed, a.playback_allowed, a.status AS asset_status
                FROM tracks t LEFT JOIN audio_assets a ON a.track_id = t.id"""


def _job_out(r: dict) -> JobOut:
    return JobOut(id=str(r["id"]), status=r["status"], error=r.get("error"), retryable=r["status"] in ("failed", "cancelled"),
                  start_s=r.get("start_s"), end_s=r.get("end_s"), whole_song=r.get("start_s") is None)


def _get_uuid(v: str) -> str:
    try:
        return str(uuid.UUID(v))
    except ValueError:
        raise HTTPException(404, "Not found")


# ------------------------------ catalog ------------------------------
@app.get("/api/health")
def health():
    return {"ok": True}


async def _musicbrainz(q: str) -> list[dict]:
    """Metadata only. Cached 24h; global 1 req/s limit; identified User-Agent. Never implies audio is analyzable."""
    if not (settings.enable_musicbrainz and settings.musicbrainz_ua):
        return []
    r = redis_client()
    ckey = f"mb:{q.lower()}"
    try:
        if (hit := r.get(ckey)):
            return json.loads(hit)
        if not r.set("mb:lock", "1", nx=True, px=1100):
            return []
    except Exception:
        return []
    try:
        async with httpx.AsyncClient(timeout=5, headers={"User-Agent": settings.musicbrainz_ua}) as c:
            resp = await c.get("https://musicbrainz.org/ws/2/recording", params={"query": q, "fmt": "json", "limit": 8})
            resp.raise_for_status()
        out = [{"id": f"mb:{x['id']}", "title": x["title"],
                "artist": ", ".join(a["name"] for a in x.get("artist-credit", []) if "name" in a) or "Unknown artist",
                "album": (x.get("releases") or [{}])[0].get("title"),
                "duration_s": (x["length"] / 1000) if x.get("length") else None,
                "source": "musicbrainz", "source_url": f"https://musicbrainz.org/recording/{x['id']}"}
               for x in resp.json().get("recordings", [])]
        r.setex(ckey, 86400, json.dumps(out))
        return out
    except Exception as e:  # network/provider failure must not break local search
        log.warning("musicbrainz lookup failed: %s", type(e).__name__)
        return []


@app.get("/api/catalog/search", response_model=list[TrackOut], dependencies=[general])
async def catalog_search(q: str = "", sid: str = Depends(session_id)):
    q = q.strip()[:100]
    like = f"%{q}%"
    with session_cursor(sid) as cur:
        cur.execute(_TRACK_SQL + """ AND a.visibility = 'catalog' WHERE t.owner_session IS NULL
                     AND (%s = '' OR t.title ILIKE %s OR t.artist ILIKE %s) ORDER BY t.title LIMIT 25""", (q, like, like))
        out = [_track_out(r) for r in cur.fetchall()]
    if q and len(out) < 5:
        have = {(t.title.lower(), t.artist.lower()) for t in out}
        for m in await _musicbrainz(q):
            if (m["title"].lower(), m["artist"].lower()) not in have:
                out.append(_track_out({**m, "asset_id": None}))
    return out


@app.get("/api/tracks/{track_id}", response_model=TrackOut, dependencies=[general])
def get_track(track_id: str, sid: str = Depends(session_id)):
    with session_cursor(sid) as cur:
        cur.execute(_TRACK_SQL + " AND a.visibility IN ('catalog','private') WHERE t.id = %s", (_get_uuid(track_id),))
        r = cur.fetchone()
    if not r:
        raise HTTPException(404, "Track not found")
    return _track_out(r)


def _playable_asset(cur, track_id: str):
    cur.execute("SELECT * FROM audio_assets WHERE track_id = %s", (track_id,))
    a = cur.fetchone()
    if not a or not a["playback_allowed"]:
        raise HTTPException(403, "Playback isn’t permitted for this recording.")
    return a


@app.get("/api/tracks/{track_id}/audio", dependencies=[general])
def track_audio(track_id: str, sid: str = Depends(session_id)):
    with session_cursor(sid) as cur:
        a = _playable_asset(cur, _get_uuid(track_id))
    return {"url": storage.signed_url(a["storage_key"]), "expires_in": settings.signed_url_ttl_s}


@app.get("/api/tracks/{track_id}/waveform", dependencies=[general])
def track_waveform(track_id: str, sid: str = Depends(session_id)):
    with session_cursor(sid) as cur:
        a = _playable_asset(cur, _get_uuid(track_id))
    if a["status"] == "failed":
        raise HTTPException(422, a["error"] or "This file couldn’t be processed.")
    if not a["peaks"]:
        raise HTTPException(409, "Waveform is still being prepared.")
    return {"peaks": a["peaks"], "duration_s": a["duration_s"], "status": a["status"]}


# ------------------------------ uploads ------------------------------
@app.post("/api/uploads", response_model=dict, dependencies=[general, upload_limit])
def create_upload(file: UploadFile = File(...), authorized: bool = Form(False), sid: str = Depends(session_id)):
    if not authorized:
        raise HTTPException(400, "Confirm that you’re authorized to use this audio.")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in media.ALLOWED_EXT:
        raise HTTPException(415, "Unsupported file type. Use MP3, WAV, FLAC or M4A.")
    sha, size = hashlib.sha256(), 0
    with tempfile.NamedTemporaryFile(suffix=ext) as tmp:
        while chunk := file.file.read(1024 * 1024):  # byte limit enforced while streaming
            size += len(chunk)
            if size > settings.max_upload_bytes:
                raise HTTPException(413, f"File is larger than {settings.max_upload_bytes // (1024 * 1024)} MB.")
            sha.update(chunk)
            tmp.write(chunk)
        tmp.flush()
        try:
            info = media.probe(tmp.name, ext, settings.max_duration_s)  # decoded-duration limit enforced here
        except media.MediaError as e:
            raise HTTPException(422, str(e))
        asset_id, track_id = str(uuid.uuid4()), str(uuid.uuid4())
        key = f"uploads/{sid[:8]}/{asset_id}{ext}"
        storage.put_file(tmp.name, key, media.CONTENT_TYPES[ext])
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.retention_hours)
    title = Path(file.filename or "Upload").stem[:120] or "Upload"
    with session_cursor(sid) as cur:
        cur.execute("""INSERT INTO tracks (id, source, source_id, title, artist, duration_s, owner_session, expires_at, license, attribution)
                       VALUES (%s,'upload',%s,%s,'Your upload',%s,%s,%s,'private upload','Uploaded by you')""",
                    (track_id, asset_id, title, info["duration_s"], sid, expires))
        cur.execute("""INSERT INTO audio_assets (id, track_id, visibility, owner_session, storage_key, sha256, bytes, duration_s, codec,
                       analysis_allowed, playback_allowed, storage_allowed, original_filename, expires_at)
                       VALUES (%s,%s,'private',%s,%s,%s,%s,%s,%s,true,true,true,%s,%s)""",
                    (asset_id, track_id, sid, key, sha.hexdigest(), size, info["duration_s"], info["codec"], title, expires))
        job_id = str(uuid.uuid4())
        cur.execute("INSERT INTO analysis_jobs (id, kind, asset_id, owner_session) VALUES (%s,'index_asset',%s,%s)", (job_id, asset_id, sid))
    celery.send_task("resonant.prepare_asset", args=[job_id], task_id=job_id)
    return {"track_id": track_id, "job_id": job_id, "expires_at": expires.isoformat(),
            "retention_hours": settings.retention_hours}


@app.delete("/api/uploads/{track_id}", status_code=204, dependencies=[general])
def delete_upload(track_id: str, sid: str = Depends(session_id)):
    tid = _get_uuid(track_id)
    with session_cursor(sid) as cur:
        cur.execute("SELECT a.storage_key FROM audio_assets a JOIN tracks t ON t.id = a.track_id "
                    "WHERE t.id = %s AND t.source = 'upload'", (tid,))
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(404, "Upload not found")
        cur.execute("DELETE FROM tracks WHERE id = %s", (tid,))  # cascades to assets, segments, features, jobs
    for r in rows:
        storage.delete(r["storage_key"])


# ------------------------------ analysis jobs ------------------------------
@app.post("/api/analysis/jobs", response_model=JobOut, dependencies=[general, analysis_limit])
def create_job(body: JobIn, sid: str = Depends(session_id)):
    tid = _get_uuid(body.track_id)
    with session_cursor(sid) as cur:
        cur.execute("SELECT * FROM audio_assets WHERE track_id = %s", (tid,))
        a = cur.fetchone()
        if not a or not a["analysis_allowed"]:
            raise HTTPException(403, "Audio analysis isn’t available for this recording. Upload an audio file you’re authorized to use.")
        if a["status"] != "ready":
            raise HTTPException(409, "This audio is still being prepared. Try again in a moment.")
        if body.whole_song:
            start = end = None
            ckey = cache_key(a["sha256"], 0, a["duration_s"], settings.preprocess_version, settings.model_version) + ":whole"
        else:
            if body.start_s is None or body.end_s is None:
                raise HTTPException(422, "Provide start_s and end_s, or set whole_song.")
            try:
                start, end = validate_range(body.start_s, body.end_s, a["duration_s"], settings.query_min_s, settings.query_max_s)
            except ValueError as e:
                raise HTTPException(422, str(e))
            ckey = cache_key(a["sha256"], start, end, settings.preprocess_version, settings.model_version)
        cur.execute("SELECT 1 FROM query_features WHERE cache_key = %s", (ckey,))
        cached = cur.fetchone() is not None
        job_id = str(uuid.uuid4())
        cur.execute("""INSERT INTO analysis_jobs (id, kind, asset_id, owner_session, start_s, end_s, cache_key, status, finished_at)
                       VALUES (%s,'query',%s,%s,%s,%s,%s,%s, CASE WHEN %s THEN now() END) RETURNING *""",
                    (job_id, a["id"], sid, start, end, ckey, "ready" if cached else "queued", cached))
        row = cur.fetchone()
    if not cached:
        celery.send_task("resonant.analyze_query", args=[job_id], task_id=job_id)
    return _job_out(row)


@app.get("/api/analysis/jobs/{job_id}", response_model=JobOut, dependencies=[general])
def get_job(job_id: str, sid: str = Depends(session_id)):
    with session_cursor(sid) as cur:
        cur.execute("SELECT * FROM analysis_jobs WHERE id = %s", (_get_uuid(job_id),))
        r = cur.fetchone()
    if not r:
        raise HTTPException(404, "Job not found")
    return _job_out(r)


@app.post("/api/analysis/jobs/{job_id}/cancel", response_model=JobOut, dependencies=[general])
def cancel_job(job_id: str, sid: str = Depends(session_id)):
    with session_cursor(sid) as cur:
        cur.execute("UPDATE analysis_jobs SET status='cancelled', finished_at=now() WHERE id=%s "
                    "AND status IN ('queued','processing') RETURNING *", (_get_uuid(job_id),))
        r = cur.fetchone()
        if not r:
            cur.execute("SELECT * FROM analysis_jobs WHERE id = %s", (_get_uuid(job_id),))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "Job not found")
    celery.control.revoke(job_id)  # worker also re-checks status between stages
    return _job_out(r)


# ------------------------------ similarity ------------------------------
def _load_query(cur, job_id: str):
    cur.execute("""SELECT j.*, a.track_id, q.windows, q.preprocess_version, q.model_version
                   FROM analysis_jobs j JOIN audio_assets a ON a.id = j.asset_id
                   LEFT JOIN query_features q ON q.cache_key = j.cache_key WHERE j.id = %s""", (_get_uuid(job_id),))
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, "Job not found")
    if r["status"] != "ready" or not r["windows"]:
        raise HTTPException(409, "Analysis isn’t ready yet.")
    return r


@app.post("/api/searches", response_model=SearchOut, dependencies=[general])
def search(body: SearchIn, sid: str = Depends(session_id)):
    t0 = time.perf_counter()
    with session_cursor(sid) as cur:
        job = _load_query(cur, body.job_id)
        cur.execute("SELECT COALESCE(recording_group_id, id) AS g FROM tracks WHERE id = %s", (job["track_id"],))
        group = cur.fetchone()["g"]
        windows = job["windows"]
        whole = job["start_s"] is None
        found = (retrieval.search_whole(cur, windows, body.mode, group, body.k) if whole
                 else retrieval.search_section(cur, windows[0], body.mode, group, body.k))
        versions = {"preprocess": job["preprocess_version"], "model": job["model_version"],
                    "windows": [list(w) for w in settings.windows]}
        weights = settings.weights[body.mode]
        ms = int((time.perf_counter() - t0) * 1000)
        cur.execute("""INSERT INTO searches (owner_session, query_asset_id, start_s, end_s, whole_song, mode, weights, analysis_versions, latency_ms)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (sid, job["asset_id"], job["start_s"], job["end_s"], whole, body.mode, json.dumps(weights), json.dumps(versions), ms))
        search_id = str(cur.fetchone()["id"])
        results = []
        for rank, m in enumerate(found, 1):
            cur.execute("""INSERT INTO results (search_id, owner_session, track_id, start_s, end_s, rank, score, components, confidence, explanations)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (search_id, sid, m["track_id"], m["start_s"], m["end_s"], rank, m["score"],
                         json.dumps(m["components"]), m["confidence"], json.dumps(m["explanations"])))
            rid = cur.fetchone()["id"]
            cur.execute(_TRACK_SQL + " AND a.visibility = 'catalog' WHERE t.id = %s", (m["track_id"],))
            results.append(Match(result_id=rid, track=_track_out(cur.fetchone()), start_s=m["start_s"], end_s=m["end_s"],
                                 score=round(m["score"], 4), confidence=m["confidence"], coverage=m.get("coverage"),
                                 components=m["components"], explanations=m["explanations"]))
    quality = "empty" if not results else ("ok" if any(r.confidence == "ok" for r in results) else "weak")
    return SearchOut(search_id=search_id, mode=body.mode, weights=weights, analysis_versions=versions,
                     quality=quality, latency_ms=ms, results=results)


@app.post("/api/compare", dependencies=[general])
def compare(body: CompareIn, sid: str = Depends(session_id)):
    """Private pair comparison using the same features and scoring as catalog search."""
    with session_cursor(sid) as cur:
        a, b = _load_query(cur, body.job_a), _load_query(cur, body.job_b)
    res = retrieval.compare_windows(a["windows"][0], b["windows"][0], body.mode)
    return {"mode": body.mode, "score": round(res["score"], 4), "confidence": res["confidence"],
            "components": res["components"], "harmonic_shift_semitones": res["harmonic_shift"],
            "weights": settings.weights[body.mode], "note": "Experimental score; compares the first analyzed window of each selection."}


# ------------------------------ feedback / saved ------------------------------
@app.post("/api/feedback", status_code=204, dependencies=[general])
def feedback(body: FeedbackIn, sid: str = Depends(session_id)):
    with session_cursor(sid) as cur:
        cur.execute("SELECT 1 FROM results WHERE id = %s", (body.result_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Result not found")
        cur.execute("""INSERT INTO feedback (result_id, owner_session, label) VALUES (%s,%s,%s)
                       ON CONFLICT (result_id, owner_session) DO UPDATE SET label = EXCLUDED.label""", (body.result_id, sid, body.label))


@app.post("/api/saved", status_code=201, dependencies=[general])
def save_item(body: SaveIn, sid: str = Depends(session_id)):
    with session_cursor(sid) as cur:
        cur.execute("INSERT INTO saved_items (owner_session, track_id, start_s, end_s) VALUES (%s,%s,%s,%s) RETURNING id",
                    (sid, _get_uuid(body.track_id), body.start_s, body.end_s))
        return {"id": cur.fetchone()["id"]}
