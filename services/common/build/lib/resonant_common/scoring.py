"""Component scoring, reranking and aggregation. Pure functions, no I/O.

All scores are *experimental, uncalibrated* similarity values in [0, 1].
They rank candidates; they are not percentages of musical similarity.
"""
from __future__ import annotations
import math
import numpy as np

# Raw chroma cosine between any two non-negative chroma frames is high (~0.5+) even for unrelated
# music, so we stretch [CHROMA_FLOOR, 1] to [0, 1]. The floor is an experimental setting.
CHROMA_FLOOR = 0.5
MIN_EVIDENCE = 0.35        # share of total weight backed by usable features
MIN_SCORE_FOR_CONFIDENT = 0.55


def cosine01(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = np.linalg.norm(a) * np.linalg.norm(b)
    if d == 0:
        return 0.0
    return float(np.clip((float(a @ b) / d + 1) / 2, 0, 1))  # map [-1,1] -> [0,1]


def _frame_cost(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    an = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    bn = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    return 1.0 - an @ bn.T


def banded_dtw_cost(cost: np.ndarray, band: float = 0.2) -> float:
    """Sakoe-Chiba banded DTW; returns mean cost along the best path."""
    n, m = cost.shape
    w = max(int(band * max(n, m)), abs(n - m) + 1)
    inf = float("inf")
    acc = np.full((n + 1, m + 1), inf)
    steps = np.zeros((n + 1, m + 1))
    acc[0, 0] = 0.0
    for i in range(1, n + 1):
        lo, hi = max(1, i - w), min(m, i + w)
        for j in range(lo, hi + 1):
            prev = min((acc[i - 1, j], steps[i - 1, j]), (acc[i, j - 1], steps[i, j - 1]),
                       (acc[i - 1, j - 1], steps[i - 1, j - 1]))
            acc[i, j] = cost[i - 1, j - 1] + prev[0]
            steps[i, j] = prev[1] + 1
    return float(acc[n, m] / max(steps[n, m], 1)) if acc[n, m] < inf else 1.0


def harmonic_similarity(seq_a, seq_b, band: float = 0.2):
    """Best banded-DTW chroma match over all 12 circular transpositions.

    Returns (score, semitone_shift). Shift is applied to seq_b to best match seq_a.
    This measures harmonic-profile similarity, not chord-progression or note identity.
    """
    a, b = np.asarray(seq_a, float), np.asarray(seq_b, float)
    if a.size == 0 or b.size == 0:
        return 0.0, 0
    best, best_shift = 1.0, 0
    for shift in range(12):
        c = banded_dtw_cost(_frame_cost(a, np.roll(b, shift, axis=1)), band)
        if c < best:
            best, best_shift = c, shift
    raw = 1.0 - best
    score = float(np.clip((raw - CHROMA_FLOOR) / (1 - CHROMA_FLOOR), 0, 1))
    return score, (best_shift if best_shift <= 6 else best_shift - 12)


def rhythm_similarity(tempo_a, conf_a, tempo_b, conf_b, dens_a, dens_b):
    """Tempo-octave-aware similarity. Returns (score, confidence)."""
    if not tempo_a or not tempo_b:
        return 0.0, 0.0
    best = 0.0
    for k, penalty in ((1.0, 1.0), (2.0, 0.9), (0.5, 0.9)):
        tb = tempo_b * k
        err = abs(tempo_a - tb) / max(tempo_a, tb)
        best = max(best, math.exp(-((err / 0.06) ** 2)) * penalty)
    dens = 1.0 - min(abs(dens_a - dens_b) / max(dens_a, dens_b, 1e-6), 1.0)
    score = 0.75 * best + 0.25 * dens
    return float(score), float(min(conf_a or 0, conf_b or 0))


def timbre_similarity(va, vb) -> float:
    """Descriptors are pre-scaled to [0,1] with fixed ranges (see worker features)."""
    a, b = np.asarray(va, float), np.asarray(vb, float)
    return float(np.clip(1.0 - np.mean(np.abs(a - b)), 0, 1))


def combine(components: dict, weights: dict) -> dict:
    """components: {name: (score, confidence)} -> final score, evidence, confidence label.

    Each weight is scaled by its feature confidence, then renormalised, so an uncertain
    component pulls less. `evidence` is the share of nominal weight actually backed by features.
    """
    eff = {k: weights[k] * max(0.0, min(1.0, components[k][1])) for k in weights if k in components}
    total = sum(eff.values())
    evidence = total / sum(weights.values())
    if total <= 0:
        return {"score": 0.0, "evidence": 0.0, "confidence": "low"}
    score = sum(eff[k] * components[k][0] for k in eff) / total
    confident = evidence >= MIN_EVIDENCE and score >= MIN_SCORE_FOR_CONFIDENT
    return {"score": float(score), "evidence": float(evidence), "confidence": "ok" if confident else "low"}


def aggregate_whole_song(best_per_window: list, floor: float = 0.5) -> dict:
    """Coverage-aware aggregate for one candidate recording.

    best_per_window: for each query window, the best score against this recording (or None).
    Windows with no match above `floor` count as zero, so one matching section cannot
    dominate: score = mean over *all* query windows.
    """
    n = len(best_per_window)
    if n == 0:
        return {"score": 0.0, "coverage": 0.0}
    vals = [s if (s is not None and s >= floor) else 0.0 for s in best_per_window]
    return {"score": float(sum(vals) / n), "coverage": float(sum(v > 0 for v in vals) / n)}


def collapse_by_recording(matches: list[dict]) -> list[dict]:
    """Keep the best match per recording group (alternate versions/duplicates share a group)."""
    seen, out = set(), []
    for m in sorted(matches, key=lambda x: x["score"], reverse=True):
        key = m.get("group_id") or m["track_id"]
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def explanations(components: dict, harmonic_shift: int | None) -> list[str]:
    """Deterministic templates tied to measured evidence. No generated musical claims."""
    out = []
    emb = components.get("embedding", (0, 0))[0]
    har = components.get("harmonic", (0, 0))
    rhy = components.get("rhythm", (0, 0))
    if emb >= 0.8:
        out.append("Close overall sonic character in the audio-embedding model.")
    if har[1] >= 0.4 and har[0] >= 0.6:
        t = f", with a consistent shift of {harmonic_shift:+d} semitones" if harmonic_shift else ""
        out.append(f"Similar harmonic profile over time{t} (chroma alignment, not an exact chord match).")
    if rhy[1] >= 0.4 and rhy[0] >= 0.7:
        out.append("Similar tempo and onset density (allowing for double/half-time ambiguity).")
    if components.get("timbre", (0, 0))[0] >= 0.85:
        out.append("Similar loudness and spectral-balance descriptors.")
    return out[:2] or ["Moderate similarity across several measured features."]


def harmonic_fast(mean_a, mean_b) -> tuple[float, int]:
    """Cheap harmonic score from mean chroma over 12 transpositions (used for whole-song search)."""
    a, b = np.asarray(mean_a, float), np.asarray(mean_b, float)
    best, shift = -1.0, 0
    for s in range(12):
        c = float(a @ np.roll(b, s)) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9)
        if c > best:
            best, shift = c, s
    return float(np.clip((best - CHROMA_FLOOR) / (1 - CHROMA_FLOOR), 0, 1)), (shift if shift <= 6 else shift - 12)
