# Architecture

## Overview

Stash is a multi-user, AI-powered personal finance web application:

- **Backend**: FastAPI serves the API, authentication, transaction logic, and static frontend build
- **Frontend**: React handles the browser UI with offline-first IndexedDB queuing
- **Database**: SQLAlchemy + PostgreSQL (Neon) or SQLite (local development)
- **LLM**: Multi-provider AI for chat-based transaction entry with fallback and retry queue
- **Isolation**: Strict `user_id` scoping on every transaction ensures family members cannot access each other's data

## Request flow

1. User signs in with username + password
2. Backend verifies password hash via bcrypt
3. Backend creates a signed session cookie (`stash_session`)
4. Every API request validates the cookie to resolve the current `user_id`
5. All CRUD operations filter by `user_id` at the database layer (no application-level leaks)
6. Session expires after 30 days (configurable)

## Multi-user isolation

Every transaction table is scoped by `user_id`:
- `income`, `expense`, `categories`, `recurring_transactions`, `recurring_postings`
- `chat_messages`, `pending_entries`, all exports

One user can never see, edit, or export another user's data. Multi-user families are seeded at startup via `app/database/seed.py` with static username/password credentials (no self-signup endpoint).

## Data model

Main tables:

- **users**: Login credentials, preferences (currency, alert threshold, salary day), theme
- **income**: Amount, source, date, description, user_id
- **expense**: Amount, category, date, description, user_id
- **categories**: Auto-seeded category list per user (income sources vs. expense categories)
- **chat_messages**: Timestamp, user message, assistant response, user_id
- **recurring_transactions**: Frequency, amount, label, enabled flag, user_id
- **recurring_postings**: Idempotency marker (source_transaction_id + posting_date) to prevent duplicate auto-posts
- **pending_entries**: Chat messages queued when both LLM providers are down/rate-limited (survives restarts)

Notes:

- Income and expense are stored separately for reporting clarity
- Balance is derived on-the-fly as `SUM(income) - SUM(expense)` filtered by user_id
- Recurring postings include an idempotency key so auto-posting can restart safely
- `pending_entries` includes retry count and last-attempted timestamp

## Backend modules

### Entry points and routing

- **app/main.py**
  - FastAPI app initialization with SessionMiddleware for signed cookies
  - Database migrations and seed loading on startup
  - Mounts React build at `/` and static assets at `/static`
  - Starts background retry loop for pending LLM messages
  - Enforces `SECRET_KEY` at startup (fails loudly if missing)

- **app/api/routes.py**
  - Aggregates all API sub-routers under `/api` prefix
  - Includes: finance, reports, settings, recurring

- **app/api/auth.py**
  - POST `/login`, `/logout`, `/session`
  - Session state validation
  - Password change endpoint (requires old password)

### API endpoints

- **app/api/finance.py**
  - POST `/api/chat` — Send a message for AI-assisted entry parsing
  - GET `/api/timeline` — Get user's transaction history (with pagination)
  - GET `/api/dashboard` — Get balance, monthly totals, smart suggestions
  - PUT `/api/transactions/{id}` — Edit transaction
  - DELETE `/api/transactions/{id}` — Delete transaction
  - POST `/api/transactions/correct` — Chat-based transaction correction workflow

- **app/api/recurring.py**
  - GET `/api/recurring` — List recurring transactions
  - POST `/api/recurring` — Create new recurring transaction
  - PUT `/api/recurring/{id}` — Edit recurring transaction
  - DELETE `/api/recurring/{id}` — Delete recurring transaction
  - POST `/api/recurring/sync` — Manually trigger auto-posting

- **app/api/reports.py**
  - GET `/api/reports/months` — Available month/year pairs
  - GET `/api/reports/month/{year}/{month}` — Category breakdown and daily trend

- **app/api/settings.py**
  - GET `/api/settings` — User profile, currency, preferences
  - PUT `/api/settings` — Update currency, alert threshold, salary day, theme
  - POST `/api/password/change` — Change password
  - POST `/api/settings/export/{format}` — Export as CSV/Excel/PDF
  - POST `/api/settings/offline-sync` — Reconcile browser IndexedDB queue
  - POST `/api/backup`, GET `/api/restore` — Backup/restore (SQLite only)

### Database layer

- **app/database/models.py**
  - SQLAlchemy ORM models for all tables with `user_id` field on every transaction table

- **app/database/database.py**
  - SQLAlchemy engine + session factory
  - Support for Postgres (via `DATABASE_URL`) or SQLite (blank `DATABASE_URL`)
  - Migration runner

- **app/database/crud.py**
  - Thin query helpers (all scoped by `user_id`)
  - `get_timeline()`, `get_month_summary()`, `get_balance()`
  - `create_income()`, `create_expense()`, `create_category()`, etc.
  - No business logic — just persistence

- **app/database/seed.py**
  - Seeds default categories (income sources, expense categories)
  - Seeds family accounts from `FAMILY_ACCOUNTS` list
  - Loads gitignored `private_accounts.py` for local-only accounts

### AI and LLM

- **app/ai/llm.py**
  - Calls Groq (`llama-3.3-70b-versatile`) first
  - Falls back to OpenRouter if Groq fails/times out/rate-limits
  - If both are down, raises `LLMUnavailableError` — caller queues to `pending_entries`
  - In-memory rate-limit tracking to detect backoff signals

- **app/ai/extractor.py**
  - Parses LLM response to extract transactions (amount, category, date, description)
  - Fixed: no longer cross-contaminates categories across multi-transaction messages
  - Matches category against LLM's per-transaction guess, longest-keyword-wins

