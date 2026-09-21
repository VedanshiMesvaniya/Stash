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

One user can never see, edit, or export another user's data. Accounts come from two places: family/demo accounts seeded at startup via `app/database/seed.py` (static username/password), and self-registered accounts created via `/api/auth/register/send-code` + `/register/verify-code`, which require confirming a 6-digit code emailed via Gmail SMTP before the account is actually created. Login accepts either a username or an email.

## Data model

Main tables:

- **users**: Login credentials, preferences (currency, alert threshold, salary day), theme
- **income**: Amount, source, date, description, user_id
- **expense**: Amount, category, date, description, user_id
- **categories**: Auto-seeded category list per user (income sources vs. expense categories)
- **chat_messages**: Timestamp, user message, assistant response, user_id
- **recurring_transactions**: Frequency, amount, label, enabled flag, user_id
- **recurring_postings**: Idempotency marker (source_transaction_id + posting_date) to prevent duplicate auto-posts
- **user_glossary**: Terms this user explicitly taught Stash ("kalakand → Snacks"), unique per (user_id, transaction_type, term); outranks the built-in glossary for that user only
- **pending_entries**: Chat messages queued when both LLM providers are down/rate-limited (survives restarts)

Notes:

- Income and expense are stored separately for reporting clarity
- Balance is derived on-the-fly as `SUM(income) - SUM(expense)` filtered by user_id
- Recurring postings include an idempotency key so auto-posting can restart safely
- `pending_entries` includes retry count and last-attempted timestamp
- `pending_selections` (one row per user) also carries `kind = "categorize"` while Stash is waiting for the answer to "which category is this item?" (expires after 24 h)

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
  - POST `/api/chat` — Send a message for AI-assisted entry parsing; assistant replies that include a report
    (category breakdown) persist that data to `chat_messages.report_entries` so the chart survives a page reload
  - GET `/api/chat/history` — Chat transcript, including `reportEntries` per message where present
  - DELETE `/api/chat/message/{id}` — Removes a user message and its paired assistant reply, for edit-and-resend
    (the message is deleted and resent fresh rather than the thread forking into two versions)
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
  - POST `/api/backup`, POST `/api/backup/restore` — Backup/restore (SQLite only; restore requires re-entering the account password and only accepts known backup filenames)

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
  - Calls Groq (`openai/gpt-oss-120b`) first
  - Falls back to NVIDIA NIM (`nvidia/nvidia-nemotron-nano-9b-v2`) if Groq fails/times out/rate-limits
  - Falls back to OpenRouter (`openrouter/free`) if NVIDIA also fails
  - If all three are down, raises `LLMUnavailableError` — caller queues to `pending_entries`
  - In-memory rate-limit tracking to detect backoff signals

- **app/ai/extractor.py**
  - Parses LLM response to extract transactions (amount, category, date, description)
  - Fixed: no longer cross-contaminates categories across multi-transaction messages
  - Category resolution order for each transaction: product glossary (only when it has one clear best match for that description) → the LLM's own category if valid → hint tables (`EXPENSE_CATEGORY_HINTS`) → `Other`
  - `explain_category()` reports `glossary_match` when the glossary decided the category

- **app/ai/intent_detector.py**
  - Classifies user message intent (add income/expense, ask question, ask for report, etc.)

- **app/ai/parser.py**
  - Chat orchestration (`handle_message`): checks for a pending question first (delete-selection or category question), then intent detection → extraction/correction/delete/QA
  - After creating transactions it appends the "which category is this item?" question when `create_transactions` flagged an unknown item (skipped when a clarification question is already going out)
  - Date resolution lives in `extractor.resolve_date_hint()` ("N days ago", "yesterday", "last <weekday>", explicit dates)

- **app/ai/response.py**
  - QA prompt handler for non-transaction questions
  - Formats answers as bulleted lists (frontend `Bubble` component renders as `<ul>`)

- **app/ai/prompts.py**
  - Centralized prompt templates for transaction extraction, QA, and intent detection

### Product glossary (`app/glossary/`)

A data-driven "what category is this item?" lookup, independent of the LLM.

- **`data/{expense,income}/*.json`** — one file per category, terms grouped by theme (dairy, vegetables, street_snacks, telecom_internet_tv, native_script ...). ~6,000 terms; format and conventions in `data/README.md`. Validated by `scripts/validate_glossary.py` (run in CI).
- **`engine.py`** — pure Python, no DB/LLM dependency. Text is tokenised (lower-case, accents stripped, Devanagari/Gujarati combining marks preserved), matched on whole words, **leftmost-longest** (`milk tea` beats `milk`). If two *different* categories tie for the longest match (`apple airpods`) it returns no answer and the caller falls back to the LLM. Plural/singular forms of a term's last word are generated at load time. A broken data file is logged and skipped; lookups never raise, so a glossary problem degrades to "no opinion" instead of breaking chat. Loaded once (~60 ms), lookups ≈ 20 µs.
- **Precedence when a transaction is created:** the user's own taught term (`user_glossary`) → built-in glossary → LLM category → learned habits (`merchant_memory`, only for `Other`) → `Other`.

**Ask-and-remember flow** (`app/services/category_learning.py`), expenses only:

