# Stash

Stash is a FastAPI + React personal wallet for tracking income, expenses, recurring transactions, reports, and AI-assisted transaction logging.

Live demo: https://stash-azsp.onrender.com

## What it does

- AI chat logging for income and expense entries
- Dashboard with balance, monthly totals, and smart suggestions
- Timeline view with edit and delete controls for every entry
- Recurring transactions with auto-posting
- Monthly reports with category charts and daily trend data
- CSV, Excel, and PDF exports
- Backup and restore endpoints
- User settings for currency, theme, alert amount, and salary day
- Signed-cookie sessions for logged-in users
- Multi-user isolation by `user_id` on every transaction table

## Demo login

Use this account to test the deployed demo:

- Username: `guest`
- Password: `12345`

After login, the browser stores the authenticated session in a signed cookie named `stash_session`. The password is not stored in the browser.

## Private users

Personal or family accounts belong in:

- `app/database/private_accounts.py`

That file is gitignored on purpose so you can keep your own usernames and passwords out of the repo.

## Fresh clone setup

1. Clone the repo.
2. Create a virtual environment and install backend dependencies.
3. Copy `.env.example` to `.env`.
4. Fill in the environment values listed below.
5. Run `npm install` and `npm run build`.
6. Start the backend with `uvicorn app.main:app --reload`.

## Environment

```bash
SECRET_KEY=...
DATABASE_URL=
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
OPENROUTER_API_KEY=
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
ENVIRONMENT=development
PENDING_RETRY_INTERVAL_SECONDS=300
APP_PUBLIC_URL=http://127.0.0.1:8000
```

What each variable does:

- `SECRET_KEY` is required. The app will not start without it because it signs the login cookie.
- `DATABASE_URL` is optional locally. Leave it blank to use SQLite in `data/finance.db`. Set it to your Neon/Postgres URL in production.
- `GROQ_API_KEY` and `OPENROUTER_API_KEY` enable AI parsing. If both are empty, messages go into the retry queue and can be processed later.
- `GROQ_MODEL` and `OPENROUTER_MODEL` control the model names used by the backend.
- `ENVIRONMENT=production` enables HTTPS-only cookies.
- `PENDING_RETRY_INTERVAL_SECONDS` controls how often the background retry loop runs.
- `APP_PUBLIC_URL` is used in outbound headers and can stay at the local default during development.

Local setup command sequence:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# fill in SECRET_KEY first, then any LLM keys and DATABASE_URL if needed

npm install
npm run build

uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/login` and sign in with the demo account or one of your private accounts.

## Feature list

### Authentication

- Username + password login
- Signed-cookie session handling
- No self-signup flow
- Password changes require the current password

### Transactions

- Add income and expense entries through chat
- Correct an existing entry through chat
- Edit any transaction from the timeline
- Delete any transaction from the timeline
- Transaction history is always filtered by the logged-in user

### Reports and analytics

- Monthly income, expense, and savings summary
- Category breakdown charts
- Daily trend chart
- Largest expense highlight
- Smart dashboard suggestion

### Recurring and sync

- Recurring income and expense rules
- Auto-posting when a recurring date becomes due
- Offline queue reconciliation
- Pending-entry retry loop when the LLM is unavailable

### Export and backup

- CSV export
- Excel export
- PDF export
- Backup creation
- Backup restore

### UI

- Dark and light themes
- Responsive desktop and mobile layout
- Timeline, reports, chat, and settings pages

## Project layout

```text
app/
  main.py              FastAPI entry point
  ai/                  LLM, parsing, extraction, and response helpers
  api/                 Auth, finance, recurring, reports, and settings routes
  auth/                Password hashing and session helpers
  database/            Models, CRUD, seed loader, and local private accounts
  services/            Business logic for finance, recurring, reports, sync, backup, export
frontend/
  src/                 React app and styles
scripts/
  reset_password.py    CLI password reset helper
  manage_users.py      CLI add/delete/list helper for users
```

## Architecture 

See project architecture in `ARCHITECTURE.md` for understand how project works

## User management

Use the console helper to manage users on your own machine:

```bash
python -m scripts.manage_users list
python -m scripts.manage_users add alice MyStrongPassword "Alice"
python -m scripts.manage_users delete alice
```

- `add` creates the DB user and updates `app/database/private_accounts.py` if it exists.
- `delete` removes the DB user and deletes all of that user's transactions, chats, recurring rules, pending items, and private account entry.
- If you only need a password reset for an existing user, use `python -m scripts.reset_password <username> <new_password>`.

## Deployment

See `DEPLOY.md` for environment variables, build steps, and Render/Neon deployment notes.
