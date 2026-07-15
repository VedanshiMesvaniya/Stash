# Stash — AI Personal Wallet (multi-user, cloud edition)

A FastAPI + React finance tracker you talk to in plain language ("Salary 35000",
"Tea 20", "petrol was actually 600") instead of filling out forms.

> This is the multi-user, cloud-LLM version of Stash. It replaced the original
> single-user, local-Ollama build. See `DEPLOY.md` for the full list of what
> changed and why, plus step-by-step deployment instructions.

## Stack

- **Backend**: FastAPI, SQLAlchemy, Postgres (Neon) in production / SQLite locally
- **AI**: Groq (`llama-3.3-70b-versatile`) primary, OpenRouter
  (`meta-llama/llama-3.3-70b-instruct:free`) fallback — no local model, no GPU needed
- **Frontend**: React + Vite, built into `app/static/react/` and served by FastAPI
- **Auth**: username + password per person, sessions via signed cookies. No self-signup —
  accounts are pre-created in `app/database/seed.py`.

## Quick start (local dev)

```bash
python -m venv venv
venv\Scripts\activate        # or: source venv/bin/activate on Mac/Linux
pip install -r requirements.txt

cp .env.example .env
# edit .env: set SECRET_KEY, GROQ_API_KEY, OPENROUTER_API_KEY
# leave DATABASE_URL blank to use local SQLite

npm install
npm run build                # builds React into app/static/react/

uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/login and sign in with one of the accounts defined in
`app/database/seed.py` (`FAMILY_ACCOUNTS` list — edit usernames/passwords there
before your first run).

On Windows, `start.bat` does all of the above in one double-click (after you've
copied `.env.example` to `.env` and filled in the keys once).

## Deploying for real (Render + Neon, both free)

See `DEPLOY.md` — covers environment variables, the Neon/Groq/OpenRouter signup
steps, the Render build/start commands, and the known limits of free-tier hosting
(cold starts, rate limits) stated plainly.

## Project layout

```
app/
  main.py              FastAPI app, session middleware, background pending-retry job
  ai/
    llm.py              Groq + OpenRouter client with automatic fallback
    extractor.py         Turns a chat message into structured transaction(s)
    intent_detector.py   Classifies chat intent (transaction/correction/question/report/chat)
    parser.py            Orchestrates the above; queues to pending_entries if both LLMs are down
    prompts.py            All system prompts in one place
    response.py           Q&A answers + dashboard suggestions
  api/                 FastAPI routers (auth, finance/chat, recurring, reports, settings)
  auth/                Login, session, password hashing (no backdoor, no self-signup)
  database/
    models.py            User, Income, Expense, Category, ChatMessage,
                          RecurringTransaction/Posting, PendingEntry
    crud.py              All DB reads/writes, every query scoped by user_id
    seed.py              Seeds default categories + the 5 family accounts
    migrations.py         Lightweight in-place schema upgrader (no Alembic)
  services/            Business logic: finance, recurring, reports, analytics, export, backup, sync
scripts/
  reset_password.py    CLI-only password reset (replaces the old network backdoor)
frontend/
  src/App.jsx           The whole React app (single file, by design - see comments inline)
```

## A few things worth knowing

- **No balance is ever stored.** It's always `SUM(income) - SUM(expense)`, computed at
  query time, so it can't drift out of sync with the actual transaction history.
- **Categories/sources are validated against a fixed list** by the LLM extraction prompt,
  with keyword-based fallback matching scoped to each individual transaction (not the
  whole chat message) to avoid one transaction's category bleeding into another's.
- **If both Groq and OpenRouter are down or rate-limited**, your message isn't lost — it's
  saved to a `pending_entries` table and a background job retries it every 5 minutes
  (configurable via `PENDING_RETRY_INTERVAL_SECONDS`).
- **Correction messages** ("petrol was actually 600") search recent transactions and, if
  more than one could match, ask you to pick rather than silently guessing.
