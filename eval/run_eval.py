import json, math, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "common"))
import numpy as np
from resonant_common import retrieval, scoring as sc
from resonant_common.config import settings
from resonant_common.db import owner_connection

K_P, K_N = 5, 10


def query_window(conn, q):
    r = conn.execute("""SELECT s.*, COALESCE(t.recording_group_id, t.id) AS group_id FROM segments s JOIN tracks t ON t.id = s.track_id
                        WHERE s.track_id = %s AND abs(s.start_s - %s) < 0.01 AND abs(s.end_s - %s) < 0.01
                        AND s.model_version = %s AND s.preprocess_version = %s LIMIT 1""",
                     (q["track_id"], q["start_s"], q["end_s"], settings.model_version, settings.preprocess_version)).fetchone()
    if not r:
        raise SystemExit(f"Query window not indexed: {q}. Use --list-windows.")
    r["embedding"], r["chroma_mean"] = list(r["embedding"]), list(r["chroma_mean"])
    return r


def rank_baseline(conn, q):
    """Metadata/tempo baseline: octave-aware tempo closeness only."""
    rows = conn.execute("""SELECT s.track_id, COALESCE(t.recording_group_id,t.id) AS g, s.start_s, s.end_s, s.tempo
                           FROM segments s JOIN tracks t ON t.id=s.track_id JOIN audio_assets a ON a.id=s.asset_id
                           WHERE a.visibility='catalog' AND s.scale_s=%s AND COALESCE(t.recording_group_id,t.id) <> %s
                           AND s.model_version=%s""", (retrieval.pick_scale(q["end_s"] - q["start_s"]), q["group_id"], settings.model_version)).fetchall()
    def err(r):
        return min(abs(q["tempo"] - r["tempo"] * k) / max(q["tempo"], r["tempo"] * k) for k in (1, 2, .5))
    best = {}
    for r in sorted(rows, key=err):
        best.setdefault(str(r["g"]), str(r["track_id"]))
    return list(best.values())


def rank_weights(conn, q, weights, mode):
    scale = retrieval.pick_scale(q["end_s"] - q["start_s"])
    cands = retrieval.candidates(conn, q, scale, mode, q["group_id"])
    rows = [retrieval._row(s, retrieval.score_pair(q, s, weights, True)) for s in cands.values()]
    return [r["track_id"] for r in sc.collapse_by_recording(rows)]


def p_at_k(ranked, grades, k):
    return sum(grades.get(t, 0) >= 2 for t in ranked[:k]) / k


def ndcg(ranked, grades, k):
    dcg = sum((2 ** grades.get(t, 0) - 1) / math.log2(i + 2) for i, t in enumerate(ranked[:k]))
    ideal = sorted(grades.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def main():
    conn = owner_connection()
    if "--list-windows" in sys.argv:
        for r in conn.execute("SELECT t.title, t.id, s.start_s, s.end_s FROM segments s JOIN tracks t ON t.id=s.track_id ORDER BY t.title, s.start_s"):
            print(r["id"], r["start_s"], r["end_s"], r["title"])
        return
    labels = json.loads(Path(sys.argv[1]).read_text())
    systems = {"tempo-baseline": None, "embedding-only": {"embedding": 1.0, "harmonic": 0, "rhythm": 0, "timbre": 0}, "combined": "mode"}
    out = {}
    for split in ("tune", "held-out"):
        items = [l for l in labels if l["split"] == split]
        for name, cfg in systems.items():
            ps, ns, lat = [], [], []
            for l in items:
                q = query_window(conn, l["query"])
                t0 = time.perf_counter()
                if cfg is None:
                    ranked = rank_baseline(conn, q)
                else:
                    w = settings.weights[l["mode"]] if cfg == "mode" else cfg
                    ranked = rank_weights(conn, q, w, l["mode"] if cfg == "mode" else "vibe")
                lat.append((time.perf_counter() - t0) * 1000)
                ps.append(p_at_k(ranked, l["grades"], K_P)); ns.append(ndcg(ranked, l["grades"], K_N))
            if items:
                out[(split, name)] = (len(items), np.mean(ps), np.mean(ns), np.percentile(lat, 50), np.percentile(lat, 95))
    print(f"{'split':9} {'system':15} {'n':>3} {'P@5':>6} {'nDCG@10':>8} {'p50 ms':>8} {'p95 ms':>8}")
    for (split, name), (n, p, nd, a, b) in out.items():
        print(f"{split:9} {name:15} {n:>3} {p:6.3f} {nd:8.3f} {a:8.0f} {b:8.0f}")
    if not out:
        print("No labeled queries found. Nothing was evaluated.")


if __name__ == "__main__":
    main()
