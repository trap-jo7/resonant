# Resonant

> Find more music that sounds like this moment.

Select a whole song or a 5–60 s section of an analyzable recording and find musically similar sections in a
permission-cleared catalog, with matching timestamps. Similarity comes from a real pipeline (FFmpeg → librosa + CLAP
embeddings → pgvector retrieval → harmonic/rhythm/timbre reranking). Scores are **experimental and uncalibrated**.

**Status:** Phase 1 (vertical slice) and most of Phase 2 are implemented. Nothing here has been benchmarked yet, and no
evaluation numbers are included. See [Status and limitations](#status-and-limitations).

## Architecture

```
apps/web         Next.js + TypeScript, Tailwind, Motion, TanStack Query, WaveSurfer.js (Regions)
services/api     FastAPI: catalog search, uploads, jobs, similarity, compare, feedback (no ML inference here)
services/worker  Celery: decode, peaks, librosa features, CLAP embeddings, retention purge (models stay warm)
services/common  Shared Python: config, timestamps, scoring, retrieval, permissions, manifest validation
db/              Postgres + pgvector schema, Row Level Security, low-privilege app role
scripts/         Catalog ingestion + FMA candidate finder
eval/            Reproducible evaluation harness (you supply human labels)
```

Postgres/pgvector, Redis, MinIO (private S3-compatible storage), API, worker and beat run in Docker Compose.
The web app runs on your machine with `npm run dev`.

## 1. Install the tools (macOS, VS Code terminal)

Open the folder in VS Code (`code .`), then use **Terminal → New Terminal**.

```bash
# Homebrew packages (skip any you have)
brew install --cask docker           # Docker Desktop; open it once so it finishes setup
brew install node@20 python@3.11 ffmpeg git

# VS Code extensions (also suggested automatically via .vscode/extensions.json)
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension charliermarsh.ruff
code --install-extension ms-azuretools.vscode-docker
code --install-extension dbaeumer.vscode-eslint
code --install-extension esbenp.prettier-vscode
code --install-extension bradlc.vscode-tailwindcss
code --install-extension ms-playwright.playwright
code --install-extension cweijan.vscode-postgresql-client2
```

If `code` isn't found: VS Code → Cmd+Shift+P → "Shell Command: Install 'code' command in PATH".

## 2. Configure

```bash
cp .env.example .env                       # then edit the three "change-me" passwords
cp apps/web/.env.local.example apps/web/.env.local
```

`.env` is git-ignored. Nothing secret goes in `NEXT_PUBLIC_*` variables.

## 3. Model setup (CLAP)

The default checkpoint is `laion/larger_clap_music` (set `CLAP_MODEL` / `CLAP_REVISION`). **Before pinning**, open its
Hugging Face model card and confirm (a) the license permits your use, (b) the expected sample rate (the code assumes
48 kHz mono) and input length (the code assumes ~10 s, so longer sections are split into ≤10 s chunks whose normalised
embeddings are averaged), and (c) the embedding size (512, matching `vector(512)` in `db/schema.sql`).
Then replace `CLAP_REVISION=main` with a commit hash from the model's "Files and versions" tab.
The worker downloads the weights on first start and caches them in the `hfcache` volume.
Also check your installed `transformers`/`torch` versions against the card, then freeze them in
`services/worker/requirements.txt`. I haven't been able to verify version compatibility from my sandbox.

To swap models, implement the `Embedder` protocol in `services/worker/worker/embed.py`, bump
`CLAP_MODEL`/`CLAP_REVISION` (a new `model_version` re-indexes automatically), and update the vector size if it differs.

## 4. Run the backend

```bash
docker compose up --build -d
docker compose logs -f api worker           # Ctrl+C to stop following
```

- API docs (OpenAPI): http://localhost:8000/docs
- MinIO console: http://localhost:9001 (login with `S3_ACCESS_KEY` / `S3_SECRET_KEY`)

## 5. Run the web app

```bash
cd apps/web
npm install            # creates package-lock.json; commit it to pin exact versions
npm run dev            # http://localhost:3000
```

Playwright browsers (once): `npx playwright install chromium`.

## 6. Add music (catalog sources)

| Source | Role in this repo | How |
|---|---|---|
| FMA | Demo catalog + experiments | `pip install -r scripts/requirements.txt`, download `fma_metadata.zip` from github.com/mdeff/fma, run `python scripts/fma_candidates.py fma_metadata/tracks.csv > data/fma_candidates.csv`. It only *suggests* tracks. Check each license, get a **full-length** file, fill the manifest. `fma_small/medium/large` are 30 s clips: fine for pipeline dev, not for trimming demos. |
| Direct artist contributions | Strongest public demo option | Add entries with written permission evidence |
| Jamendo | **Not implemented yet.** The adapter is intentionally left until its terms are checked | `ENABLE_JAMENDO` in `.env.example` is a placeholder |
| MusicBrainz | Metadata-only search results (cached 24 h, 1 req/s, identified User-Agent) | Set `ENABLE_MUSICBRAINZ=true` and put your contact email in `MUSICBRAINZ_USER_AGENT` |
| Uploads | Private queries/comparisons | Built in; deleted after 24 h or immediately on request |
| Spotify | Not used for analysis, ever | `manifest.py` rejects it as a source |

Copy `data/catalog_manifest.example.json` to `data/catalog_manifest.json`, then (with `.env` exported and the
Docker services running; host ports are published for Postgres, Redis and MinIO):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt && pip install ./services/common
set -a; source .env; set +a
export DATABASE_OWNER_URL=postgresql://resonant:$POSTGRES_PASSWORD@localhost:5432/resonant
export REDIS_URL=redis://localhost:6379/0 S3_ENDPOINT=http://localhost:9000
python scripts/ingest_manifest.py data/catalog_manifest.json
```

An entry is skipped unless it has explicit `analysis` / `playback` / `storage` booleans, a `permission_evidence`
note, an attribution string and a full-length file. A streaming link or metadata match is never treated as permission.
Watch indexing in `docker compose logs -f worker`. Each track is decoded once and embedded at 12 s/6 s and 24 s/12 s windows.

## 7. Test

```bash
cd services/api && pip install pytest && PYTHONPATH=../common pytest      # timestamps, permissions, scoring, retrieval logic
cd apps/web && npm run lint && npm run typecheck && npm run test:e2e      # E2E_AUDIO=/path/clip.mp3 enables the backend journey
```

The 16 pure-logic tests pass in my sandbox. Database-backed retrieval tests and the full Playwright journey need your
running stack and are not included as passing results.

## 8. Evaluate

See `eval/README.md`. You supply human-graded pairs; the harness reports P@5, nDCG@10 and p50/p95 latency for a
tempo baseline, embeddings alone, and combined reranking, on separate tune and held-out splits.

## Privacy and security model

- Anonymous httpOnly session cookie; every private row is scoped to it, and enforced by Postgres RLS (the API connects as `resonant_app`).
- Uploads: 50 MB streamed byte cap, 10-minute duration cap and codec/extension allowlist (ffprobe + short decode check), enforced in the API. Subprocesses use argument lists, CPU limits and timeouts.
- Private audio is served through expiring signed URLs (object storage handles HTTP Range, so seeking works). They never appear in public links.
- Uploads and their derived features are deleted after `UPLOAD_RETENTION_HOURS` (24) by the beat job, or immediately via `DELETE /api/uploads/{id}`. Uploads are never added to the recommendation catalog.
- Rate limits per IP via Redis (general, upload, analysis). Uploads/analysis fail closed if Redis is down.

## Status and limitations

**Implemented:** catalog search, metadata-only handling, uploads, real waveform peaks, whole/section selection with draggable
region and typed timestamps, shared player, queued/processing/ready/failed jobs with cancel and retry, cached query features
(keyed by audio hash + range + preprocessing + model), CLAP embeddings, librosa chroma/tempo/onset/timbre features,
exact pgvector search plus a 12-transposition harmonic candidate path, banded-DTW harmonic reranking with transposition,
confidence-weighted combination, coverage-aware whole-song aggregation, duplicate collapsing, deterministic explanations,
feedback/save, private pair compare, retention, RLS, evaluation harness.

**Not done or not verified:**
- **Untested end to end.** I could not run Docker, npm, or the model here. Expect first-run fixes (WaveSurfer region import paths, transformers API differences, Next/Tailwind versions).
- Embeddings: no benchmark of which checkpoint works best on music similarity, and no approximate-retrieval recall measurement. Exact search only; HNSW is commented in the schema pending benchmarks.
- Whole-song search uses a cheaper harmonic score (mean chroma over 12 transpositions) than section search (banded DTW) to bound latency.
- Section queries are compared against the catalog window length closest to their length; very long sections are weaker matches.
- Harmonic similarity is chroma-profile similarity, not chord or note identity. Melody mode is not built.
- Tempo/chroma "confidence" values are heuristics, not calibrated probabilities. Fixed-range timbre descriptors are heuristics too.
- Jamendo adapter not implemented; OpenAPI → TypeScript type generation not wired (types in `lib/api.ts` are hand-written to match `/openapi.json`).
- Uploads are one request (`POST /api/uploads`) rather than separate create/complete calls.
- No right-hand details drawer; "Why this matched" is an inline panel.
- Latency targets (1–2 s warm) are unmeasured. `searches.latency_ms` records real search timings you can summarise with SQL: `SELECT percentile_cont(ARRAY[0.5,0.95]) WITHIN GROUP (ORDER BY latency_ms) FROM searches;`

## Deployment notes

Host the web app on any Node host and the API, worker, beat, Postgres (pgvector), Redis and object storage on a persistent
Docker host. Put web and API on the same registrable domain (cookies are `SameSite=Lax`), set `COOKIE_SECURE=true`,
`CORS_ORIGIN`, run uvicorn with `--proxy-headers` behind your proxy, and set spend caps (see `docs/AUDIT.md`).
