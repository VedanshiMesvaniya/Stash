# Stash — Multi-user AI Personal Finance App

Stash is a FastAPI + React web application for tracking income, expenses, recurring transactions, and generating financial reports with AI-assisted transaction logging and multi-user isolation.

**Live demo**: https://stash-azsp.onrender.com

## Features

### Core functionality

- **AI chat-based entry logging**: Natural language input ("spent 50 on groceries yesterday") → AI extracts transaction details
- **Multi-user**: Every family member, self-registered account, or seeded demo account is completely isolated by `user_id`; one member cannot see another's transactions
- **Two ways to get an account**: self-registration with email verification (a 6-digit code sent via Gmail SMTP), or pre-seeded accounts via `app/database/seed.py`/CLI — see [User management](#user-management) below
- **Transaction management**:
  - Timeline view with edit/delete controls
  - Chat-based transaction correction and deletion (single or multi-select)
  - Cash vs. online wallet split, and per-category monthly budgets
- **Recurring transactions**: Set-and-forget income/expense rules with auto-posting, or manual confirm-to-post for schedules like salary/rent
- **Smart dashboard**:
  - Current balance and monthly summary
  - Top spending categories
  - Low-balance alerts
  - Actionable financial insights
- **Reports**: Monthly breakdowns by category, daily/period trend charts, income vs. expense trends
- **Export formats**: CSV, Excel (XLSX), PDF—all scoped per user
- **Backup/restore**: Full database snapshots (local SQLite only; use Neon's branching on production); restoring requires re-entering the account password and only accepts filenames the app already knows about
- **Multi-currency support**: Live exchange rates, display in INR/USD/GBP/JPY/CNY/KRW/EUR

### Technical resilience

- **Multi-LLM fallback**: Groq → NVIDIA NIM → OpenRouter → pending queue (automatic retry)
- **Offline-first transactions**: Browser IndexedDB queue, syncs on reconnect
- **Pending entry queue**: If every LLM provider is down, messages wait and retry every 5 minutes
- **Signed session cookies**: 30-day expiry, tamper-proof, HTTPS-only in production
- **Brute-force lockout**: Login, the app-lock PIN, and registration codes all lock out after repeated wrong attempts
- **Database flexibility**: SQLite locally, PostgreSQL (Neon) in production

## Demo login

Test the live demo at https://stash-azsp.onrender.com:

- **Email or username**: `guest`
- **Password**: `12345`

This account has pre-loaded sample data. The password is never stored in the browser—only a signed session cookie is maintained.

Alternatively, use "Don't have an account? Create one" on the login page to self-register — enter an email, username, and password, and confirm the 6-digit code sent to that email.

## Private accounts (local development)

Personal or family accounts belong in:

```
app/database/private_accounts.py
```

This file is gitignored on purpose so you can keep your own usernames and passwords out of the repo. It's generated/updated automatically by `scripts/manage_users.py add` (see [User management](#user-management)), or you can hand-write it. Format is a list of `(username, password, display_name)` tuples:

```python
PRIVATE_ACCOUNTS = [
    ("alice", "AlicePass123", "Alice"),
    ("bob", "BobPass456", "Bob"),
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
   cd Stash
   ```

2. **Create Python virtual environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install backend dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env    # Windows: copy .env.example .env
   # Then edit .env with your values (see table below)
   ```

5. **Generate SECRET_KEY** (required; app won't start without it):
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   # Copy the output and paste into .env as SECRET_KEY=...
   ```

6. **(Optional) Set up Gmail SMTP** if you want self-registration to work locally — see the Environment variables table below for `SMTP_*` vars, and [DEPLOY.md](DEPLOY.md) for the App Password setup steps. Without it, registration's send-code step returns a clear error instead of failing silently.

7. **Install frontend dependencies and build**:
   ```bash
   npm install
   npx vite build
   # Vite output lands in app/static/react/ automatically. Always run
   # this from the repo root, not `cd frontend && npm run build` - see
   # DEPLOY.md for why.
   ```

8. **Start the backend**:
   ```bash
   uvicorn app.main:app --reload
   ```

9. **Open in browser**:
   ```
   http://127.0.0.1:8000/login
   ```
   Sign in with `guest` / `12345`, your own private account credentials, or self-register a new account.

## Environment variables

Copy `.env.example` to `.env` and fill in the values below. All keys are optional EXCEPT `SECRET_KEY`.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SECRET_KEY` | **Yes** | — | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | No | (SQLite) | Leave blank for local SQLite in `data/finance.db`; set to Neon connection string for production |
| `GROQ_API_KEY` | No (recommended) | — | Get from https://console.groq.com/keys; enables fast AI parsing |
| `GROQ_MODEL` | No | `llama-3.1-8b-instant` | Groq model name |
| `NVIDIA_API_KEY` | No (recommended) | — | Get from https://build.nvidia.com; second LLM provider (free NIM tier) |
| `NVIDIA_MODEL` | No | `nvidia/nvidia-nemotron-nano-9b-v2` | NVIDIA NIM model name |
| `OPENROUTER_API_KEY` | No (recommended) | — | Get from https://openrouter.ai/keys; third/last-resort LLM provider |
| `OPENROUTER_MODEL` | No | `openrouter/free` | OpenRouter model name |
| `ENVIRONMENT` | No | `development` | Set to `production` to enable HTTPS-only session cookies |
| `PENDING_RETRY_INTERVAL_SECONDS` | No | `300` | How often to retry queued LLM messages (seconds) |
| `APP_PUBLIC_URL` | No | `http://127.0.0.1:8000` | Used for outbound headers; local default is fine during dev |
| `SMTP_HOST` | No | `smtp.gmail.com` | SMTP server for registration verification emails |
| `SMTP_PORT` | No | `587` | STARTTLS port |
| `SMTP_USERNAME` | No (required for registration) | — | Full sending email address, e.g. `noreplystash2026@gmail.com` |
| `SMTP_PASSWORD` | No (required for registration) | — | A Google **App Password** (needs 2-Step Verification on that account) — NOT your normal Gmail password. Generate at https://myaccount.google.com/apppasswords |
| `SMTP_FROM_EMAIL` | No | (same as `SMTP_USERNAME`) | "From" address shown to recipients |
| `SMTP_FROM_NAME` | No | `Stash` | "From" display name shown to recipients |

Without `SMTP_USERNAME`/`SMTP_PASSWORD` set, self-registration's send-code step returns a clear "email sending isn't configured" error instead of failing silently — everything else in the app works fine without them.

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
    auth.py               POST /login, /register/send-code, /register/verify-code, /logout, GET /session, /unlock, /lock-settings
    finance.py            Chat, timeline, dashboard, wallets, budgets, transaction edit/delete
    recurring.py          Recurring transaction CRUD, sync, and manual confirm-to-post
    reports.py            Monthly reports, trends, and CSV/Excel/PDF export
    settings.py           User profile + password change, offline-sync, backup/restore
    routes.py             Router aggregation
  auth/
    auth.py               Login attempt logic (incl. brute-force lockout), session dependency
    registration.py       Self-registration: OTP generation, cooldown, attempt lockout, account creation
    password.py           bcrypt password hashing
    session.py            Session validation and user extraction
  database/
    models.py             SQLAlchemy ORM (User, Income, Expense, PendingRegistration, etc.)
    database.py           Engine, session factory, migration runner
    crud.py                CRUD queries (all scoped by user_id)
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
    backup.py             Database backup/restore helpers (path-traversal safe)
    email_service.py      Gmail SMTP sender for registration verification codes
    notifications.py      Low-balance alert checks
  static/
    react/                Vite-built React app (app/static/react/)
    service-worker.js     Service worker for offline support
    manifest.json         PWA manifest
frontend/
  src/
    App.jsx               React app root (incl. Login/Register/Verify auth flow)
    main.jsx              React entry point
    api.js                API fetch wrapper
    styles.css            Global styles
    components/           React components (charts, UI widgets, etc.)
  index.html              HTML template
scripts/
  manage_users.py         CLI tool to add/delete/list users, or delete-all-except one
  reset_password.py       CLI tool to reset a user's password
.github/
  workflows/ci.yml        GitHub Actions CI (backend smoke tests + frontend build check)
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

# Delete every user except one (e.g. to reset test accounts, keeping guest)
python -m scripts.manage_users delete-all-except guest

# Reset password for an existing user
python -m scripts.reset_password alice NewPassword123
```

When you add a user locally, the tool also updates `app/database/private_accounts.py` (if it exists) so the account is seeded on next app startup. Users can also create their own account without the CLI at all, via self-registration on the login page.

## API endpoints

### Authentication (`/api/auth`)

- `POST /api/auth/login` — Email or username + password → signed session cookie (locks out after 5 wrong attempts)
- `POST /api/auth/register/send-code` — Email + username + password + confirm_password → emails a 6-digit verification code via Gmail SMTP
- `POST /api/auth/register/verify-code` — Email + code → creates the account and logs in, if the code is correct (locks out after 5 wrong codes)
- `POST /api/auth/logout` — Clears session cookie
- `GET /api/auth/session` — Returns current logged-in user info
- `POST /api/auth/unlock` — Check the app-lock PIN (locks out after 5 wrong attempts)
- `POST /api/auth/lock-settings` — Enable/disable app lock, biometric flag, and set/clear the PIN

### Finance (`/api`)

- `POST /api/chat` — Send user message; AI parses and returns structured response + transactions
- `POST /api/chat/confirm-correction` — Confirm an amount correction the chat flow proposed
- `POST /api/chat/confirm-delete` — Confirm deleting one or more transactions the chat flow proposed
- `GET /api/chat/history` — Chat transcript, including chart data (`reportEntries`) for report replies
- `DELETE /api/chat/message/{id}` — Edit-and-resend: deletes a user message + its assistant reply
- `DELETE /api/chat/history` — Clears the whole chat transcript (does not touch transaction data)
- `GET /api/pending` — Chat messages queued because every LLM provider was down when sent
- `GET /api/dashboard` — Balance, monthly summary, smart suggestions (also catches up any due auto-post recurring schedules)
- `GET /api/wallets` — Cash vs. online running balances
- `GET /api/budgets` / `POST /api/budgets` — Per-category monthly spending limits
- `GET /api/timeline` — Transaction history (by month, or `?all=true` for the last 200)
- `PUT /api/transactions/{type}/{id}` — Edit an existing income/expense transaction
- `DELETE /api/transactions/{type}/{id}` — Delete a transaction

### Recurring (`/api/recurring`)

- `GET /api/recurring` — List recurring transaction rules (also syncs any due auto-post schedules first)
- `POST /api/recurring` — Create new rule
- `PUT /api/recurring/{id}` — Edit rule
- `POST /api/recurring/{id}/disable` — Deactivate a rule (there's no hard delete — disabling keeps history intact)
- `POST /api/recurring/sync` — Manually trigger auto-posting
- `GET /api/recurring/due` — Manual (non-auto-post) schedules waiting for the user to confirm, e.g. salary/rent
- `POST /api/recurring/{id}/confirm` — Confirm posting a manual schedule for this cycle

### Reports & export (`/api`)

- `GET /api/reports` — Full monthly report (category breakdown, etc.)
- `GET /api/reports/trend` — Income vs. expense trend over a period
- `GET /api/reports/months` — List available month/year pairs with data
- `GET /api/export/csv` / `GET /api/export/excel` / `GET /api/export/pdf` — Download a full transaction export

### Settings (`/api`)

- `GET /api/settings` — User profile (currency, preferences, theme, lock status)
- `PUT /api/settings` — Update profile; also handles username changes and password changes (pass `old_password` + `new_password`)
- `POST /api/sync` — Reconcile the browser's offline IndexedDB queue
- `POST /api/backup` — Create database backup (SQLite only)
- `GET /api/backup/list` — List available backup filenames
- `POST /api/backup/restore` — Restore from a backup by filename (SQLite only; requires the account's current password, and only accepts filenames already known to `GET /api/backup/list` — no arbitrary paths)

## CI/CD

Every push and PR to `main` or `feature/add_new` runs `.github/workflows/ci.yml` on GitHub Actions, two jobs:

- **backend** — syntax-checks every `.py` file, imports `app.main` (catches broken wiring, not just syntax errors), runs migrations + seeding against a fresh database, and smoke-tests login/session through the real routes with the seeded `guest` account.
- **frontend** — `npm ci` + `npx vite build` from the repo root, then diffs the freshly built output against what's committed in `app/static/react/`. Fails if they differ, since that means `frontend/src` changed but the prebuilt bundle wasn't rebuilt and committed — Render never rebuilds it itself (see [DEPLOY.md](DEPLOY.md)).

Nothing here deploys anything — Render already auto-deploys from GitHub on its own. The workflow only makes sure whatever reaches `main` actually starts up correctly. To make that enforced rather than advisory, add a branch protection rule on `main` (Settings → Branches → add rule → require status checks → select `backend` and `frontend`).

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for a detailed breakdown of the multi-user isolation model, LLM fallback logic, offline sync, and all service modules.
