# OpenClaw

Personal job-search intelligence system for discovering roles, scoring fit, and tailoring resumes.

This repo is no longer a Telegram bot. The current product is a Dockerized FastAPI backend with a React frontend, backed by SQLite, with Ollama-first model support and plugin-based campaign discovery.

## What it does

- Runs scheduled and on-demand job scraping across multiple sources.
- Supports reusable search campaigns built from natural-language prompts.
- Uses deterministic discovery plugins and real URLs instead of model-invented links.
- Scores roles against a stored candidate profile.
- Stores evidence for where a job came from: plugin, query, canonical URL.
- Tailors resume variants from job URLs, pasted JDs, or saved jobs.
- Keeps notes, profile context, funded-company leads, interview answers, and outreach helpers in one app.

## Current stack

- Backend: FastAPI
- Frontend: React + Vite + Tailwind
- Database: SQLite
- LLM path: Ollama-first, with wrappers for OpenAI and Anthropic
- Scraping: `requests`, `BeautifulSoup`, `aiohttp`, `Playwright`
- Resume output: LaTeX + `latexmk`

## Main features

### 1. Campaign-based discovery

Campaigns represent search intent, not just a flat keyword list.

Example:

```text
Find remote or India-friendly AI-native backend, FDE/Solutions, DevRel, backend, fullstack, developer-tools, and Web3 infra roles. Avoid pure sales, pure support, senior/staff-only, and onsite-only roles.
```

The campaign pipeline:

```text
Prompt
  -> planner model
  -> discovery plugins
  -> URL normalization / dedupe
  -> fetch / parse
  -> hard filters
  -> fit scoring
  -> SQLite + frontend results
```

Currently supported discovery plugins:

- `ollama_web`
- `ats`
- `hn`
- `web3`
- `manual`
- `ddg_optional`

### 2. ATS discovery and scraping

The app directly fetches public Greenhouse, Lever, and Ashby job boards.

ATS registry discovery is now separated from interactive campaign runs. You can refresh the ATS registry explicitly instead of forcing every campaign to do bootstrap discovery inline.

### 3. Job scoring

Jobs are scored against the stored candidate profile and campaign intent.

Current fit output includes:

- `score`
- `reason`
- `fit_band`
- `matched_role_family`
- `red_flags`

### 4. Resume tailoring

The app can tailor resumes from:

- saved jobs
- arbitrary job URLs
- pasted job descriptions

It writes full variant folders and ZIP/PDF outputs under `data/resumes/`.

### 5. Campaign archiving

Campaigns can be archived and restored. Archive is a soft-delete:

- archived campaigns disappear from the active list
- history remains in the database
- archived campaigns can be restored from the UI

## Repo structure

```text
src/backend/
  main.py                FastAPI app and API routes
  db.py                  SQLite schema, migrations, persistence helpers
  llm.py                 provider abstraction and task-specific model routing
  scraper.py             legacy scrape pipeline + generic page parsing
  sources_ats.py         ATS company discovery and ATS board fetchers
  campaigns.py           campaign planning and discovery execution
  tailor.py              resume tailoring and variant generation
  outreach.py            outreach/contact discovery helpers
  discovery/
    base.py
    registry.py
    url_utils.py
    ollama_web.py
    ats.py
    hn.py
    web3.py
    manual.py
    ddg_optional.py

src/frontend/
  src/
    pages/
      Jobs.jsx
      Campaigns.jsx
      Funded.jsx
      Resumes.jsx
      ResumeEdit.jsx
      Journal.jsx
      InterviewPrep.jsx
      Outreach.jsx
      Config.jsx

resume/                  source resume project mounted read-only into container
data/                    SQLite DB + generated outputs
```

## Setup

### Prerequisites

- Docker Desktop
- Ollama running on the host machine if using `MODEL_PROVIDER=ollama`
- A LaTeX resume source tree under `resume/`

### Resume layout

The app expects a LaTeX project like:

```text
resume/
  resume.tex
  _header.tex
  TLCresume.sty
  sections/
    experience.tex
    skills.tex
    projects.tex
    education.tex
    ...
```

The `resume/` mount is read-only. Tailored variants are written into `data/resumes/`.

### Environment

Start from:

```bash
cp .env.example .env
```

Important variables:

```env
MODEL_PROVIDER=ollama
MODEL_API_KEY=ollama
MODEL_NAME=gemma4:31b-cloud
OLLAMA_BASE_URL=http://host.docker.internal:11434

SCORE_MODEL=gemma4:31b-cloud
PLANNER_MODEL=gemma4:31b-cloud
TAILOR_MODEL=gemma4:31b-cloud
RESEARCH_MODEL=gemma4:31b-cloud

DEFAULT_THINK=false
SCORE_THINK=false
PLANNER_THINK=false
TAILOR_THINK=false
RESEARCH_THINK=low

OLLAMA_API_KEY=your_ollama_api_key
ENABLE_OLLAMA_WEB_SEARCH=true
OLLAMA_WEB_MAX_RESULTS=5
ENABLE_DDG_SEARCH=false
OLLAMA_CLOUD_NATIVE_JSON=false

SCORE_THRESHOLD=60

SERPER_API_KEY=
SCRAPERAPI_KEY=
HUNTER_API_KEY=
```

Notes:

- `OLLAMA_API_KEY` is used for `ollama_web`.
- If `ENABLE_OLLAMA_WEB_SEARCH` is omitted, the backend now auto-enables `ollama_web` when `OLLAMA_API_KEY` is present.
- `SERPER_API_KEY`, `SCRAPERAPI_KEY`, and `HUNTER_API_KEY` are only for outreach helpers.

### Start the app

```bash
docker compose up --build
```

Backend:

- `http://localhost:8000`

Frontend:

- served by FastAPI from the built `src/frontend/dist`

## Frontend development

The Docker container serves the built frontend assets from `src/frontend/dist`.

When you change frontend code:

```bash
cd src/frontend
npm install
npm run build
```

Then refresh the browser. The `dist` directory is mounted into the container.

Backend code is mounted directly, so Python changes hot-reload under `uvicorn --reload`.

## Main UI pages

- `Jobs`: legacy queue + manual tailor-from-URL/JD
- `Campaigns`: campaign creation, run, archive/restore, results
- `Funded`: funded company leads
- `Resumes`: generated variants
- `Resume Edit`: free-form resume edits
- `Journal`: work log / personal memory
- `Interview`: answer hiring questions in your voice
- `Outreach`: contact discovery helpers
- `Config`: legacy global search config + candidate profile

## API overview

### Jobs

- `GET /api/jobs`
- `GET /api/jobs/all`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/status`

### Scraping

- `POST /api/scrape`
- `GET /api/scrape/status`
- `GET /api/batches`
- `POST /api/batches/poll`

### Campaigns

- `GET /api/campaigns`
- `GET /api/campaigns?include_archived=true`
- `POST /api/campaigns`
- `POST /api/campaigns/{id}/run`
- `POST /api/campaigns/{id}/archive`
- `POST /api/campaigns/{id}/restore`
- `GET /api/campaigns/{id}/results`
- `POST /api/discovery/run`
- `POST /api/discovery/ats/refresh`

### Resume / profile

- `POST /api/tailor`
- `POST /api/resume/edit`
- `POST /api/variants/{id}/refine`
- `GET /api/variants`
- `GET /api/variants/{id}/zip`
- `GET /api/variants/{id}/pdf`
- `GET /api/profile`
- `PUT /api/profile`
- `POST /api/profile/sync-from-journal`

### Other

- `GET /api/funded`
- `GET /api/journal`
- `POST /api/journal`
- `POST /api/resumediff`
- `POST /api/interview/answer`
- `GET /api/config`
- `PUT /api/config`
- `GET /api/sources`

## Operational notes

### Campaign runs

- Campaign runs are concurrent across plugins, materialization, and scoring.
- ATS registry refresh is explicit and separate from interactive campaign execution.
- ATS board fetching still takes real time because it is doing actual network work.

### Data persistence

Persisted on the host:

```text
data/jobs.db
data/resumes/
```

### Scheduled background work

Configured in the backend lifespan:

- daily scrape at `08:00` Asia/Kolkata
- batch polling every `5` minutes

## Known rough edges

- Some legacy README-era terminology still exists in variable names and comments.
- Company extraction from generic job pages is improving but not perfect.
- Some older job rows may still contain weak company values from earlier runs.
- `main.py` currently emits a pre-existing Python string escape warning at import time.
- Frontend build emits a Vite/package module warning but still builds cleanly.

## Typical workflow

1. Start Ollama on the host.
2. Start the app with `docker compose up --build`.
3. Open the UI at `http://localhost:8000`.
4. Create or quick-run a campaign.
5. Inspect surfaced jobs and evidence.
6. Tailor a resume variant from a saved job or pasted JD.
7. Archive old campaigns instead of deleting them.

## Pushing to GitHub

Before pushing:

```bash
cd src/frontend && npm run build
docker compose up --build
```

Check:

- UI loads
- campaign creation/runs work
- archived campaigns can be restored
- backend starts cleanly enough for your target environment

Do not commit:

- `.env`
- local secrets
- unnecessary generated artifacts if you do not want them versioned
