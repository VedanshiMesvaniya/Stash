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
  { path: '/', label: 'Dashboard', short: 'DB' },
  { path: '/chat', label: 'Chat', short: 'AI' },
  { path: '/timeline', label: 'Timeline', short: 'TX' },
  { path: '/reports', label: 'Reports', short: 'RP' },
  { path: '/settings', label: 'Settings', short: 'ST' },
];

const AUTH_ROUTES = new Set(['/login']);
const LOGO_SRC = '/static/icons/FullLogo.png';
const DASHBOARD_CACHE_KEY = 'stash_dashboard_cache';
const RECURRING_CACHE_KEY = 'stash_recurring_cache';

const emptySession = {
  authenticated: false,
  first_run: false,
  settings: {
    theme: 'obsidian',
    currency: 'INR',
  },
};

const THEME_OPTIONS = [
  { key: 'obsidian', label: 'Obsidian', swatch: '#1f2430' },
  { key: 'shadow', label: 'Shadow', swatch: '#312f41' },
  { key: 'violet', label: 'Violet', swatch: '#4b3b6f' },
  { key: 'lavender', label: 'Lavender', swatch: '#b8a4d1' },
  { key: 'mist', label: 'Mist', swatch: '#d3d0cf' },
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
  const initial = localStorage.getItem('stash_theme') || session?.settings?.theme || 'obsidian';
  const [theme, setTheme] = useState(normalizeTheme(initial));

  useEffect(() => {
    const nextTheme = session?.settings?.theme || localStorage.getItem('stash_theme') || 'obsidian';
    setTheme(normalizeTheme(nextTheme));
  }, [session?.settings?.theme]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('stash_theme', theme);
  }, [theme]);

  return [theme, setTheme];
}

function normalizeTheme(value) {
  if (!value) return 'obsidian';
  if (value === 'dark') return 'obsidian';
  if (value === 'light') return 'mist';
  return value;
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
    const isChat = route === '/chat';
    document.body.classList.toggle('chat-route', isChat);
    document.documentElement.classList.toggle('chat-route', isChat);
    document.body.style.overflow = isChat ? 'hidden' : '';
    document.documentElement.style.overflow = isChat ? 'hidden' : '';
    return () => {
      document.body.classList.remove('chat-route');
      document.documentElement.classList.remove('chat-route');
      document.body.style.overflow = '';
      document.documentElement.style.overflow = '';
    };
  }, [route]);

  const syncSessionSettings = (patch) => {
    setSession((current) => ({
      ...current,
      settings: {
        ...(current?.settings || {}),
        ...patch,
      },
    }));
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
      onSessionSync={syncSessionSettings}
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
        <img src={LOGO_SRC} alt="Stash" className="brand-logo brand-logo-auth" />
        <div className="brand-subtitle">Private family finance workspace</div>

        <h1 className="page-title">Welcome back</h1>
        <p className="page-copy">Sign in with the username and password you were given.</p>

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
          <button className="btn btn-danger btn-full" type="button" onClick={onLogout}>
            Log out
          </button>
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
        className={compact ? 'brand-logo brand-logo-compact' : 'brand-logo brand-logo-shell'}
      />
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
          <span className="nav-icon">{item.short}</span>
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
            <span>{item.label}</span>
          </a>
        ))}
      </div>
    </nav>
  );
}

