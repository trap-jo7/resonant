# Evaluation harness

No labels or results ship with this repo. You create them.

1. Index your catalog, then list indexed windows: `python eval/run_eval.py --list-windows`.
2. Have listeners grade query/result pairs 0–3 (0 = unrelated, 3 = strong match) for **vibe** or **harmony**.
   Save as JSON (see `labels.example.json`). Mark each query `"split": "tune"` or `"held-out"`.
   Tune weights only on `tune`; report `held-out` numbers.
3. `python eval/run_eval.py eval/labels.json` prints Precision@5 (grade >= 2 counts as relevant), nDCG@10 and
   latency p50/p95 for three systems: tempo baseline, embedding only, combined retrieval + reranking.

Recordings in the same `recording_group_id` as the query (duplicates, alternate versions) are excluded from every system.
