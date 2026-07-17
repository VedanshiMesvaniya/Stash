# Architecture

## Overview

Stash is a two-part web app:

- `FastAPI` serves the backend API, authentication, and static frontend build.
- `React` handles the user interface in the browser.

The backend owns all persistence, auth, transaction logic, and scheduled work. The frontend only calls the API and renders responses.

## Request flow

1. The user signs in with a username and password.
2. The backend verifies the password hash and creates a signed session cookie.
3. Every authenticated API request uses that cookie to resolve the current `user_id`.
4. CRUD queries always filter by `user_id`, so one account cannot read another account's data.

## Data model

Main tables:

- `users`
- `income`
- `expense`
- `categories`
- `chat_messages`
- `recurring_transactions`
- `recurring_postings`
- `pending_entries`

Notes:

- Income and expense are stored separately.
- Balance is never stored. It is derived as `SUM(income) - SUM(expense)`.
- Recurring postings keep auto-generated transactions idempotent.
- `pending_entries` holds chat messages that could not be processed immediately.

## Backend modules

- `app/main.py`
  - Starts the app
  - Runs migrations and seed loading
  - Mounts the React build
  - Starts the pending-entry retry loop

- `app/api/auth.py`
  - Login, logout, session state, lock settings

- `app/api/finance.py`
  - Chat entry point
  - Timeline data
  - Transaction update/delete
  - Correction confirmation
  - Dashboard data

- `app/api/recurring.py`
  - Recurring transaction CRUD and sync

- `app/api/reports.py`
  - Monthly report data and month picker

- `app/api/settings.py`
  - User settings
  - Password and username updates
  - Backup and restore
  - Offline queue reconciliation

- `app/database/seed.py`
  - Seeds categories
  - Seeds the public demo login
  - Loads local-only accounts from the gitignored `private_accounts.py`

- `app/database/crud.py`
  - Thin database access helpers
  - All reads and writes are scoped by `user_id`

- `app/services/finance.py`
  - Transaction creation and correction logic

- `app/services/recurring.py`
  - Recurring schedule logic and auto-posting

- `app/services/analytics.py`
  - Dashboard summaries and smart suggestions

## Frontend flow

The React app lives in `frontend/src/App.jsx` and uses:

- `apiFetch` for authenticated requests
- local state for session, theme, and page data
- the timeline page for edit/delete actions
- dashboard and reports pages for read-only views

The browser stores the logged-in session in a signed cookie plus a small local cache for UI state. It does not store the raw password.

## Manual users

If you want to add private accounts, edit:

- `app/database/private_accounts.py`

That file is ignored by git so private credentials stay out of commits.

## Deployment notes

- Local development can use SQLite.
- Production is designed for Postgres on Neon.
- The demo instance is hosted at `https://stash-azsp.onrender.com`.

