# Setup Guide

## Local Development

### Prerequisites

- **Python** 3.12+
- **Node.js** 22+ (for the frontend dashboard)
- **npm** (ships with Node.js)

### 1. Backend

```bash
cd backend
python -m venv .venv

# Activate the environment
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python -m app.db.init_db
```

The `init_db` command creates the SQLite database and all tables. The database file (`archive_assistant.db`) lives in the `backend/` directory.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 3. Start both

| Service | Command | URL |
|---|---|---|
| Backend | `uvicorn app.main:app --reload` | `http://127.0.0.1:8000` |
| Frontend | `npm run dev` (from `frontend/`) | `http://localhost:5173` |

The Vite dev server proxies `/api/*` requests to the backend on port 8000.

### 4. Prepare test data

Create the directory structure:

```bash
# On Windows, manually create:
#   data/_INGEST/
#   data/_QUARANTINE/
#   data/_REPORTS/
#   data/Music/Library/FLAC/
#   data/Music/Library/MP3/
#   data/Music/Discographies/
#   data/Movies/Library/
#   data/TV/Library/
#   data/Books/
#   data/Audiobooks/Library/

# Or use the sample tree script (requires bash/WSL):
bash scripts/create_sample_tree.sh
```

Drop test media folders into `data/_INGEST/` and run a scan from the dashboard or API.

### 5. Environment variables (optional)

Create `backend/.env` to override defaults:

```env
DEBUG=true
ARCHIVE_ASSISTANT_TIMEZONE=America/Chicago
API_DOCS_ENABLED=false
DATABASE_URL=sqlite:///./archive_assistant.db
```

---

## Docker Compose

```bash
docker-compose up
```

This builds and starts two containers:

- **archive-backend** (port `8000`) — Python 3.12-slim, runs `init_db` then `uvicorn`
- **archive-frontend** (port `5173`) — Node 22-alpine, serves the dashboard with hot-reload

Volumes:
- `./data:/app/data` — persists ingest, library, reports, and move logs
- `./backend/archive_assistant.db:/app/backend/archive_assistant.db` — persists the SQLite database

Environment:
- `TZ=America/Chicago` — container timezone
- `ARCHIVE_ASSISTANT_TIMEZONE=America/Chicago` — app display timezone

---

## TrueNAS Deployment

### Prerequisites

- TrueNAS SCALE 25.10.x (stable branch)
- `rust-pool` for bulk media storage
- `fast-pool` for apps, Docker volumes, and PostgreSQL

### 1. Datasets

```text
rust-pool/
  _INGEST/
  _STAGING/
  _QUARANTINE/
  _REPORTS/
  _METADATA_RECOVERY/
  Music/
  Movies/
  TV/
  Books/
  Audiobooks/
  Photos/
  Documents/
  Projects/
  Backups/

fast-pool/
  apps/
  databases/postgresql/
  docker-volumes/
  service-configs/
  scripts/
  dev-workspaces/
```

### 2. Service user

Create an `archive-assistant` user with access only to the media datasets listed above. Do not grant access to system paths, financial documents, or secrets.

### 3. PostgreSQL migration (future)

SQLite is the default for local development. For NAS production, migrate to PostgreSQL:

1. Create a `postgresql` dataset on `fast-pool`
2. Deploy PostgreSQL as a TrueNAS app or Docker container
3. Update `DATABASE_URL` to point to the PostgreSQL instance
4. Run `init_db` to create tables in PostgreSQL

### 4. Deploy Archive Assistant

Two options:

**A. Docker Compose (recommended):**
- Deploy the `docker-compose.yml` as a TrueNAS custom app
- Mount `rust-pool` datasets to `/app/data/`
- Set environment variables for timezone and database URL

**B. Native Python:**
- Create a Python virtual environment on the NAS
- Run uvicorn directly with systemd or a startup script
- Use a reverse proxy (nginx/Caddy) for TLS

### 5. Health checks

The `/api/health` endpoint returns:

```json
{
  "status": "ok",
  "service": "archive-assistant",
  "debug": false,
  "dev_tools_enabled": false
}
```

Disable debug and dev tools in production:

```env
DEBUG=false
DEV_TOOLS_ENABLED=false
```
