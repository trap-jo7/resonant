"""Candidate retrieval (pgvector) + reranking. Works with any psycopg cursor (RLS or owner)."""
from __future__ import annotations
import numpy as np
from . import scoring as sc
from .config import settings

_COLS = """s.id, s.track_id, COALESCE(t.recording_group_id, t.id) AS group_id, s.start_s, s.end_s,
  s.embedding, s.chroma_mean, s.chroma_seq, s.chroma_conf, s.tempo, s.tempo_conf, s.onset_density, s.timbre"""
_FROM = """FROM segments s JOIN tracks t ON t.id = s.track_id JOIN audio_assets a ON a.id = s.asset_id
  WHERE a.visibility = 'catalog' AND a.analysis_allowed AND s.scale_s = %s
    AND s.model_version = %s AND s.preprocess_version = %s
    AND COALESCE(t.recording_group_id, t.id) <> %s"""


def pick_scale(length_s: float) -> int:
    """Catalog scale (window length) closest to the query length."""
    return int(min((w[0] for w in settings.windows), key=lambda L: abs(L - length_s)))


def candidates(cur, q: dict, scale: int, mode: str, exclude_group, per_path: int = 40) -> dict[int, dict]:
    base = (scale, settings.model_version, settings.preprocess_version, str(exclude_group))
    found: dict[int, dict] = {}
    cur.execute(f"SELECT {_COLS} {_FROM} ORDER BY s.embedding <=> %s LIMIT %s",
                (*base, np.asarray(q["embedding"], dtype=np.float32), per_path))
    for r in cur.fetchall():
        found[r["id"]] = r
    if mode in ("balanced", "harmony"):  # harmonic path: 12 transpositions of the mean chroma
        qm = np.asarray(q["chroma_mean"], dtype=np.float32)
        for shift in range(12):
            cur.execute(f"SELECT {_COLS} {_FROM} ORDER BY s.chroma_mean <=> %s LIMIT %s",
                        (*base, np.roll(qm, shift), max(5, per_path // 8)))
            for r in cur.fetchall():
                found.setdefault(r["id"], r)
    return found  # union, de-duplicated by segment id


def score_pair(q: dict, s: dict, weights: dict, detailed: bool = True) -> dict:
    if detailed:
        har, shift = sc.harmonic_similarity(q["chroma_seq"], s["chroma_seq"])
    else:
        har, shift = sc.harmonic_fast(q["chroma_mean"], s["chroma_mean"])
    hconf = min(q.get("chroma_conf") or 0.0, s.get("chroma_conf") or 0.0)
    rhy, rconf = sc.rhythm_similarity(q.get("tempo"), q.get("tempo_conf"), s.get("tempo"), s.get("tempo_conf"),
                                      q.get("onset_density") or 0, s.get("onset_density") or 0)
    comps = {
        "embedding": (sc.cosine01(q["embedding"], s["embedding"]), 1.0),
        "harmonic": (har, hconf),
        "rhythm": (rhy, rconf),
        "timbre": (sc.timbre_similarity(q["timbre"], s["timbre"]), 1.0),
    }
    out = sc.combine(comps, weights)
    out.update(components={k: {"score": round(v[0], 4), "confidence": round(v[1], 3)} for k, v in comps.items()},
               harmonic_shift=shift, _raw=comps)
    return out


def _row(s: dict, scored: dict) -> dict:
    return {"track_id": str(s["track_id"]), "group_id": str(s["group_id"]), "start_s": float(s["start_s"]),
            "end_s": float(s["end_s"]), "score": scored["score"], "confidence": scored["confidence"],
            "evidence": scored["evidence"], "components": scored["components"],
            "explanations": sc.explanations(scored["_raw"], scored["harmonic_shift"])}


def search_section(cur, q: dict, mode: str, exclude_group, k: int = 10) -> list[dict]:
    weights = settings.weights[mode]
    scale = pick_scale(q["end_s"] - q["start_s"])
    cands = candidates(cur, q, scale, mode, exclude_group)
    scored = [_row(s, score_pair(q, s, weights, detailed=True)) for s in cands.values()]
    return sc.collapse_by_recording(scored)[:k]


def search_whole(cur, windows: list[dict], mode: str, exclude_group, k: int = 10, max_windows: int = 40) -> list[dict]:
    weights = settings.weights[mode]
    scale = int(min(w[0] for w in settings.windows))
    step = max(1, len(windows) // max_windows)
    wins = windows[::step]
    per_group: dict[str, dict] = {}
    for wi, q in enumerate(wins):
        cands = candidates(cur, q, scale, mode, exclude_group, per_path=25)
        best_here: dict[str, dict] = {}
        for s in cands.values():
            row = _row(s, score_pair(q, s, weights, detailed=False))
            g = row["group_id"]
            if g not in best_here or row["score"] > best_here[g]["score"]:
                best_here[g] = row
        for g, row in best_here.items():
            slot = per_group.setdefault(g, {"scores": [None] * len(wins), "best": row})
            slot["scores"][wi] = row["score"]
            if row["score"] > slot["best"]["score"]:
                slot["best"] = row
    out = []
    for g, slot in per_group.items():
        agg = sc.aggregate_whole_song(slot["scores"])
        row = dict(slot["best"])
        row.update(score=agg["score"], coverage=agg["coverage"])
        if agg["coverage"] < 0.25:
            row["confidence"] = "low"
        out.append(row)
    return sc.collapse_by_recording(out)[:k]


def compare_windows(a: dict, b: dict, mode: str) -> dict:
    r = score_pair(a, b, settings.weights[mode], detailed=True)
    r.pop("_raw", None)
    return r
