import React, { useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, dayLabel, fromDateInput, money, toDateInput } from './api';
import SplashScreen from './components/ui/SplashScreen';
import ThemeToggle from './components/ui/ThemeToggle';
import SectionHeader from './components/ui/SectionHeader';
import MetricCard from './components/ui/MetricCard';
import TimelineItem from './components/ui/TimelineItem';
import RecurringCard from './components/ui/RecurringCard';
import { PieViz, BarViz, LineViz } from './components/charts/Charts';

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: 'space_dashboard' },
  { path: '/chat', label: 'Chat', icon: 'auto_awesome' },
  { path: '/timeline', label: 'Timeline', icon: 'receipt_long' },
  { path: '/reports', label: 'Reports', icon: 'query_stats' },
  { path: '/settings', label: 'Settings', icon: 'tune' },
];

const AUTH_ROUTES = new Set(['/login']);
const LOGO_SRC = '/static/icons/mark.png';
const DASHBOARD_CACHE_KEY = 'stash_dashboard_cache';
const RECURRING_CACHE_KEY = 'stash_recurring_cache';
const STASH_STORAGE_KEYS = [
  'stash_dashboard_cache',
  'stash_recurring_cache',
  'stash_session_cache',
  'stash_theme',
];

const emptySession = {
  authenticated: false,
  first_run: false,
  settings: {
    theme: 'mist',
    currency: 'INR',
  },
};

const THEME_OPTIONS = [
  { key: 'obsidian', label: 'Dark', swatch: '#151313' },
  { key: 'mist', label: 'Light', swatch: '#fcf9f8' },
];

const CURRENCY_OPTIONS = [
  { key: 'INR', label: 'India (INR)' },
  { key: 'USD', label: 'United States (USD)' },
  { key: 'GBP', label: 'United Kingdom (GBP)' },
  { key: 'JPY', label: 'Japan (JPY)' },
  { key: 'CNY', label: 'China (CNY)' },
  { key: 'KRW', label: 'Korea (KRW)' },
];

function isAuthRoute(pathname) {
  return AUTH_ROUTES.has(pathname);
}