```
message ──> LLM extraction ──> resolve category (glossary first)
                                   │
              known item ──────────┴──> saved with that category
              unknown item (no glossary hit, LLM said Other, 1-3 word description)
                    │
                    ├─> saved as "Other" (balance stays correct)
                    └─> reply also asks "which category is <item>?"  + pending_selections(kind=categorize)

next message ──> parser.handle_message checks the pending question BEFORE intent detection
                    ├─ contains a number / isn't short  -> treated as a new message, question dropped
                    ├─ "skip" / "don't know"            -> stays Other, nothing learned
                    └─ category name or glossary word   -> entry moved, term saved to user_glossary
```

Several unknown items in one message are asked one at a time; two unreadable replies in a row leave the item as `Other`.

### Services

- **app/services/category_learning.py**
  - `find_taught_category()`, `unknown_term_for()`, `ask_about_unknown_terms()`, `handle_answer()` — the loop above; imports `crud` + `glossary` only (finance calls into it, not the other way round)

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
  - Category/source and description cells are sanitized against CSV/Excel formula injection (CWE-1236): any value starting with `=`, `+`, `-`, `@`, tab, or CR is prefixed with a leading apostrophe before being written, so spreadsheet apps render it as text instead of evaluating it as a formula

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
- **State management**: Local React state for session, page data, and UI flags
- **Offline queue**: IndexedDB-backed transaction queue (syncs on reconnect via `POST /api/settings/offline-sync`)
- **Pages**:
  - Dashboard: Balance + this-month income/expense progress, quick-action shortcuts, a 2x2 metric block (income, expense, savings, most-used category), recent timeline, recurring, and a live embedded chat panel (desktop)
  - Chat: Full conversational transaction logging, also embedded compact on the dashboard
  - Timeline: Transaction history with edit/delete controls, chat integration
  - Reports: Category breakdowns and daily trend charts
  - Settings: User profile, currency, password change, export/import

### Design system — "Glass"

- One design, no light/dark toggle. Monochrome white-glass cards and a charcoal sidebar, with a single burnt-orange accent (`--primary: #dc6743`), colors sampled from the reference mockups.
- `.card` uses `backdrop-filter: blur()` plus translucent white over a soft gradient page background for the glass effect.
- The sidebar and mobile bottom nav are always dark charcoal (`--sidebar-bg`), independent of the surface tokens, with a rounded orange active-icon pill.
- `frontend/src/styles.css` defines every color as a single CSS variable set in `:root` (no more `[data-theme='obsidian']` / `[data-theme='mist']` blocks) — retheming means editing variables, not duplicating rules.
- The user's `settings.theme` field still round-trips through `/api/settings` for backward compatibility, but no UI reads it anymore.
- `ChatPage` takes a `compact` prop: full-page mode keeps the fixed composer and page-level scroll; compact mode (used in the dashboard's embedded panel) scrolls its own container and lays out the composer inline. Both share the same send/candidate-confirmation logic.

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
  - Retries LLM parsing; if successful, creates the income/expense rows (same category resolution as chat, incl. the product glossary) and applies cash withdrawals as wallet transfers rather than expenses
  - Runs without a user present, so it never asks clarification or category questions: anything unclear is logged, and only what was clearly extracted is saved
  - Survives app restarts (state persisted in database, not memory)

## Error handling and resilience

- **LLM unavailable**: Message queued to `pending_entries`; background retry loop processes later
- **Auth failures**: 401 redirects to login; signed cookie prevents forgery
- **Rate limits**: Detected via response headers; circuit-breaks temporarily, queues to `pending_entries`
- **Multi-provider fallback**: Groq fails → tries NVIDIA NIM → tries OpenRouter → queues to `pending_entries`
- **User_id filtering**: Applied at database query layer (SQLAlchemy `filter_by(user_id=...)`)
- **Offline transactions**: Browser IndexedDB queue survives restarts; syncs on reconnect

## Security model

- **No hardcoded backdoors**: No recovery password, master key, or bypass exists anywhere in the auth code path
- **SECRET_KEY enforcement**: App fails to start without `SECRET_KEY` env var (no default)
- **Session signing**: Signed cookies prevent tampering; expires after 30 days
- **Multi-user isolation**: Every query filtered by `user_id` at the ORM layer
- **Password storage**: bcrypt hashing; original never stored; password resets via CLI-only tool or Settings (self-service, requires the current password)
- **Brute-force lockout**: Login, the app-lock PIN, and registration verification codes each lock out after repeated wrong attempts (see `app/auth/auth.py`, `app/api/auth.py`, `app/auth/registration.py`)
- **HTTPS-only cookies**: Enabled in production (`ENVIRONMENT=production`)
- **Self-registration with email verification**: `/api/auth/register/send-code` + `/register/verify-code` let anyone create an account, but nothing is written to the `users` table until they prove control of the email address via a 6-digit code (bcrypt-hashed at rest, 10-minute expiry, 60s resend cooldown, 5-attempt lockout) sent via Gmail SMTP - see `app/auth/registration.py` and `app/services/email_service.py`. This is a deliberate move away from invite-only seeding for new accounts; seeded family/demo accounts from `seed.py` still work unchanged.
- **Backup/restore hardening**: `POST /api/backup/restore` only accepts filenames already known to the backup listing (rejects path traversal) and requires re-entering the account password, since it overwrites the single shared database for every user.

## Deployment notes

- Local development can use SQLite.
- Production is designed for Postgres on Neon.
- The demo instance is hosted at `https://stash-azsp.onrender.com`.
- CI runs on GitHub Actions (`.github/workflows/ci.yml`) on every push/PR to `main` and `feature/add_new`; it validates the app but does not deploy — Render's own GitHub integration handles that separately. See the CI/CD section in [README.md](README.md) for what the two jobs (`backend`, `frontend`) actually check.

