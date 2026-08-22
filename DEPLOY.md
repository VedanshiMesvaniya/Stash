# Stash — Multi-user Deployment Guide

This guide covers deploying Stash to production with Render (hosting) and Neon (PostgreSQL database).

## What's new in the multi-user update

**Security**
- No hardcoded recovery password, master key, or auth bypass anywhere in the codebase
- `SECRET_KEY` now fails app startup loudly if unset — no silent insecure default
- Password reset is available via a CLI-only tool (`scripts/reset_password.py`) or self-service from Settings
- Multi-user isolation: every transaction table scoped by `user_id` (one family member cannot see another's data)
- Self-registration with email verification: anyone can create an account via a 6-digit code sent through Brevo, confirmed before the account exists; login now accepts either username or email
- Login, the app-lock PIN, and registration codes all lock out after repeated wrong attempts
- Backup restore only accepts known backup filenames (no path traversal) and requires re-entering the account password

**Database**
- Swapped SQLite-only for Postgres-or-SQLite: set `DATABASE_URL` to Neon connection string in production; leave blank locally for SQLite

**LLM resilience**
- Removed Ollama entirely; now calls Groq first, then falls back to OpenRouter if Groq errors/times out/rate-limits
- If BOTH providers are down, messages queue to `pending_entries` table and retry every 5 minutes

**Bug fixes**
- **Category mis-detection**: Fixed cross-message contamination in multi-transaction messages
- **Date parsing**: Added support for "N days ago", "day before yesterday", "last week", "last <weekday>"
- **Chat formatting**: QA answers now render as proper bulleted lists, not plain text
- **Chat charts disappearing on reload**: report replies (the bar chart + table under a chat bubble) are now persisted
  (`chat_messages.report_entries`) instead of living only in React state, so they survive a page refresh

**UI improvements**
- Chat input is now an auto-growing textarea (was single-line `<input>`)
- Typing indicator is real bouncing dots (was literal "...")
- Message formatting: bullets and **bold** render correctly
- Chat send button shows a spinner while a message is processing
- User chat messages can be edited: editing removes that message and its assistant reply
  (`DELETE /api/chat/message/{id}`) and reloads the text into the composer to resend, rather than forking the thread
- Dashboard: removed the "Unspecified" wallet tile and the smart-suggestion insight card; the Recurring card's Edit
  button is now wired up on the dashboard (it deep-links to Settings, which opens the edit form for that item)

## Architecture highlights

- **Multi-user isolation**: `user_id` filtering on every query (database layer, not application)
- **Offline-first**: Browser IndexedDB queue for transactions; auto-syncs on reconnect
- **Pending entry queue**: LLM unavailable → queue to `pending_entries` → background retry job every 5 min
- **Multi-currency**: Live exchange rates; base currency is INR; user can display in USD/GBP/JPY/CNY/KRW/EUR
- **Export**: CSV, Excel, PDF — fully scoped per user

See [ARCHITECTURE.md](ARCHITECTURE.md) for full details.

---

## Environment variables (required for both local and production)

Copy `.env.example` → `.env` locally, or set in Render dashboard for production.

| Variable | Required | Local default | Production | Notes |
|---|---|---|---|---|
| `SECRET_KEY` | **Yes** | — | — | `python -c "import secrets; print(secrets.token_hex(32))"` — no fallback, app refuses to start without it |
| `DATABASE_URL` | No | (SQLite) | **Required** | Leave blank for local SQLite in `data/finance.db`; set to Neon connection string for Postgres |
| `GROQ_API_KEY` | No | — | Recommended | Get from https://console.groq.com/keys; first LLM provider |
| `GROQ_MODEL` | No | `llama-3.1-8b-instant` | — | Groq model name |
| `NVIDIA_API_KEY` | No | — | Recommended | Get from https://build.nvidia.com; second LLM provider (free NIM tier, no card required) |
| `NVIDIA_MODEL` | No | `nvidia/nvidia-nemotron-nano-9b-v2` | — | NVIDIA NIM model name |
| `OPENROUTER_API_KEY` | No | — | Recommended | Get from https://openrouter.ai/keys; third/last-resort LLM provider. Do $10 one-time credit top-up. |
| `OPENROUTER_MODEL` | No | `openrouter/free` | — | OpenRouter model name |
| `ENVIRONMENT` | No | `development` | `production` | Enables HTTPS-only session cookies |
| `PENDING_RETRY_INTERVAL_SECONDS` | No | `300` | `300` | How often to retry queued LLM messages (seconds) |
| `APP_PUBLIC_URL` | No | `http://127.0.0.1:8000` | Your domain | Used in outbound headers |

**Important notes:**
- `SECRET_KEY` is **non-negotiable** — the app will not start without it. Generate a fresh one for each deployment.
- Both Groq and OpenRouter are optional but **strongly recommended**. If both are missing, LLM errors queue to `pending_entries` forever.
- On OpenRouter, do a one-time $10 credit top-up to raise daily cap from 50 to 1,000 requests.
- For local SQLite, leave `DATABASE_URL` blank.
- For production (Neon), set `DATABASE_URL` to your connection string: `postgresql://user:password@host:port/dbname`

## Deploying to production (Render + Neon, both free tier)

### Pre-deployment checklist

1. **Generate a strong SECRET_KEY**:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Copy this value — you'll need it for Render dashboard.

2. **Set up Neon database**:
   - Go to https://neon.tech
   - Create a new project
   - Copy the connection string (format: `postgresql://user:password@host/dbname`)

3. **Set up Groq (optional but recommended)**:
   - Go to https://console.groq.com/keys
   - Create an API key

4. **Set up OpenRouter (optional but recommended)**:
   - Go to https://openrouter.ai/keys
   - Create an API key
   - Do a one-time $10 credit top-up (raises daily cap from 50 to 1,000 requests)

5. **Configure accounts** (optional):
   - Users can self-register via email verification (see the Brevo setup step below) once deployed — no pre-configuration needed for that path.
   - To also pre-seed accounts, edit `app/database/seed.py`'s `PUBLIC_ACCOUNTS` list before first deploy — once accounts exist, use the CLI to change passwords instead:
     ```bash
     python -m scripts.reset_password <username> <new_password>
     ```

6. **Set up Brevo for registration emails** (required if you want self-registration to work):
   - Go to https://app.brevo.com, create a free account, generate an API key under Settings → SMTP & API → API Keys
   - Verify a sender address under Senders & IP → Senders

### Deploy steps

1. **Build frontend**:
   ```bash
   npm install
   npm run build
   ```
   This creates the Vite bundle in `app/static/react/`. Commit the changes.

2. **Create Render web service**:
   - Go to https://render.com → Dashboard → New + → Web Service
   - Connect your GitHub repo
   - Choose branch (e.g., `main`)

3. **Configure build and start commands**:
   - **Build Command**: `npm install && npm run build && pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Publish**: Yes (make it live after build)

4. **Add environment variables in Render dashboard**:
   - Click "Environment" section
   - Add each variable from the table above:
     - `SECRET_KEY` (your generated value)
     - `DATABASE_URL` (your Neon connection string)
     - `GROQ_API_KEY` (if using)
     - `GROQ_MODEL` (if using Groq)
     - `NVIDIA_API_KEY` (if using)
     - `NVIDIA_MODEL` (if using NVIDIA NIM)
     - `OPENROUTER_API_KEY` (if using)
     - `OPENROUTER_MODEL` (if using OpenRouter)
     - `ENVIRONMENT` = `production`
     - `APP_PUBLIC_URL` = your Render URL (e.g., `https://stash.onrender.com`)
     - `BREVO_API_KEY` (if you want self-registration to work)
     - `BREVO_SENDER_EMAIL` (your verified Brevo sender)
     - `BREVO_SENDER_NAME` (optional, defaults to "Stash")

5. **Deploy**:
   - Click "Create Web Service"
   - Render will automatically build and deploy
   - First deployment seeds categories + multi-user accounts
   - Check logs for any errors

6. **Post-deployment**:
   - Visit your Render URL
   - Log in with one of your configured family accounts
   - Test transaction creation, offline sync, exports, etc.

### Multi-user family accounts

Two ways to create accounts:

1. **Self-registration** (recommended for most users): visit the app and use "Don't have an account? Create one" — enter email, username, and password, confirm the 6-digit code sent to that email (via Brevo — see the Brevo setup below), and the account is created automatically.
2. **Pre-seeded accounts**: edit `app/database/seed.py`'s `PUBLIC_ACCOUNTS` list (or the gitignored `app/database/private_accounts.py` for personal ones not meant for the public demo) before first deploy:

```python
PUBLIC_ACCOUNTS = [
    ("guest", "12345", "Guest Demo"),
]
```

**Important**: Edit this BEFORE first deployment. Once accounts exist in the database, updating `seed.py` won't change their passwords. Use the CLI tool instead:

```bash
# Via Render's shell:
python -m scripts.reset_password guest NewPassword123
```

Each account's transactions are completely isolated by `user_id` — no cross-contamination, regardless of which of the two methods above created the account.

### Brevo setup (for self-registration email verification)

Self-registration sends its 6-digit verification code via [Brevo](https://www.brevo.com) (formerly Sendinblue):

1. Create a free Brevo account and go to **Settings → SMTP & API → API Keys** to generate a key
2. Verify a sender address/domain under **Senders & IP → Senders** — Brevo will reject sends from an unverified sender
3. Set these in your `.env` (locally) or Render environment variables (in production):
   - `BREVO_API_KEY` — the key from step 1
   - `BREVO_SENDER_EMAIL` — the verified address from step 2
   - `BREVO_SENDER_NAME` — display name shown to recipients (defaults to "Stash")

Without these set, registration's send-code step returns a clear error instead of silently failing.

### Custom user management (post-deployment)

Use the CLI tool to manage users after deployment:

```bash
# List all users
python -m scripts.manage_users list

# Add a new user
python -m scripts.manage_users add charlie "StrongPass123" "Charlie"

# Delete a user (removes all their data)
python -m scripts.manage_users delete alice

# Reset a password
python -m scripts.reset_password bob NewPass456
```

Run these commands via Render's shell or SSH into your container.

## Troubleshooting

| Issue | Solution |
|---|---|
| App won't start: "SECRET_KEY env var not set" | Generate one: `python -c "import secrets; print(secrets.token_hex(32))"` and set in Render dashboard |
| LLM requests fail silently | Check that `GROQ_API_KEY`, `NVIDIA_API_KEY`, and `OPENROUTER_API_KEY` are set in Render (only one is strictly required, but all three gives the most resilient fallback chain). Pending messages auto-retry every 5 min. |
| Chat messages stuck in `pending_entries` | Both LLM providers are down. Wait for retry loop (every 5 min) or check API keys. |
| Password reset not working | Use CLI: `python -m scripts.reset_password <username> <new_password>` via Render shell |
| Render cold start is too slow | This is normal on free tier (~30-60s after 15 min idle). Consider Render paid tier for production. |
| Export files not generating | Ensure `exports/` directory exists and has write permissions. Check Render logs for errors. |
| Offline queue not syncing | Browser must have IndexedDB enabled. Check browser DevTools → Application → Storage. |
| Registration "Email sending isn't configured" | Set `BREVO_API_KEY` and `BREVO_SENDER_EMAIL` in your environment (see Brevo setup above). |
| Registration email never arrives | Confirm the sender address is verified in Brevo (Senders & IP → Senders) — unverified senders get silently rejected by some providers, or check spam. |

## Known limits and considerations

- **Render free tier**: Spins down after 15 minutes idle. First request after idle takes ~30-60s (cold start).
- **LLM rate limits**: At ≤10 messages/user/day for 5 family members (50/day total), you're within limits. Bursts may queue to `pending_entries`.
- **Neon free tier**: Includes 3 branches, 50GB storage, and auto-suspend after 1 week idle (data persists).
- **Backup/restore**: Only works with local SQLite. On Neon, use Neon's native branching/point-in-time restore: https://neon.tech/docs/introduction/branching
- **Session duration**: 30 days (configurable). After timeout, user must log in again.
- **Multi-user isolation**: Applied at database query layer (SQLAlchemy ORM); one user cannot see/edit another's data.

## Performance tips

1. **Enable frontend caching**: Vite automatically generates cache-busting hashes; assets are cached long-term.
2. **Batch API requests**: Use timeline pagination (limit=50 default) for large datasets.
3. **Monitor pending_entries**: If queue grows, LLM providers may be overwhelmed; consider increasing `PENDING_RETRY_INTERVAL_SECONDS`.
4. **Use recurring rules**: Auto-posting saves manual entry time for predictable income/expenses.

## Security best practices

1. **Never commit `.env`**: Render dashboard is the only place for secrets.
2. **Rotate SECRET_KEY periodically**: Changes expire all existing sessions (expected).
3. **Monitor family member access**: No admin panel yet; audit via logs if available.
4. **Use strong passwords**: Recommend 12+ characters, mixed case, numbers, symbols.
5. **Enable HTTPS**: Set `ENVIRONMENT=production` in Render for HTTPS-only cookies.