function navigate(pathname, replace = false) {
  if (replace) window.history.replaceState({}, '', pathname);
  else window.history.pushState({}, '', pathname);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function readJsonCache(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJsonCache(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore storage errors and keep rendering the live data.
  }
}

function clearStashStorage() {
  try {
    STASH_STORAGE_KEYS.forEach((key) => localStorage.removeItem(key));
  } catch {
    // Ignore storage cleanup errors.
  }
}

function useRoute() {
  const [route, setRoute] = useState(window.location.pathname);
  useEffect(() => {
    const onPop = () => setRoute(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  return [route, navigate];
}

function useSession() {
  const [session, setSession] = useState(() => {
    try {
      const cached = localStorage.getItem('stash_session_cache');
      return cached ? JSON.parse(cached) : emptySession;
    } catch {
      return emptySession;
    }
  });
  const [loading, setLoading] = useState(false);

  const reload = async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    try {
      const data = await apiFetch('/api/auth/session', { method: 'GET', headers: {} });
      const nextSession = data || emptySession;
      setSession(nextSession);
      localStorage.setItem('stash_session_cache', JSON.stringify(nextSession));
      return data;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload({ silent: true }).catch(() => {
      setSession(emptySession);
      localStorage.removeItem('stash_session_cache');
      setLoading(false);
    });
  }, []);

  return [session || emptySession, loading, reload, setSession];
}

function useTheme(session) {
  const initial = localStorage.getItem('stash_theme') || session?.settings?.theme || 'mist';
  const [theme, setTheme] = useState(normalizeTheme(initial));

  useEffect(() => {
    const nextTheme = session?.settings?.theme || localStorage.getItem('stash_theme') || 'mist';
    setTheme(normalizeTheme(nextTheme));
  }, [session?.settings?.theme]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('stash_theme', theme);
  }, [theme]);

  return [theme, setTheme];
}

const LIGHT_THEME_ALIASES = new Set(['light', 'mist', 'lavender']);

function normalizeTheme(value) {
  if (!value) return 'mist';
  return LIGHT_THEME_ALIASES.has(value) ? 'mist' : 'obsidian';
}

function ThemedDropdown({ value, options, onChange, label, triggerClassName = '' }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onPointerDown = (event) => {
      if (ref.current && !ref.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  const active = options.find((option) => option.value === value) || options[0];

  return (
    <div className="themed-dropdown" ref={ref}>
      <button
        type="button"
        className={`themed-dropdown-trigger ${open ? 'open' : ''} ${triggerClassName}`.trim()}
        onClick={() => setOpen((next) => !next)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="themed-dropdown-label">{active?.label || label}</span>
        <span className="themed-dropdown-value">{active?.value || value}</span>
        <span className="themed-dropdown-caret">⌄</span>
      </button>
      {open ? (
        <div className="themed-dropdown-menu" role="listbox" aria-label={label}>
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`themed-dropdown-option ${value === option.value ? 'active' : ''}`}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              role="option"
              aria-selected={value === option.value}
            >
              <span>{option.label}</span>
              <span className="themed-dropdown-option-value">{option.value}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function App() {
  const [route, navigateTo] = useRoute();
  const [session, loadingSession, reloadSession, setSession] = useSession();
  const [theme, setTheme] = useTheme(session);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    document.body.classList.toggle('chat-route', route === '/chat');
    document.documentElement.classList.toggle('chat-route', route === '/chat');
  }, [route]);

  const syncSessionPatch = (patch) => {
    setSession((current) => {
      const nextSession = {
        ...current,
        ...patch,
        settings: {
          ...(current?.settings || {}),
          ...(patch?.settings || {}),
        },
      };
      try {
        localStorage.setItem('stash_session_cache', JSON.stringify(nextSession));
      } catch {
        // Ignore cache write failures and keep the live session state.
      }
      return nextSession;
    });
  };

  useEffect(() => {
    if (!session) return;
    if (session.authenticated && isAuthRoute(route)) {
      navigateTo('/', true);
      return;
    }
    if (!session.authenticated && !isAuthRoute(route)) {
      navigateTo('/login', true);
    }
  }, [session, route]);

  const touchData = () => setRefreshToken((value) => value + 1);

  const updateTheme = async (nextTheme) => {
    const normalized = normalizeTheme(nextTheme);
    setTheme(normalized);
    if (session.authenticated) {
      await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({ theme: normalized }),
      });
      touchData();
    }
  };

  const logout = async () => {
    await apiFetch('/api/auth/logout', { method: 'POST', body: JSON.stringify({}) });
    clearStashStorage();
    navigateTo('/login', true);
    await reloadSession();
  };

  const onAuthSuccess = async () => {
    await reloadSession();
    navigateTo('/', true);
    touchData();
  };

  if (loadingSession) {
    return <SplashScreen />;
  }

  if (route === '/login') {
    return (
      <AuthPage
        onSuccess={onAuthSuccess}
        onThemeChange={updateTheme}
        theme={theme}
        session={session}
      />
    );
  }

  return (
    <AppShell
      route={route}
      theme={theme}
      session={session}
      onNavigate={navigateTo}
      onLogout={logout}
      onThemeChange={updateTheme}
      onSessionSync={syncSessionPatch}
      onTouchData={touchData}
      refreshToken={refreshToken}
    />
  );
}

function AuthPage({ onSuccess, onThemeChange, theme }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await apiFetch('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      if (!result.ok) throw new Error(result.error || 'Authentication failed');
      await onSuccess();
    } catch (err) {
      setError(err.message || 'Authentication failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img src={LOGO_SRC} alt="Stash" className="brand-mark" style={{ width: 56, height: 56, borderRadius: 16 }} />
        <div className="brand-wordmark" style={{ fontSize: 26, marginTop: 4 }}>Stash</div>

        <h1 className="page-title">Welcome back</h1>

        <form className="stack" onSubmit={submit}>
          <input
            className="input"
            type="text"
            required
            autoComplete="username"
            autoCapitalize="none"
            placeholder="Username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
          <input
            className="input"
            type="password"
            required
            minLength={1}
            autoComplete="current-password"
            placeholder="Password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button className="btn btn-primary btn-full" type="submit" disabled={busy}>
            {busy ? 'Signing in...' : 'Log in'}
          </button>
        </form>

        {error ? <div className="alert alert-error">{error}</div> : null}

        <ThemeToggle theme={theme} onThemeChange={onThemeChange} />
      </div>
    </div>
  );
}

function AppShell({
  route,
  theme,
  session,
  onNavigate,
  onLogout,
  onThemeChange,
  onSessionSync,
  onTouchData,
  refreshToken,
}) {
  return (
    <div className="app-frame" data-theme={theme}>
      <aside className="sidebar">
        <Brand />
        <Nav route={route} onNavigate={onNavigate} vertical />
        <div className="sidebar-footer">
          <div className="account-card">
            <div className="account-title">{session.display_name || session.username || 'Stash'}</div>
            <div className="account-subtitle">Private wallet</div>
          </div>
          <ThemeToggle theme={theme} onThemeChange={onThemeChange} />
        </div>
      </aside>

      <div className="app-column">
        <main className={route === '/chat' ? 'app-shell app-shell-chat' : 'app-shell'}>
          <Page
            route={route}
            theme={theme}
            session={session}
            onNavigate={onNavigate}
            onTouchData={onTouchData}
            refreshToken={refreshToken}
            onThemeChange={onThemeChange}
            onSessionSync={onSessionSync}
            onLogout={onLogout}
          />
        </main>

        <MobileNav route={route} onNavigate={onNavigate} />
      </div>
    </div>
  );
}

function Brand({ compact = false }) {
  return (
    <a href="/" className="brand-link" onClick={(event) => {
      event.preventDefault();
      navigate('/', true);
    }}>
      <img
        src={LOGO_SRC}
        alt="Stash"
        className={compact ? 'brand-mark brand-mark-compact' : 'brand-mark'}
      />
      {!compact ? (
        <div>
          <div className="brand-wordmark">Stash</div>
        </div>
      ) : null}
    </a>
  );
}

function Nav({ route, onNavigate, vertical = false }) {
  return (
    <nav className={vertical ? 'sidebar-nav' : 'nav-inner'} aria-label="Primary">
      {NAV_ITEMS.map((item) => (
        <a
          key={item.path}
          href={item.path}
          className={`nav-link ${route === item.path ? 'active' : ''}`}
          onClick={(event) => {
            event.preventDefault();
            onNavigate(item.path);
          }}
        >
          <span className="nav-icon">
            <span className="material-symbols-rounded">{item.icon}</span>
          </span>
          <span>{item.label}</span>
        </a>
      ))}
    </nav>
  );
}

function MobileNav({ route, onNavigate }) {
  return (
    <nav className="nav mobile-nav" aria-label="Primary">
      <div className="nav-inner">
        {NAV_ITEMS.map((item) => (
          <a
            key={item.path}
            href={item.path}
            className={`nav-link ${route === item.path ? 'active' : ''}`}
            onClick={(event) => {
              event.preventDefault();
              onNavigate(item.path);
            }}
          >
            <span className="material-symbols-rounded">{item.icon}</span>
            <span>{item.label}</span>
          </a>
        ))}
      </div>
    </nav>
  );
}

function Page({ route, theme, session, onNavigate, onTouchData, refreshToken, onThemeChange, onSessionSync, onUnlock, onBiometric, onLogout }) {
  if (route === '/chat') {
    return (
      <ChatPage
        session={session}
        onNavigate={onNavigate}
        onTouchData={onTouchData}
        refreshToken={refreshToken}
      />
    );
  }
  if (route === '/timeline') {
    return <TimelinePage session={session} />;
  }
  if (route === '/reports') {
    return <ReportsPage session={session} refreshToken={refreshToken} />;
  }
  if (route === '/settings') {
    return (
      <SettingsPage
        session={session}
        theme={theme}
        onThemeChange={onThemeChange}
        onSessionSync={onSessionSync}
        onTouchData={onTouchData}
        onLogout={onLogout}
      />
    );
  }
  return <DashboardPage session={session} onNavigate={onNavigate} refreshToken={refreshToken} onTouchData={onTouchData} />;
}

function DashboardPage({ session, onNavigate, refreshToken, onTouchData }) {
  const [data, setData] = useState(() => readJsonCache(DASHBOARD_CACHE_KEY, null));
  const [recurring, setRecurring] = useState(() => readJsonCache(RECURRING_CACHE_KEY, []));
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    setError('');
    const loadDashboard = async () => {
      try {
        const [dashboardResult, recurringResult] = await Promise.allSettled([
          apiFetch('/api/dashboard', { method: 'GET', headers: {} }),
          apiFetch('/api/recurring', { method: 'GET', headers: {} }),
        ]);
        if (!alive) return;

        if (dashboardResult.status === 'fulfilled') {
          setData(dashboardResult.value);
          writeJsonCache(DASHBOARD_CACHE_KEY, dashboardResult.value);
        } else if (dashboardResult.reason?.status === 401 || recurringResult.reason?.status === 401) {
          navigate('/login', true);
          return;
        } else if (dashboardResult.reason) {
          setError(dashboardResult.reason.message);
        }

        if (recurringResult.status === 'fulfilled') {
          setRecurring(recurringResult.value);
          writeJsonCache(RECURRING_CACHE_KEY, recurringResult.value);
        } else if (recurringResult.reason?.status === 401) {
          navigate('/login', true);
          return;
        } else if (recurringResult.reason && !dashboardResult.reason) {
          setError(recurringResult.reason.message);
        }
      } catch (err) {
        if (alive) setError(err.message);
      }
    };

    loadDashboard();
    return () => {
      alive = false;
    };
  }, [refreshToken]);

  const currency = session.settings?.currency || 'INR';

  return (
    <div className="stack">
      <SectionHeader
        title="Dashboard"
      />

      {error ? <div className="alert alert-error">{error}</div> : null}

      <section className="card hero-card">
        <div className="eyebrow">Current balance</div>
        <div className="hero-balance">{money(data?.balance || 0, currency)}</div>
        {/* <div className="hero-subtle">Computed live from income minus expense.</div> */}
      </section>

      <section className="grid metrics">
        <MetricCard label="This Month Income" value={money(data?.income || 0, currency)} tone="good" />
        <MetricCard label="This Month Expense" value={money(data?.expense || 0, currency)} tone="bad" />
        <MetricCard label="Savings" value={money(data?.saved || 0, currency)} tone="accent" />
      </section>

      {data?.suggestion ? <div className="card card-pad insight-card">{data.suggestion}</div> : null}

      <section className="grid two-up">
        <div className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="card-title">Recent transaction timeline</h2>
              <div className="card-note">Latest income and expense activity</div>
            </div>
            <button className="btn btn-ghost" onClick={() => onNavigate('/timeline')}>Open timeline</button>
          </div>
          <div className="timeline">
            {data?.recent_timeline?.length ? (
              data.recent_timeline.map((item) => (
                <TimelineItem key={`${item.type}-${item.label}-${item.date}-${item.amount}`} item={item} currency={currency} />
              ))
            ) : (
              <div className="empty-state">No transactions yet. Tell Stash what happened today.</div>
            )}
          </div>
        </div>

        <div className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="card-title">Recurring</h2>
              <div className="card-note">Salary, rent, EMIs, and subscriptions on autopilot</div>
            </div>
            <button className="btn btn-ghost" onClick={() => onNavigate('/settings')}>Manage</button>
          </div>
          <div className="stack">
            {recurring.length ? recurring.slice(0, 4).map((row) => <RecurringCard key={row.id} row={row} currency={currency} />) : (
              <div className="empty-state">No recurring rules yet.</div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function ChatPage({ session, onNavigate, onTouchData, refreshToken }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [paymentMethod, setPaymentMethod] = useState(null); // 'cash' | 'online' | null (#33)
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const textareaRef = useRef(null);

  const resizeComposer = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  const scrollBottom = () => {
    requestAnimationFrame(() => {
      const scrollTarget = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
      window.scrollTo({ top: scrollTarget, behavior: 'auto' });
    });
  };

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const rows = await apiFetch('/api/chat/history', { method: 'GET', headers: {} });
        if (!alive) return;
        setMessages(rows.map((row) => ({ role: row.role, content: row.content })));
        if (!rows.length) {
          setMessages([
            { role: 'assistant', content: "Hi, I'm Stash. Tell me what happened today." },
          ]);
        }
        setLoading(false);
        scrollBottom();
      } catch (err) {
        if (err.status === 401) {
          navigate('/login', true);
          return;
        }
        if (alive) {
          setError(err.message);
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      alive = false;
    };
  }, [refreshToken]);

  useEffect(() => {
    scrollBottom();
  }, [messages]);

  useEffect(() => {
    resizeComposer();
  }, [input]);

  useEffect(() => {
    if (!busy) {
      textareaRef.current?.focus();
    }
  }, [busy]);

  const addMessage = (role, content) => {
    setMessages((prev) => [...prev, { role, content }]);
  };

  const sendMessage = async (overrideMessage) => {
    const message = (overrideMessage ?? input).trim();
    if (!message || busy) return;
    setBusy(true);
    setError('');
    setInput('');
    addMessage('user', message);
    addMessage('assistant', '__TYPING__');
    try {
      const reply = await apiFetch('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message, payment_method: paymentMethod }),
      });
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content: reply.reply };
        return next;
      });
      if (reply.needs_confirmation && reply.candidates) {
        addMessage('assistant', `I found ${reply.candidates.length} possible matches. Pick one below.`);
        addMessage('assistant', JSON.stringify({
          candidates: reply.candidates,
          pendingNewAmount: reply.data?.pending_new_amount,
          pendingAction: reply.data?.pending_action || (reply.intent === 'delete' ? 'delete' : 'correction'),
        }));
      }
      onTouchData();
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content: err.message || 'Something went wrong.' };
        return next;
      });
      if (err.status === 401) {
        navigate('/login', true);
      }
    } finally {
      setBusy(false);
      scrollBottom();
      requestAnimationFrame(() => {
        resizeComposer();
        textareaRef.current?.focus();
      });
    }
  };

  const handleCandidateConfirm = async (candidate, pendingNewAmount) => {
    addMessage('assistant', 'Updating...');
    const pendingAction = candidatePayload?.pendingAction || (pendingNewAmount ? 'correction' : 'delete');
    const endpoint = pendingAction === 'delete' ? '/api/chat/confirm-delete' : '/api/chat/confirm-correction';
    const payload = pendingAction === 'delete'
      ? {
          transaction_id: candidate.id,
          transaction_type: candidate.type,
        }
      : {
          transaction_id: candidate.id,
          transaction_type: candidate.type,
          new_amount: pendingNewAmount,
        };
    const result = await apiFetch(endpoint, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    setMessages((prev) => [...prev, { role: 'assistant', content: result.reply }]);
    onTouchData();
  };

  const candidatePayload = useMemo(() => {
    const last = messages[messages.length - 1];
    if (!last || last.role !== 'assistant') return null;
    try {
      const parsed = JSON.parse(last.content);
      if (parsed && parsed.candidates) return parsed;
    } catch {
      return null;
    }
    return null;
  }, [messages]);

  return (
    <div className="chat-shell chat-page-shell">
      <SectionHeader title="Chat with Stash" />

      <div className="chat-panel">
        <div className="chat-log">
          {loading ? <div className="empty-state">Loading chat...</div> : null}
          {error ? <div className="alert alert-error">{error}</div> : null}
          {!loading && !messages.length ? <div className="empty-state">No conversation yet.</div> : null}
          {messages.map((message, index) => {
            if (typeof message.content === 'string' && message.content.startsWith('{') && message.role === 'assistant') {
              return null;
            }
            return (
              <Bubble key={`${index}-${message.role}-${message.content.slice(0, 10)}`} role={message.role} onCandidate={handleCandidateConfirm} message={message} candidatePayload={candidatePayload} />
            );
          })}
          {candidatePayload ? (
            <div className="bubble-row assistant">
              <div className="bubble assistant bubble-stack">
                {candidatePayload.candidates.map((candidate) => (
                  <button
                    key={candidate.id}
                    className="btn btn-ghost btn-full candidate-btn"
                    onClick={() => handleCandidateConfirm(candidate, candidatePayload.pendingNewAmount)}
                  >
                    <span>{candidate.label}</span>
                    <span>
                      {money(candidate.amount, session.settings?.currency || 'INR')} ({candidate.date})
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            sendMessage();
          }}
        >
          <div className="composer-wallet-toggle" role="group" aria-label="Payment method">
            <button
              type="button"
              className={`btn btn-ghost btn-pill${paymentMethod === 'cash' ? ' active' : ''}`}
              aria-pressed={paymentMethod === 'cash'}
              onClick={() => setPaymentMethod((prev) => (prev === 'cash' ? null : 'cash'))}
              title="Log this as a cash transaction unless the message says otherwise"
            >
              <span className="material-symbols-rounded" aria-hidden="true">payments</span>
              Cash
            </button>
            <button
              type="button"
              className={`btn btn-ghost btn-pill${paymentMethod === 'online' ? ' active' : ''}`}
              aria-pressed={paymentMethod === 'online'}
              onClick={() => setPaymentMethod((prev) => (prev === 'online' ? null : 'online'))}
              title="Log this as an online/digital transaction unless the message says otherwise"
            >
              <span className="material-symbols-rounded" aria-hidden="true">contactless</span>
              Online
            </button>
          </div>
          <textarea
            ref={textareaRef}
            className="input composer-textarea"
            rows={1}
            autoComplete="off"
            placeholder="Ask Stash anything..."
            value={input}
            disabled={busy}
            onChange={(event) => {
              setInput(event.target.value);
              resizeComposer();
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
              }
            }}
          />
          <button className="btn btn-primary" type="submit" disabled={busy || !input.trim()} aria-label="Send message">
            <span className="material-symbols-rounded" aria-hidden="true">
              arrow_upward
            </span>
          </button>
        </form>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <span className="typing-indicator" aria-label="Stash is typing">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </span>
  );
}

function formatInlineMarkdown(text) {
  // Minimal, safe inline formatting: **bold** only. No HTML injection risk
  // since we build React nodes, never dangerouslySetInnerHTML.
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={idx}>{part.slice(2, -2)}</strong>;
    }
    return <React.Fragment key={idx}>{part}</React.Fragment>;
  });
}

