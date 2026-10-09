# AI Model Evaluation & Rubric Management System — Setup Instructions

This guide takes you from a fresh clone to a running application, with the test suite and a demo.
The project is a FastAPI backend that also serves a plain HTML/CSS/JavaScript web interface. No
Node.js or separate frontend server is needed.

## Requirements

- **Python 3.12 or newer** (`python3 --version`)
- **pip** (included with Python)
- **Git**, if you are cloning the repository
- **PostgreSQL 13+** is optional. SQLite is the default and needs no setup.

## Clone the repository

```bash
git clone https://github.com/Ngetich-86/ai-evaluation-rubrics-management-system.git
cd ai-evaluation-rubrics-management-system
```

## Create a virtual environment

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

## Install dependencies

Recommended. This installs the application plus the test and lint tools (pytest, httpx, ruff):

```bash
pip install -e ".[dev]"
```

`pyproject.toml` is the source of truth for dependencies. If you only want to run the
application, `pip install -r requirements.txt` installs the runtime dependencies alone. It does
not include pytest, httpx or ruff, so you can't run tests or quality checks after it.

## Environment configuration

The only setting you are likely to change is `DATABASE_URL`. Without it, the application uses a
local SQLite file:

```text
sqlite:///./eval.db
```

You can set it in the environment, or copy the example file and edit it:

```bash
cp .env.example .env
```

`.env.example`:

```ini
# Copy to .env to override defaults. Never commit a real .env.

# SQLite (default, zero configuration)
DATABASE_URL=sqlite:///./eval.db

# PostgreSQL (requires: pip install -e ".[postgres]")
# DATABASE_URL=postgresql+psycopg://eval_user:change-me@localhost:5432/eval

LOG_LEVEL=INFO
SQL_ECHO=false
```

`.env` is git-ignored. Never commit real credentials.

## Run the application

```bash
uvicorn app.main:app --reload
```

The database schema is created automatically on startup. Then open:

| What | URL |
| --- | --- |
| Web interface | <http://127.0.0.1:8000/> |
| Swagger / OpenAPI docs | <http://127.0.0.1:8000/docs> |
| Health check | <http://127.0.0.1:8000/health> |

The health check returns `{"status":"ok","database":"ok"}`.

## Run tests

```bash
pytest
```

Every test uses its own temporary SQLite database, so tests never touch `eval.db`.

## Run quality checks

```bash
ruff check .
ruff format --check .
```

CI runs the same checks plus the tests on every push and pull request
(`.github/workflows/ci.yml`).

## Demo flow

Start the server first (`uvicorn app.main:app --reload`). Both options below need it running.

### Option A: web interface

Open <http://127.0.0.1:8000/> and work through the numbered sections:

1. **Rubrics**: click **Fill example**, then **Create rubric**. A three-criterion 1–5 rubric
   appears in the list. Click **View** to see its anchors.
2. **Submissions**: click **Fill example**, then **Create submission**. The new submission is
   selected automatically.
3. **Score a submission**: choose the rubric, pick a score for every criterion and an overall
   score, then click **Submit evaluation**. The rater ID advances to `rater-002`. Score again with
   different values to add a second rater.
4. **Scores & agreement**: click **Load evaluations** to see both evaluations with derived
   means. Click **Calculate agreement** for pairwise Cohen's kappa.

To see validation in action, try scoring again as `rater-001`. The page shows the API's 409
duplicate-evaluation message.

### Option B: script

In a second terminal, with the virtual environment active:

```bash
python scripts/demo_flow.py
```

The script runs the same flow through the API and prints each response. It needs `httpx`, which
`pip install -e ".[dev]"` installs. To target another server, pass its address:
`python scripts/demo_flow.py http://127.0.0.1:9000`.

## PostgreSQL

SQLite is all you need for evaluation. To use PostgreSQL instead:

```bash
pip install -e ".[postgres]"          # adds the psycopg driver
export DATABASE_URL="postgresql+psycopg://eval_user:change-me@localhost:5432/eval"
uvicorn app.main:app --reload
```

On Windows PowerShell, set the variable with
`$env:DATABASE_URL = "postgresql+psycopg://..."`, or put it in `.env`.

The database must already exist; the tables are created on startup. If you have Docker, you can
start a disposable server with:

```bash
docker run -d --rm --name eval-postgres \
  -e POSTGRES_USER=eval_user -e POSTGRES_PASSWORD=change-me -e POSTGRES_DB=eval \
  -p 5432:5432 postgres:16-alpine
```

On PostgreSQL, `model_metadata` is stored as `JSONB` and timestamps as `timestamptz`.

## Project structure

```text
app/              FastAPI backend
  api/            HTTP routers (rubrics, submissions, scores, agreement, health, web UI)
  services/       business rules, transactional scoring, Cohen's kappa
  schemas/        Pydantic request/response models
  db/             SQLAlchemy models and session handling
  core/           settings, error handling, JSON request logging
frontend/         web interface: index.html, styles.css, app.js (no build step)
tests/            pytest suite
scripts/          demo_flow.py: end-to-end demo against a running server
docs/             screenshot used in the README
README.md         overview, API reference, agreement metric, design decisions
instructions.md   this guide
```

## Troubleshooting

- **`uvicorn: command not found` or `No module named ...`**: the virtual environment isn't
  active. Run `source .venv/bin/activate` (or `.venv\Scripts\Activate.ps1`) and try again. If
  that doesn't help, reinstall with `pip install -e ".[dev]"`.
- **PowerShell refuses to run `Activate.ps1`**: allow local scripts for your user with
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- **`Address already in use` on port 8000**: another process is using the port. Stop it, or run
  on another port: `uvicorn app.main:app --reload --port 8001`.
- **`unable to open database file` / `attempt to write a readonly database`**: the process can't
  write `eval.db` in the current directory. Run from a directory you own, or point
  `DATABASE_URL` at a writable path, for example `sqlite:////tmp/eval.db`.
- **PostgreSQL `connection refused` or `password authentication failed`**: check that the server
  is running, that the host, port, user, password and database name in `DATABASE_URL` are correct,
  and that the URL starts with `postgresql+psycopg://`.
