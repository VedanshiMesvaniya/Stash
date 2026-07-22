# Stash — Multi-user Deployment Guide

This guide covers deploying Stash to production with Render (hosting) and Neon (PostgreSQL database).

## What's new in the multi-user update

**Security**
- Removed hardcoded recovery-password backdoor (`app/auth/nyx0908.py` is gone)
- `SECRET_KEY` now fails app startup loudly if unset — no silent insecure default
- Password reset is now a CLI-only tool (`scripts/reset_password.py`), not a network endpoint
- Multi-user isolation: every transaction table scoped by `user_id` (one family member cannot see another's data)

**Database**
- Swapped SQLite-only for Postgres-or-SQLite: set `DATABASE_URL` to Neon connection string in production; leave blank locally for SQLite

**LLM resilience**
- Removed Ollama entirely; now calls Groq first, then falls back to OpenRouter if Groq errors/times out/rate-limits
- If BOTH providers are down, messages queue to `pending_entries` table and retry every 5 minutes

**Bug fixes**
- **Category mis-detection**: Fixed cross-message contamination in multi-transaction messages
- **Date parsing**: Added support for "N days ago", "day before yesterday", "last week", "last <weekday>"
- **Chat formatting**: QA answers now render as proper bulleted lists, not plain text

**UI improvements**
- Chat input is now an auto-growing textarea (was single-line `<input>`)
- Typing indicator is real bouncing dots (was literal "...")
- Message formatting: bullets and **bold** render correctly

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
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | — | Groq model name |
| `OPENROUTER_API_KEY` | No | — | Recommended | Get from https://openrouter.ai/keys; fallback LLM provider. Do $10 one-time credit top-up. |
| `OPENROUTER_MODEL` | No | `meta-llama/llama-3.3-70b-instruct:free` | — | OpenRouter model name |
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

5. **Configure multi-user accounts** (optional):
   - Edit `app/database/seed.py` to customize family usernames/passwords
   - This is your only chance before first deploy — once accounts exist, use CLI to change passwords:
     ```bash
     python -m scripts.reset_password <username> <new_password>
     ```

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
     - `OPENROUTER_API_KEY` (if using)
     - `OPENROUTER_MODEL` (if using OpenRouter)
     - `ENVIRONMENT` = `production`
     - `APP_PUBLIC_URL` = your Render URL (e.g., `https://stash.onrender.com`)

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

By default, Stash seeds 5 family accounts on first deploy from `app/database/seed.py`:

```python
FAMILY_ACCOUNTS = [
    {"username": "alice", "password": "alice_password_here", "name": "Alice"},
    {"username": "bob", "password": "bob_password_here", "name": "Bob"},
    # ... more accounts
]
```

**Important**: Edit this BEFORE first deployment. Once accounts exist in the database, updating `seed.py` won't change their passwords. Use the CLI tool instead:

```bash
# Via Render's shell:
python -m scripts.reset_password alice NewPassword123
```

Each family member's transactions are completely isolated by `user_id` — no cross-contamination.

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
| LLM requests fail silently | Check that both `GROQ_API_KEY` and `OPENROUTER_API_KEY` are set in Render. Pending messages auto-retry every 5 min. |
| Chat messages stuck in `pending_entries` | Both LLM providers are down. Wait for retry loop (every 5 min) or check API keys. |
| Password reset not working | Use CLI: `python -m scripts.reset_password <username> <new_password>` via Render shell |
| Render cold start is too slow | This is normal on free tier (~30-60s after 15 min idle). Consider Render paid tier for production. |
| Export files not generating | Ensure `exports/` directory exists and has write permissions. Check Render logs for errors. |
| Offline queue not syncing | Browser must have IndexedDB enabled. Check browser DevTools → Application → Storage. |

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