function BubbleContent({ content }) {
  // Renders the assistant/user text with real line breaks and turns lines
  // starting with "- " or "* " into an actual bulleted list, instead of
  // dumping raw text into one <div> where newlines visually collapse.
  const lines = content.split('\n');
  const nodes = [];
  let currentList = [];

  const flushList = (key) => {
    if (currentList.length) {
      nodes.push(
        <ul className="bubble-list" key={`ul-${key}`}>
          {currentList.map((line, i) => (
            <li key={i}>{formatInlineMarkdown(line.replace(/^[-*]\s+/, ''))}</li>
          ))}
        </ul>
      );
      currentList = [];
    }
  };

  lines.forEach((line, idx) => {
    if (/^[-*]\s+/.test(line.trim())) {
      currentList.push(line.trim());
    } else {
      flushList(idx);
      if (line.trim().length) {
        nodes.push(<p className="bubble-line" key={idx}>{formatInlineMarkdown(line)}</p>);
      }
    }
  });
  flushList('end');

  return <>{nodes}</>;
}

function Bubble({ message, role }) {
  if (message.content === '__TYPING__') {
    return (
      <div className={`bubble-row ${role}`}>
        <div className={`bubble ${role} bubble-typing`}>
          <TypingIndicator />
        </div>
      </div>
    );
  }
  return (
    <div className={`bubble-row ${role}`}>
      <div className={`bubble ${role}`}>
        <BubbleContent content={message.content} />
      </div>
    </div>
  );
}

