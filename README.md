# Stash — Multi-user AI Personal Finance App

Stash is a FastAPI + React web application for tracking income, expenses, recurring transactions, and generating financial reports with AI-assisted transaction logging and multi-user isolation.

**Live demo**: https://stash-azsp.onrender.com

## Features

### Core functionality

- **AI chat-based entry logging**: Natural language input ("spent 50 on groceries yesterday") → AI extracts transaction details
- **Multi-user families**: Up to 5 family members, completely isolated by user_id; one member cannot see another's transactions
- **Transaction management**:
  - Timeline view with edit/delete controls
  - Chat-based transaction correction
  - Transaction history with full description and metadata
- **Recurring transactions**: Set-and-forget income/expense rules with auto-posting
- **Smart dashboard**:
  - Current balance and monthly summary
  - Top spending categories
  - Low-balance alerts
  - Actionable financial insights
- **Reports**: Monthly breakdowns by category, daily trend charts, income vs. expense trends
- **Export formats**: CSV, Excel (XLSX), PDF—all scoped per user
- **Backup/restore**: Full database snapshots (local SQLite only; use Neon's branching on production)
- **Multi-currency support**: Live exchange rates, display in INR/USD/GBP/JPY/CNY/KRW/EUR

### Technical resilience

- **Multi-LLM fallback**: Groq → OpenRouter → pending queue (automatic retry)
- **Offline-first transactions**: Browser IndexedDB queue, syncs on reconnect
- **Pending entry queue**: If both LLM providers are down, messages wait and retry every 5 minutes
- **Signed session cookies**: 30-day expiry, tamper-proof, HTTPS-only in production
- **Database flexibility**: SQLite locally, PostgreSQL (Neon) in production

## Demo login

Test the live demo at https://stash-azsp.onrender.com:

- **Username**: `guest`
- **Password**: `12345`

This account has pre-loaded sample data. The password is never stored in the browser—only a signed session cookie is maintained.

## Private accounts (local development)

Personal or family accounts belong in:

```
app/database/private_accounts.py
```

This file is gitignored on purpose so you can keep your own usernames and passwords out of the repo. Format:

```python
PRIVATE_ACCOUNTS = [
    {"username": "alice", "password": "AlicePass123", "name": "Alice"},
    {"username": "bob", "password": "BobPass456", "name": "Bob"},
]
```

These accounts are seeded automatically on first startup.

## Fresh clone setup

### Prerequisites

- Python 3.9+
- Node.js 16+ (for frontend build)
- SQLite (included with Python) or Postgres/Neon (for production)

### Steps

1. **Clone and navigate to the project**:
   ```bash
   git clone <repo-url>
   cd Stash_multiuser_updated
   ```

2. **Create Python virtual environment**:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install backend dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   copy .env.example .env
   # Then edit .env with your values (see table below)
   ```

5. **Generate SECRET_KEY** (required; app won't start without it):
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   # Copy the output and paste into .env as SECRET_KEY=...
   ```

6. **Install frontend dependencies and build**:
   ```bash
   npm install
   npm run build
   # Vite output lands in app/static/react/ automatically
   ```

7. **Start the backend**:
   ```bash
   uvicorn app.main:app --reload
   ```

8. **Open in browser**:
   ```
   http://127.0.0.1:8000/login
   ```
   Sign in with `guest` / `12345` or your private account credentials.

## Environment variables

Copy `.env.example` to `.env` and fill in the values below. All keys are optional EXCEPT `SECRET_KEY`.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SECRET_KEY` | **Yes** | — | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | No | (SQLite) | Leave blank for local SQLite in `data/finance.db`; set to Neon connection string for production |
| `GROQ_API_KEY` | No (recommended) | — | Get from https://console.groq.com/keys; enables fast AI parsing |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model name |
| `OPENROUTER_API_KEY` | No (recommended) | — | Get from https://openrouter.ai/keys; fallback LLM provider |
| `OPENROUTER_MODEL` | No | `meta-llama/llama-3.3-70b-instruct:free` | OpenRouter model name |
| `ENVIRONMENT` | No | `development` | Set to `production` to enable HTTPS-only session cookies |
| `PENDING_RETRY_INTERVAL_SECONDS` | No | `300` | How often to retry queued LLM messages (seconds) |
| `APP_PUBLIC_URL` | No | `http://127.0.0.1:8000` | Used for outbound headers; local default is fine during dev |

### LLM setup notes

- Both Groq and OpenRouter are optional, but at least one is recommended.
- If both are missing or down, chat messages queue to `pending_entries` and retry automatically.
- For OpenRouter, do a one-time $10 credit top-up to raise your daily cap from 50 to 1,000 requests.

## Project structure

```
app/
  main.py                 FastAPI entry point, middleware setup, background tasks
  ai/
    llm.py                LLM calls (Groq/OpenRouter with fallback)
    extractor.py          Parse LLM response into structured transactions
    intent_detector.py    Classify user intent (add, ask, etc.)
    parser.py             Date parsing (N days ago, last week, etc.)
    response.py           QA prompt handler for non-transaction questions
    prompts.py            Centralized prompt templates
  api/
    auth.py               POST /login, /logout, /session
    finance.py            POST /api/chat, GET /api/timeline, PUT /api/transactions/{id}, etc.
    recurring.py          Recurring transaction CRUD and sync
    reports.py            Monthly reports and category breakdowns
    settings.py           User settings, export, offline-sync, backup/restore
    routes.py             Router aggregation
  auth/
    auth.py               Session helpers
    password.py           bcrypt password hashing
    session.py            Session validation and user extraction
  database/
    models.py             SQLAlchemy ORM (User, Income, Expense, etc.)
    database.py           Engine, session factory, migration runner
    crud.py               CRUD queries (all scoped by user_id)
    seed.py               Default categories and accounts
    migrations.py         SQL schema
    private_accounts.py   Local-only user accounts (gitignored)
  services/
    finance.py            Transaction creation from chat
    recurring.py          Auto-posting recurring transactions
    analytics.py          Dashboard data and smart suggestions
    export.py             CSV, Excel, PDF export
    sync.py               Offline queue reconciliation
    currency.py           Exchange rate lookups and formatting
    backup.py             Database backup/restore helpers
    notifications.py      Low-balance alert checks
  static/
    react/                Vite-built React app (app/static/react/)
    service-worker.js     Service worker for offline support
    manifest.json         PWA manifest
frontend/
  src/
    App.jsx               React app root
    main.jsx              React entry point
    api.js                API fetch wrapper
    styles.css            Global styles
    components/           React components (charts, UI widgets, etc.)
  index.html              HTML template
scripts/
  manage_users.py         CLI tool to add/delete/list users
  reset_password.py       CLI tool to reset a user's password
```

## User management

Manage users via the CLI tool:

```bash
# List all users
python -m scripts.manage_users list

# Add a new user
python -m scripts.manage_users add alice "MyStrongPassword" "Alice"

# Delete a user (removes all their transactions, chats, recurring rules)
python -m scripts.manage_users delete alice

# Reset password for an existing user
python -m scripts.reset_password alice NewPassword123
```

When you add a user locally, the tool also updates `app/database/private_accounts.py` (if it exists) so the account is seeded on next app startup.

## API endpoints

### Authentication (no /api prefix)

- `POST /login` — Form submission; username + password → signed session cookie
- `POST /logout` — Clears session cookie
- `GET /session` — Returns current logged-in user info

### Finance (`/api/finance`)

- `POST /api/chat` — Send user message; AI parses and returns structured response + transactions
- `GET /api/timeline` — Get transaction history (paginated, scoped to current user)
- `GET /api/dashboard` — Get balance, monthly summary, smart suggestions
- `PUT /api/transactions/{id}` — Edit existing transaction
- `DELETE /api/transactions/{id}` — Delete transaction

### Recurring (`/api/recurring`)

- `GET /api/recurring` — List recurring transaction rules
- `POST /api/recurring` — Create new rule
- `PUT /api/recurring/{id}` — Edit rule
- `DELETE /api/recurring/{id}` — Delete rule
- `POST /api/recurring/sync` — Manually trigger auto-posting

### Reports (`/api/reports`)

- `GET /api/reports/months` — List available month/year pairs
- `GET /api/reports/month/{year}/{month}` — Category breakdown and daily trends

### Settings (`/api/settings`)

- `GET /api/settings` — User profile (currency, preferences, theme)
- `PUT /api/settings` — Update profile
- `POST /api/password/change` — Change password (requires old password)
- `POST /api/settings/export/{format}` — Export as csv/excel/pdf
- `POST /api/settings/offline-sync` — Reconcile browser IndexedDB queue
- `POST /api/backup` — Create database backup (SQLite only)
- `GET /api/restore` — Restore from backup (SQLite only)

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for a detailed breakdown of the multi-user isolation model, LLM fallback logic, offline sync, and all service modules.