function Page({ route, theme, session, onNavigate, onTouchData, refreshToken, onThemeChange, onSessionSync, onUnlock, onBiometric }) {
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
        copy="A clean wallet overview powered by chat, recurring tracking, and live summaries."
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
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState(sessionStorage.getItem('stash_chat_history_hidden') === '1');
  const [error, setError] = useState('');
  const logRef = useRef(null);
  const textareaRef = useRef(null);
  const pendingConsumedRef = useRef(false);

  const resizeComposer = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  const scrollBottom = () => {
    requestAnimationFrame(() => {
      if (logRef.current) {
        logRef.current.scrollTop = logRef.current.scrollHeight;
      }
    });
  };

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        if (hidden) {
          if (alive) {
            setMessages([]);
            setLoading(false);
          }
          return;
        }
        const rows = await apiFetch('/api/chat/history', { method: 'GET', headers: {} });
        if (!alive) return;
        setMessages(rows.map((row) => ({ role: row.role, content: row.content })));
        if (!rows.length) {
          setMessages([
            { role: 'assistant', content: "Hi, I'm Stash. Tell me what happened today, for example: Salary received 35000 or Tea 20." },
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
  }, [hidden, refreshToken]);

  useEffect(() => {
    const pending = sessionStorage.getItem('stash_pending_message');
    if (pending && !pendingConsumedRef.current) {
      pendingConsumedRef.current = true;
      sessionStorage.removeItem('stash_pending_message');
      setInput(pending);
      queueMicrotask(() => {
        sendMessage(pending);
      });
    }
  }, []);

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
        body: JSON.stringify({ message }),
      });
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content: reply.reply };
        return next;
      });
      if (reply.needs_confirmation && reply.candidates) {
        addMessage('assistant', `I found ${reply.candidates.length} possible matches. Pick one below.`);
        addMessage('assistant', JSON.stringify({ candidates: reply.candidates, pendingNewAmount: reply.data?.pending_new_amount }));
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

  const clearChat = () => {
    sessionStorage.setItem('stash_chat_history_hidden', '1');
    setHidden(true);
    setMessages([]);
  };

  const showChat = async () => {
    sessionStorage.removeItem('stash_chat_history_hidden');
    setHidden(false);
    setLoading(true);
  };

  const handleCandidateConfirm = async (candidate, pendingNewAmount) => {
    addMessage('assistant', 'Updating...');
    const result = await apiFetch('/api/chat/confirm-correction', {
      method: 'POST',
      body: JSON.stringify({
        transaction_id: candidate.id,
        transaction_type: candidate.type,
        new_amount: pendingNewAmount,
      }),
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
      <SectionHeader
        title="Chat with Stash"
        copy="Speak naturally. Stash turns plain language into transactions, corrections, and reports."
        action={<button className="btn btn-ghost" onClick={hidden ? showChat : clearChat}>{hidden ? 'Show chat' : 'Clear chat'}</button>}
      />

      <div className="chip-row section">
        {['Salary received 35000', 'Paid 480 for petrol', 'Show this month report', 'How much money do I have?'].map((chip) => (
          <button key={chip} className="chip" onClick={() => setInput(chip)}>
            {chip}
          </button>
        ))}
      </div>

      <div className="chat-panel">
        <div className="chat-log" ref={logRef}>
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
          <button className="btn btn-primary" type="submit" disabled={busy || !input.trim()}>
            {busy ? 'Sending...' : 'Send'}
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

  useEffect(() => {
    let alive = true;
    apiFetch('/api/timeline', { method: 'GET', headers: {} })
      .then((data) => {
        if (alive) setRows(data);
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
      <SectionHeader
        title="Timeline"
        copy="A unified ledger view of every income and expense in chronological order."
      />
      {error ? <div className="alert alert-error">{error}</div> : null}
      <div className="timeline-stack">
        {rows.length ? (
          Object.entries(groups).map(([label, items]) => (
            <div key={label} className="stack">
              <div className="timeline-heading">{label}</div>
              <div className="stack">
                {items.map((item) => (
                  <TimelineItem key={`${item.id}-${item.date}`} item={item} currency={session.settings?.currency || 'INR'} />
                ))}
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
        copy="AI-friendly monthly summaries with chart-style views and export links."
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

function SettingsPage({ session, theme, onThemeChange, onSessionSync, onTouchData }) {
  const [settings, setSettings] = useState({
    monthly_alert_amount: '',
    salary_day: '',
    currency: 'INR',
    theme: theme || 'obsidian',
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
        theme: normalizeTheme(settingsData.theme || theme || 'obsidian'),
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
        monthly_alert_amount: settings.monthly_alert_amount ? Number(settings.monthly_alert_amount) : null,
        salary_day: settings.salary_day ? Number(settings.salary_day) : null,
        currency: settings.currency,
        theme: settings.theme,
      });
      await onThemeChange(settings.theme);
      setSaveStatus('Saved.');
      onTouchData();
      setTimeout(() => setSaveStatus(''), 1600);
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
      <SectionHeader
        title="Settings"
        copy="Tune the wallet, app lock, theme, and recurring rules from one clean workspace."
      />

      {error ? <div className="alert alert-error">{error}</div> : null}

      <section className="grid two-up">
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
    </div>
  );
}

export default App;
