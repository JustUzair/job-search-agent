# Job Hunter Bot — Setup (10 minutes)

No OpenClaw. No framework. Just a Python Telegram bot + Docker.

## What you need first

1. **Docker Desktop** running on your Mac
2. **A Telegram bot token** — message @BotFather on Telegram:
   - Send `/newbot`
   - Follow prompts, get a token like `123456789:ABCdef...`
3. **Your Telegram chat ID** — message @userinfobot on Telegram, it replies with your ID
4. **Your OpenAI API key**

---

## Setup

### 1. Create the project folder

```bash
mkdir job-bot && cd job-bot
```

Copy all these files into it:

```
job-bot/
  bot.py
  scraper.py
  tailor.py
  db.py
  Dockerfile
  docker-compose.yml
  requirements.txt
  .env
  resume/              ← your Overleaf project folder goes here
  data/                ← created automatically, holds DB + tailored resumes
```

### 2. Create your .env file

```bash
cp .env.example .env
```

Edit `.env`:

```
TELEGRAM_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=987654321
OPENAI_API_KEY=sk-...
SCORE_THRESHOLD=60
```

### 3. Add your resume

Download your full Overleaf project:

- In Overleaf: Menu > Download > Source > gives you a .zip
- Unzip it into a folder called `resume/` inside `job-bot/`

Your structure should look like:

```
job-bot/
  resume/
    resume.tex
    _header.tex
    TLCresume.sty
    sections/
      experience.tex
      skills.tex
      objective.tex
      ... etc
```

The `resume/` folder is mounted read-only -- the bot never touches your originals.

### 4. Build and start

```bash
docker compose up --build
```

First run takes ~2 minutes (downloading Python, installing packages).
After that, starts in seconds.

You should see:

```
Bot polling...
Scheduler started — daily scrape at 08:00
```

### 5. Test it

Open Telegram, message your bot: `/scrape`

It will scrape HN, web3.career, etc., score jobs, and send you a digest.

---

## (Optional): Using Ollama for Free (Local LLM)

Skip the OpenAI/Anthropic API keys and run job scoring locally on your machine using **Ollama**. No cloud costs, no API limits, completely free.

### Prerequisites

- **Ollama** installed on your Mac: https://ollama.ai
- A supported model downloaded locally

### Step 1: Install Ollama

Download and install from [ollama.ai](https://ollama.ai). Takes ~2 minutes.

### Step 2: Pull a model

Open a terminal and pull a local model. Choose one:

**Recommended (good balance):**

```bash
ollama pull gpt-oss:20b-cloud
```

**Lightweight (3B parameters, faster):**

```bash
ollama pull phi
```

**Heavier (70B parameters, better quality):**

```bash
ollama pull llama2:70b
```

Pull takes 5–30 minutes depending on model size and internet speed. It downloads once and caches locally.

### Step 2b: Create a custom model from Modelfile (optional)

If you want to use the specialized coding assistant configuration included in this project:

1. Make sure you're in the project directory (contains the `Modelfile`)
2. Create the custom model:

```bash
ollama create qwen3:8b -f Modelfile
```

3. Update your `.env` to use the custom model:

```
MODEL_NAME=qwen3:8b
```

This custom model includes detailed instructions for code quality, architecture, and best practices built into the system prompt.

### Step 3: Update your `.env` file

### Step 4: Update your `.env` file

Replace the API key config with Ollama settings:

```
# **Comment these out if using Ollama:**
# OPENAI_API_KEY=sk-...

# **Add these instead:**
MODEL_PROVIDER=ollama
MODEL_NAME=gpt-oss:20b-cloud
OLLAMA_BASE_URL=http://host.docker.internal:11434

TELEGRAM_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=987654321
SCORE_THRESHOLD=60
```

**Note:** `host.docker.internal` is how Docker containers reach your Mac's `localhost:11434`.

### Step 5: Start Ollama server (in a separate terminal)

```bash
ollama serve
```

Leave this running. You'll see:

```
Listening on 127.0.0.1:11434
```

### Step 6: Start the bot

In your original terminal:

```bash
docker compose up --build
```

The bot now pulls job descriptions directly to your local model. Scoring happens completely on your machine.

### Step 6: Test it

Message your bot: `/scrape`

Jobs will be scored using your local Ollama model (no API calls, no costs).

---

### Step 7: Test it

Message your bot: `/scrape`

Jobs will be scored using your local Ollama model (no API calls, no costs).

---

### Switching models

To try a different model (including your custom model):

1. Pull or create the model:
   - `ollama pull llama2:70b` (pull remote)
   - `ollama create qwen3:8b -f Modelfile` (create from local Modelfile)
2. Update `.env`: `MODEL_NAME=llama2:70b` or `MODEL_NAME=qwen3:8b`
3. Restart: `docker compose down && docker compose up`

### Pros & Cons

| Aspect      | Ollama                           | OpenAI/Anthropic  |
| ----------- | -------------------------------- | ----------------- |
| **Cost**    | Free                             | Pay per request   |
| **Speed**   | Depends on model (30–60 sec/job) | Fast (~5 sec/job) |
| **Quality** | Good (~70–80% accuracy)          | Excellent (~95%+) |
| **Privacy** | All local (no data leaves)       | Cloud-based       |
| **Setup**   | ~30 min (first pull)             | Instant (API key) |

---

## Day-to-day usage

```bash
# Start in background
docker compose up -d

# Watch logs
docker compose logs -f

# Stop
docker compose down

# Rebuild after code changes
docker compose up --build
```

---

## Bot commands

| Command               | What it does                   |
| --------------------- | ------------------------------ |
| `/scrape`             | Run a fresh scrape right now   |
| `/jobs`               | List jobs in queue             |
| `/tailor abc123`      | Tailor resume for job by ID    |
| `/tailor https://...` | Tailor resume for any job URL  |
| `/funded`             | Show recently funded companies |
| `/applied abc123`     | Mark job as applied            |
| `/skip abc123`        | Skip a job                     |

Tailored resumes land in `./data/resumes/<company_timestamp>/` on your Mac.
Each folder is a complete copy of your resume with the relevant files modified.
Copy the folder contents back into your Overleaf project to apply.

---

## Files on your Mac (persisted across restarts)

```
./data/jobs.db          ← SQLite database
./resume/               ← your Overleaf source (read-only mount)
./data/jobs.db          ← SQLite database
./data/resumes/         ← tailored resume folders, one per job
```

---

## Tweaking the candidate profile

Edit the `CANDIDATE_PROFILE` string in `scraper.py`.
Rebuild: `docker compose up --build -d`

## Adjusting the score threshold

Change `SCORE_THRESHOLD` in your `.env` file, then restart:

```bash
docker compose restart
```

## Adding more job sources later

Add a new function in `scraper.py` following the same pattern
(`scrape_xyz() -> list[dict]`) and add it to `run_scrape()`.
