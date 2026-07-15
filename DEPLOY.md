# Stash — multi-user update, deployment guide

## What changed (summary)

**Security**
- Removed the hardcoded recovery-password backdoor (`app/auth/nyx0908.py` is gone).
- `SECRET_KEY` now fails app startup loudly if unset — no silent insecure default.
- Password reset is now a CLI-only tool (`scripts/reset_password.py`), not a network endpoint.

**Multi-user**
- New `User` table. Every transaction table (`Income`, `Expense`, `RecurringTransaction`,
  `RecurringPosting`, `ChatMessage`, `PendingEntry`) is scoped by `user_id`. One family
  member can never see or edit another's data.
- 5 static accounts are seeded automatically on first startup — see `app/database/seed.py`
  to change usernames/passwords (`FAMILY_ACCOUNTS` list at the top of that file).
- No self-signup. You hand out username + password; there's no "create account" screen.

**Database**
- Swapped SQLite-only for Postgres-or-SQLite: set `DATABASE_URL` to your Neon connection
  string in production; leave it blank locally to keep using SQLite.

**LLM**
- Removed Ollama entirely. `app/ai/llm.py` now calls Groq (`llama-3.3-70b-versatile`) first,
  and falls back to OpenRouter (`meta-llama/llama-3.3-70b-instruct:free`) if Groq errors,
  times out, or rate-limits.
- If BOTH providers are down, the chat message is saved to a `pending_entries` table
  (not memory — survives restarts) and a background job retries it every 5 minutes
  (`PENDING_RETRY_INTERVAL_SECONDS` in `.env`).

**Bug fixes**
- **Category mis-detection**: the old code fell back to scanning the ENTIRE chat message
  for keyword hints when the LLM's category guess didn't exactly match, which meant one
  transaction's category could get contaminated by words elsewhere in a multi-transaction
  message. Fixed in `app/ai/extractor.py` — matching now happens against the LLM's own
  per-transaction guess, longest-keyword-wins, never the full raw message.
- **"2 days ago" not detected**: the date parser only understood `today`/`yesterday`/weekday
  names/explicit dates. Added regex handling for "N days ago/back", "day before yesterday",
  "last week", and "last <weekday>" in `resolve_date_hint()`.
- **One-line list answers**: the QA prompt only said "keep answers short," so the model
  never produced real lists. `QA_SYSTEM_PROMPT` now explicitly requires a line-separated
  bulleted list for any multi-item answer, and the frontend's `Bubble` component renders
  those bullets as an actual `<ul>`, not just a wall of text.

**Chat UI**
- Input is now an auto-growing textarea (was a single-line `<input>`), disabled while
  Stash is replying, Enter sends / Shift+Enter for a newline.
- Real typing indicator (bouncing dots) instead of a literal "..." bubble.
- Assistant replies render bullets and **bold** properly instead of raw text.

---

## Environment variables (copy `.env.example` → `.env` locally, or set in Render dashboard)

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | Yes | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Prod only | Neon connection string. Blank = local SQLite. |
| `GROQ_API_KEY` | Yes | https://console.groq.com/keys |
| `OPENROUTER_API_KEY` | Yes | https://openrouter.ai/keys (do the $10 one-time top-up to raise the daily cap) |
| `ENVIRONMENT` | Prod: `production` | Enables HTTPS-only session cookies |

## Deploying (Render + Neon, both free)

1. **Neon**: create a project at neon.tech, copy the connection string into `DATABASE_URL`.
2. **Groq**: create a key at console.groq.com, put it in `GROQ_API_KEY`.
3. **OpenRouter**: create a key at openrouter.ai, put it in `OPENROUTER_API_KEY`. Do the
   one-time $10 credit top-up so your daily cap is 1,000 requests instead of 50.
4. **Render**: New → Web Service → connect this repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Add all the env vars above in the Render dashboard (never commit `.env`).
5. First deploy will seed categories + the 5 accounts automatically (`app/database/seed.py`).
6. Edit usernames/passwords in `seed.py` BEFORE first deploy — once an account exists,
   changing this file won't update its password. Use `python -m scripts.reset_password
   <username> <new_password>` via Render's shell for that instead.
7. Frontend build: `cd frontend && npm install && npm run build` — copy the build output
   into `app/static/react/` (already wired up in `main.py`'s `_frontend_response`).

## Known limits, stated plainly

- Render's free tier spins down after 15 minutes idle — expect a ~30-60s cold start on
  the first request after inactivity.
- Groq/OpenRouter free tiers are rate-limited. At ≤10 messages/user/day for 5 users
  (50/day total), you're well within both providers' limits, but bursts of retries or
  testing can still occasionally trip a limit — that's what the `pending_entries` queue
  and background retry job are for.
- `backups/`, local SQLite file-copy backup/restore only works when `DATABASE_URL` is
  unset (local SQLite mode). On Neon, use Neon's own branching/point-in-time restore
  instead: https://neon.tech/docs/introduction/branching