- **app/ai/intent_detector.py**
  - Classifies user message intent (add income/expense, ask question, ask for report, etc.)

- **app/ai/parser.py**
  - Date parsing with support for "N days ago", "yesterday", "last week", weekday names, explicit dates
  - Fixed: now handles "day before yesterday", "last <weekday>" patterns

- **app/ai/response.py**
  - QA prompt handler for non-transaction questions
  - Formats answers as bulleted lists (frontend `Bubble` component renders as `<ul>`)

- **app/ai/prompts.py**
  - Centralized prompt templates for transaction extraction, QA, and intent detection

### Services

- **app/services/finance.py**
  - `create_transaction_from_chat()` — Parses LLM response and creates income/expense
  - `correct_transaction_via_chat()` — Handles correction workflow through chat

- **app/services/recurring.py**
  - `auto_post_recurring()` — Daily background job (triggered by scheduled task or manually)
  - Uses idempotency keys (`source_transaction_id` + `posting_date`) to prevent duplicate posts

- **app/services/analytics.py**
  - `get_dashboard_data()` — Assembles balance, month summary, timeline, and smart suggestions
  - `get_smart_suggestion()` — Low-balance alerts, top spending categories, savings recommendations
  - Separated from finance.py since it's read-only aggregation

- **app/services/export.py**
  - `export_csv()`, `export_excel()`, `export_pdf()`
  - Exports full transaction timeline per user (scoped by `user_id`)
  - Files written to `exports/{csv,excel,pdf}/` with timestamp and user_id in filename

- **app/services/sync.py**
  - `reconcile_offline_queue()` — Merges browser IndexedDB transactions into database
  - Deduplicates by (user_id, type, amount, category, date, description)
  - Conflict resolution: last-write-wins by client timestamp
  - Fully scoped by `user_id` — one user's queue cannot touch another's account

- **app/services/currency.py**
  - Live exchange-rate lookups (1-hour TTL cache)
  - `convert_amount()`, `format_amount()` for display
  - Database keeps single base currency (INR); user display preference is applied at read/write boundaries

- **app/services/backup.py**
  - Full database export/import helpers
  - Only functional when `DATABASE_URL` is blank (local SQLite mode)

- **app/services/notifications.py**
  - `check_low_balance_alert()` — Compares balance to user's alert threshold
  - Currently called by analytics (future: could wire into separate notification route)

## Frontend architecture

The React app lives in `frontend/src/App.jsx`:

- **Session**: Signed cookie (`stash_session`) managed by FastAPI SessionMiddleware
- **Auth**: POST to `/login` or `/logout` (HTML form submission); cookie auto-validated on every request
- **API calls**: `apiFetch()` wrapper adds cookie to all requests; 401 response redirects to login
- **State management**: Local React state for session, theme, page data, and UI flags
- **Offline queue**: IndexedDB-backed transaction queue (syncs on reconnect via `POST /api/settings/offline-sync`)
- **Pages**:
  - Dashboard: Balance, monthly summary, smart suggestions, quick add buttons
  - Timeline: Transaction history with edit/delete controls, chat integration
  - Reports: Category breakdowns and daily trend charts
  - Settings: User profile, currency, theme, password change, export/import

### Key UI improvements

- **Chat input**: Auto-growing textarea (was single-line `<input>`), disabled while replying
- **Message input**: Enter sends, Shift+Enter for newline (was single-line form)
- **Typing indicator**: Real bouncing dots (was literal "...")
- **Formatting**: Assistant replies render bullets (`<ul>`) and **bold** properly
- **Offline support**: IndexedDB queue for pending transactions; auto-syncs when online

## Adding custom users

To add private accounts (not in repo), edit:

- `app/database/private_accounts.py`

That file is ignored by git so private credentials stay out of commits.

## Background jobs

- **Pending entry retry loop** (runs in main.py on app startup)
  - Every `PENDING_RETRY_INTERVAL_SECONDS` (default: 300s = 5 min)
  - Polls `pending_entries` table for unprocessed chat messages
  - Retries LLM parsing; if successful, moves to income/expense/categories
  - Survives app restarts (state persisted in database, not memory)

## Error handling and resilience

- **LLM unavailable**: Message queued to `pending_entries`; background retry loop processes later
- **Auth failures**: 401 redirects to login; signed cookie prevents forgery
- **Rate limits**: Detected via response headers; circuit-breaks temporarily, queues to `pending_entries`
- **Multi-provider fallback**: Groq fails → tries OpenRouter → queues to `pending_entries`
- **User_id filtering**: Applied at database query layer (SQLAlchemy `filter_by(user_id=...)`)
- **Offline transactions**: Browser IndexedDB queue survives restarts; syncs on reconnect

## Security model

- **No hardcoded backdoors**: Removed recovery-password hardcoded access (`app/auth/nyx0908.py` is gone)
- **SECRET_KEY enforcement**: App fails to start without `SECRET_KEY` env var (no default)
- **Session signing**: Signed cookies prevent tampering; expires after 30 days
- **Multi-user isolation**: Every query filtered by `user_id` at the ORM layer
- **Password storage**: bcrypt hashing; original never stored; password resets via CLI-only tool
- **HTTPS-only cookies**: Enabled in production (`ENVIRONMENT=production`)

## Deployment notes

- Local development can use SQLite.
- Production is designed for Postgres on Neon.
- The demo instance is hosted at `https://stash-azsp.onrender.com`.