function TimelinePage({ session }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  const [editingKey, setEditingKey] = useState('');
  const [editForm, setEditForm] = useState(null);
  const [busyKey, setBusyKey] = useState('');

  const loadRows = async () => {
    return apiFetch('/api/timeline', { method: 'GET', headers: {} });
  };

  useEffect(() => {
    let alive = true;
    loadRows()
      .then((data) => {
        if (!alive) return;
        setRows(data);
      })
      .catch((err) => {
        if (err.status === 401) {
          navigate('/login', true);
          return;
        }
        if (alive) setError(err.message);
      });
    return () => {
      alive = false;
    };
  }, []);

  const startEdit = (item) => {
    const key = `${item.type}-${item.id}`;
    setEditingKey(key);
    setEditForm({
      amount: String(item.amount ?? ''),
      category_or_source: item.label || '',
      description: item.description || '',
      date: toDateInput(item.date),
    });
  };

  const cancelEdit = () => {
    setEditingKey('');
    setEditForm(null);
  };

  const saveEdit = async (item) => {
    if (!editForm) return;
    const key = `${item.type}-${item.id}`;
    setBusyKey(key);
    setError('');
    try {
      await apiFetch(`/api/transactions/${item.type}/${item.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          amount: Number(editForm.amount),
          category_or_source: editForm.category_or_source,
          description: editForm.description || null,
          date: editForm.date,
        }),
      });
      cancelEdit();
      setRows(await loadRows());
    } catch (err) {
      if (err.status === 401) {
        navigate('/login', true);
        return;
      }
      setError(err.message);
    } finally {
      setBusyKey('');
    }
  };

  const deleteEntry = async (item) => {
    const key = `${item.type}-${item.id}`;
    if (!window.confirm(`Delete this ${item.type} entry?`)) return;
    setBusyKey(key);
    setError('');
    try {
      await apiFetch(`/api/transactions/${item.type}/${item.id}`, {
        method: 'DELETE',
        body: JSON.stringify({}),
      });
      if (editingKey === key) cancelEdit();
      setRows(await loadRows());
    } catch (err) {
      if (err.status === 401) {
        navigate('/login', true);
        return;
      }
      setError(err.message);
    } finally {
      setBusyKey('');
    }
  };

  const groups = useMemo(() => {
    const byLabel = {};
    rows.forEach((row) => {
      const label = dayLabel(row.date);
      if (!byLabel[label]) byLabel[label] = [];
      byLabel[label].push(row);
    });
    return byLabel;
  }, [rows]);

  return (
    <div className="stack">
      <SectionHeader title="Timeline" />
      {error ? <div className="alert alert-error">{error}</div> : null}
      <div className="timeline-stack">
        {rows.length ? (
          Object.entries(groups).map(([label, items]) => (
            <div key={label} className="stack">
              <div className="timeline-heading">{label}</div>
              <div className="stack">
                {items.map((item) => {
                  const key = `${item.type}-${item.id}`;
                  const editing = editingKey === key;
                  return (
                    <TimelineItem
                      key={`${item.id}-${item.date}`}
                      item={item}
                      currency={session.settings?.currency || 'INR'}
                      actions={editing ? (
                        <>
                          <button
                            className="btn btn-primary btn-inline"
                            type="button"
                            onClick={() => saveEdit(item)}
                            disabled={busyKey === key || !editForm}
                          >
                            Save
                          </button>
                          <button
                            className="btn btn-ghost btn-inline"
                            type="button"
                            onClick={cancelEdit}
                            disabled={busyKey === key}
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            className="btn btn-ghost btn-inline"
                            type="button"
                            onClick={() => startEdit(item)}
                            disabled={busyKey === key}
                          >
                            Edit
                          </button>
                          <button
                            className="btn btn-danger btn-inline"
                            type="button"
                            onClick={() => deleteEntry(item)}
                            disabled={busyKey === key}
                          >
                            Delete
                          </button>
                        </>
                      )}
                    >
                      {editing ? (
                        <div className="transaction-editor-grid">
                          <label className="field">
                            <span>Amount</span>
                            <input
                              className="input"
                              type="number"
                              value={editForm?.amount ?? ''}
                              onChange={(event) => setEditForm((prev) => ({ ...prev, amount: event.target.value }))}
                            />
                          </label>
                          <label className="field">
                            <span>{item.type === 'income' ? 'Source' : 'Category'}</span>
                            <input
                              className="input"
                              value={editForm?.category_or_source ?? ''}
                              onChange={(event) => setEditForm((prev) => ({ ...prev, category_or_source: event.target.value }))}
                            />
                          </label>
                          <label className="field">
                            <span>Date</span>
                            <input
                              className="input"
                              type="date"
                              value={editForm?.date ?? ''}
                              onChange={(event) => setEditForm((prev) => ({ ...prev, date: event.target.value }))}
                            />
                          </label>
                          <label className="field wide">
                            <span>Description</span>
                            <input
                              className="input"
                              value={editForm?.description ?? ''}
                              onChange={(event) => setEditForm((prev) => ({ ...prev, description: event.target.value }))}
                              placeholder="Optional note"
                            />
                          </label>
                        </div>
                      ) : null}
                    </TimelineItem>
                  );
                })}
              </div>
            </div>
          ))
        ) : (
          <div className="empty-state">Nothing logged yet.</div>
        )}
      </div>
    </div>
  );
}

function ReportsPage({ session, refreshToken }) {
  const [months, setMonths] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    apiFetch('/api/reports/months', { method: 'GET', headers: {} })
      .then((data) => {
        if (!alive) return;
        const rows = data.length
          ? data
          : (() => {
              const today = new Date();
              return [{ year: today.getFullYear(), month: today.getMonth() + 1, label: 'This month' }];
            })();
        setMonths(rows);
        setSelectedMonth(`${rows[0].year}-${rows[0].month}`);
      })
      .catch((err) => setError(err.message));
    return () => {
      alive = false;
    };
  }, [refreshToken]);

  useEffect(() => {
    if (!selectedMonth) return;
    const [year, month] = selectedMonth.split('-');
    let alive = true;
    apiFetch(`/api/reports?year=${year}&month=${month}`, { method: 'GET', headers: {} })
      .then((data) => {
        if (alive) setReport(data);
      })
      .catch((err) => {
        if (err.status === 401) {
          navigate('/login', true);
          return;
        }
        if (alive) setError(err.message);
      });
    return () => {
      alive = false;
    };
  }, [selectedMonth, refreshToken]);

  const categories = report ? Object.entries(report.category_breakdown || {}) : [];
  const days = report ? Object.entries(report.daily_trend || {}) : [];

  return (
    <div className="stack">
      <SectionHeader
        title="Reports"
        action={
          <select className="select page-select" value={selectedMonth} onChange={(event) => setSelectedMonth(event.target.value)}>
            {months.map((item) => (
              <option key={`${item.year}-${item.month}`} value={`${item.year}-${item.month}`}>
                {item.label}
              </option>
            ))}
          </select>
        }
      />

      {error ? <div className="alert alert-error">{error}</div> : null}

      <section className="grid metrics">
        <MetricCard label="Income" value={money(report?.income || 0, session.settings?.currency || 'INR')} tone="good" />
        <MetricCard label="Expense" value={money(report?.expense || 0, session.settings?.currency || 'INR')} tone="bad" />
        <MetricCard label="Saved" value={money(report?.saved || 0, session.settings?.currency || 'INR')} tone="accent" />
        <div className="card metric-card">
          <div className="metric-label">Most Used Category</div>
          <div className="metric-value">{report?.most_used_category || '-'}</div>
        </div>
      </section>

      {report?.largest_expense ? <div className="card card-pad">Largest expense: {report.largest_expense.category} - {money(report.largest_expense.amount, session.settings?.currency || 'INR')}</div> : null}

      <section className="grid two-up">
        <div className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="card-title">Spending by Category</h2>
              <div className="card-note">Minimal chart view of the month</div>
            </div>
          </div>
          <PieViz entries={categories} />
        </div>
        <div className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="card-title">Category Comparison</h2>
              <div className="card-note">Bar chart view</div>
            </div>
          </div>
          <BarViz entries={categories} />
        </div>
      </section>

      <section className="card card-pad">
        <div className="card-head">
          <div>
            <h2 className="card-title">Daily Trend</h2>
            <div className="card-note">Expense pattern over the month</div>
          </div>
        </div>
        <LineViz entries={days} />
      </section>

      <section className="card card-pad">
        <div className="card-head">
          <div>
            <h2 className="card-title">Exports</h2>
            <div className="card-note">Offline-friendly download options</div>
          </div>
        </div>
        <div className="grid export-grid">
          <a href="/api/export/csv" className="btn btn-ghost">CSV</a>
          <a href="/api/export/excel" className="btn btn-ghost">Excel</a>
          <a href="/api/export/pdf" className="btn btn-ghost">PDF</a>
        </div>
      </section>
    </div>
  );
}

function SettingsPage({ session, theme, onThemeChange, onSessionSync, onTouchData, onLogout }) {
  const [settings, setSettings] = useState({
    monthly_alert_amount: '',
    salary_day: '',
    currency: 'INR',
    theme: theme || 'mist',
  });
  const [account, setAccount] = useState({
    username: session.username || '',
    old_password: '',
    new_password: '',
  });
  const [currencyOpen, setCurrencyOpen] = useState(false);
  const [recurringRows, setRecurringRows] = useState([]);
  const [form, setForm] = useState({
    name: '',
    category_or_source: 'Salary',
    transaction_type: 'income',
    amount: '',
    description: '',
    start_date: toDateInput(new Date()),
    interval_months: 1,
    total_cycles: '',
  });
  const [saveStatus, setSaveStatus] = useState('');
  const [accountStatus, setAccountStatus] = useState('');
  const [error, setError] = useState('');
  const currencyRef = useRef(null);

  const load = async () => {
    try {
      const [settingsData, recurringData] = await Promise.all([
        apiFetch('/api/settings', { method: 'GET', headers: {} }),
        apiFetch('/api/recurring', { method: 'GET', headers: {} }),
      ]);
      setSettings((prev) => ({
        ...prev,
        ...settingsData,
        currency: (settingsData.currency || prev.currency || 'INR').toUpperCase(),
        theme: normalizeTheme(settingsData.theme || theme || 'mist'),
      }));
      setRecurringRows(recurringData);
    } catch (err) {
      if (err.status === 401) {
        navigate('/login', true);
        return;
      }
      setError(err.message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    setAccount((prev) => ({
      ...prev,
      username: session.username || prev.username || '',
    }));
  }, [session.username]);

  useEffect(() => {
    const onPointerDown = (event) => {
      if (currencyRef.current && !currencyRef.current.contains(event.target)) {
        setCurrencyOpen(false);
      }
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setCurrencyOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  const saveSettings = async () => {
    setError('');
    try {
      await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({
          monthly_alert_amount: settings.monthly_alert_amount ? Number(settings.monthly_alert_amount) : null,
          salary_day: settings.salary_day ? Number(settings.salary_day) : null,
          currency: settings.currency,
          theme: settings.theme,
        }),
      });
      onSessionSync({
        settings: {
          monthly_alert_amount: settings.monthly_alert_amount ? Number(settings.monthly_alert_amount) : null,
          salary_day: settings.salary_day ? Number(settings.salary_day) : null,
          currency: settings.currency,
          theme: settings.theme,
        },
      });
      await onThemeChange(settings.theme);
      setSaveStatus('Saved.');
      onTouchData();
      setTimeout(() => setSaveStatus(''), 1600);
    } catch (err) {
      setError(err.message);
    }
  };

  const saveAccount = async () => {
    setError('');
    const nextUsername = account.username.trim();
    const currentUsername = (session.username || '').trim();
    const payload = {};

    if (nextUsername && nextUsername !== currentUsername) {
      payload.username = nextUsername;
    }
    if (account.new_password) {
      payload.old_password = account.old_password;
      payload.new_password = account.new_password;
    }

    if (!Object.keys(payload).length) {
      setAccountStatus('No changes to save.');
      return;
    }

    try {
      const result = await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      if (payload.username) {
        onSessionSync({ username: result.username || nextUsername });
      }
      setAccount((prev) => ({ ...prev, old_password: '', new_password: '' }));
      setAccountStatus('Account updated.');
      setTimeout(() => setAccountStatus(''), 1600);
    } catch (err) {
      setError(err.message);
    }
  };

  const saveRecurring = async () => {
    try {
      await apiFetch('/api/recurring', {
        method: 'POST',
        body: JSON.stringify({
          name: form.name,
          category_or_source: form.category_or_source,
          transaction_type: form.transaction_type,
          amount: Number(form.amount),
          description: form.description || null,
          start_date: fromDateInput(form.start_date),
          interval_months: Number(form.interval_months || 1),
          total_cycles: form.total_cycles ? Number(form.total_cycles) : null,
        }),
      });
      setForm((prev) => ({ ...prev, name: '', amount: '', description: '', total_cycles: '' }));
      await load();
      onTouchData();
    } catch (err) {
      setError(err.message);
    }
  };

  const recurringTypeOptions = [
    { value: 'income', label: 'Income' },
    { value: 'expense', label: 'Expense' },
  ];
  const recurringCategoryOptions = (form.transaction_type === 'income'
    ? ['Salary', 'Freelance', 'Gift', 'Refund', 'Other']
    : ['Rent', 'EMI', 'Subscription', 'Bills', 'Groceries', 'Other']
  ).map((item) => ({ value: item, label: item }));

  const disableRecurring = async (id) => {
    await apiFetch(`/api/recurring/${id}/disable`, { method: 'POST', body: JSON.stringify({}) });
    await load();
    onTouchData();
  };

  return (
    <div className="stack">
      <SectionHeader title="Settings" />

      {error ? <div className="alert alert-error">{error}</div> : null}

      <section className="grid two-up">
        <div className="card card-pad stack">
          <h2 className="card-title">Account</h2>
          <div className="form-grid wallet-grid">
            <label className="field">
              <span>Username</span>
              <input
                className="input"
                autoComplete="username"
                value={account.username}
                onChange={(e) => setAccount((prev) => ({ ...prev, username: e.target.value }))}
                placeholder="Username"
              />
            </label>
            <label className="field">
              <span>Old password</span>
              <input
                className="input"
                type="password"
                autoComplete="current-password"
                value={account.old_password}
                onChange={(e) => setAccount((prev) => ({ ...prev, old_password: e.target.value }))}
                placeholder="Required only for password changes"
              />
            </label>
            <label className="field">
              <span>New password</span>
              <input
                className="input"
                type="password"
                autoComplete="new-password"
                value={account.new_password}
                onChange={(e) => setAccount((prev) => ({ ...prev, new_password: e.target.value }))}
                placeholder="Leave blank to keep current password"
              />
            </label>
          </div>
          <div className="card-note">
            Change username directly. If you set a new password, the old password is required.
          </div>
          <button className="btn btn-primary btn-full" onClick={saveAccount}>Save account</button>
          {accountStatus ? <div className="success-text">{accountStatus}</div> : null}
        </div>

        <div className="card card-pad stack">
          <h2 className="card-title">Wallet preferences</h2>
          <div className="form-grid wallet-grid">
            <label className="field">
              <span>Monthly low-balance alert</span>
              <input className="input" type="number" value={settings.monthly_alert_amount ?? ''} onChange={(e) => setSettings((prev) => ({ ...prev, monthly_alert_amount: e.target.value }))} />
            </label>
            <label className="field">
              <span>Salary day</span>
              <input className="input" type="number" min="1" max="31" value={settings.salary_day ?? ''} onChange={(e) => setSettings((prev) => ({ ...prev, salary_day: e.target.value }))} />
            </label>
            <label className="field">
              <span>Currency</span>
              <div className="currency-picker" ref={currencyRef}>
                <button
                  type="button"
                  className={`currency-trigger ${currencyOpen ? 'open' : ''}`}
                  onClick={() => setCurrencyOpen((open) => !open)}
                  aria-haspopup="listbox"
                  aria-expanded={currencyOpen}
                >
                  <span className="currency-trigger-label">{CURRENCY_OPTIONS.find((item) => item.key === settings.currency)?.label || settings.currency}</span>
                  <span className="currency-trigger-code">{settings.currency}</span>
                  <span className="currency-trigger-caret">⌄</span>
                </button>
                {currencyOpen ? (
                  <div className="currency-menu" role="listbox" aria-label="Currency">
                    {CURRENCY_OPTIONS.map((option) => (
                      <button
                        key={option.key}
                        type="button"
                        className={`currency-option ${settings.currency === option.key ? 'active' : ''}`}
                        onClick={() => {
                          setSettings((prev) => ({ ...prev, currency: option.key }));
                          setCurrencyOpen(false);
                        }}
                        role="option"
                        aria-selected={settings.currency === option.key}
                      >
                        <span>{option.label}</span>
                        <span className="currency-option-code">{option.key}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </label>
            <label className="field theme-field">
              <span>Theme</span>
              <div className="theme-palette">
                {THEME_OPTIONS.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    className={`theme-chip ${settings.theme === option.key ? 'active' : ''}`}
                    onClick={() => setSettings((prev) => ({ ...prev, theme: option.key }))}
                  >
                    <span className="theme-swatch" style={{ background: option.swatch }} />
                    <span>{option.label}</span>
                  </button>
                ))}
              </div>
            </label>
          </div>
          <button className="btn btn-primary btn-full" onClick={saveSettings}>Save preferences</button>
          {saveStatus ? <div className="success-text">{saveStatus}</div> : null}
        </div>
      </section>

      <section className="card card-pad stack">
        <div className="card-head">
          <div>
            <h2 className="card-title">Recurring transactions</h2>
            <div className="card-note">Salary, rent, EMI, and subscription schedules that auto-log each cycle</div>
          </div>
        </div>
          <div className="form-grid recurring-grid">
            <label className="field">
              <span>Name</span>
              <input className="input" value={form.name} onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))} placeholder="Rent / Salary / EMI" />
            </label>
            <label className="field">
              <span>Type</span>
              <ThemedDropdown
                label="Type"
                value={form.transaction_type}
                options={recurringTypeOptions}
                onChange={(next) => setForm((prev) => ({
                  ...prev,
                  transaction_type: next,
                  category_or_source: next === 'income' ? 'Salary' : 'Rent',
                }))}
              />
            </label>
            <label className="field">
              <span>Category / Source</span>
              <ThemedDropdown
                label="Category / Source"
                value={form.category_or_source}
                options={recurringCategoryOptions}
                onChange={(next) => setForm((prev) => ({ ...prev, category_or_source: next }))}
              />
            </label>
          <label className="field">
            <span>Amount</span>
            <input className="input" type="number" value={form.amount} onChange={(e) => setForm((prev) => ({ ...prev, amount: e.target.value }))} />
          </label>
          <label className="field">
            <span>Start date</span>
            <input className="input" type="date" value={form.start_date} onChange={(e) => setForm((prev) => ({ ...prev, start_date: e.target.value }))} />
          </label>
          <label className="field">
            <span>Interval months</span>
            <input className="input" type="number" min="1" value={form.interval_months} onChange={(e) => setForm((prev) => ({ ...prev, interval_months: e.target.value }))} />
          </label>
          <label className="field">
            <span>Cycle count</span>
            <input className="input" type="number" min="1" placeholder="Leave blank for open-ended" value={form.total_cycles} onChange={(e) => setForm((prev) => ({ ...prev, total_cycles: e.target.value }))} />
          </label>
          <label className="field wide">
            <span>Description</span>
            <input className="input" value={form.description} onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))} placeholder="Optional note" />
          </label>
        </div>
        <button className="btn btn-primary" onClick={saveRecurring}>Add recurring rule</button>
      </section>

      <section className="grid recurring-list">
        {recurringRows.length ? recurringRows.map((row) => (
          <RecurringCard key={row.id} row={row} currency={session.settings?.currency || 'INR'} onDisable={disableRecurring} />
        )) : <div className="empty-state">No recurring schedules yet.</div>}
      </section>

      <section className="card card-pad stack">
        <div className="card-head">
          <div>
            <h2 className="card-title">Account</h2>
            <div className="card-note">Signed in as {session.display_name || session.username || 'your account'}</div>
          </div>
        </div>
        <button className="btn btn-danger btn-full" type="button" onClick={onLogout}>
          <span className="material-symbols-rounded" style={{ fontSize: 18 }}>logout</span>
          Log out
        </button>
      </section>
    </div>
  );
}

export default App;
