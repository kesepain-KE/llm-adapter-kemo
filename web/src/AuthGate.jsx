import { useState, useRef, useEffect } from 'react';

const SESSION_KEY = 'kemo_auth_session';
const LOGIN_API = '/api/auth/login';

/** 从 localStorage / sessionStorage 恢复会话 */
function getStoredSession() {
  try {
    // 优先检查 localStorage（记住此设备）
    const raw = localStorage.getItem(SESSION_KEY) || sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (data && data.token && data.expires > Date.now()) return data;
    // 过期则清理
    localStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_KEY);
    return null;
  } catch {
    localStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export function useAuth() {
  const [session, setSession] = useState(() => getStoredSession());

  /** 调用后端 /api/auth/login，成功则持久化 token */
  const login = async (username, password, remember = false) => {
    const res = await fetch(LOGIN_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, remember }),
    });
    if (!res.ok) return false;

    const data = await res.json();
    const sessionData = {
      token: data.token,
      username: data.username,
      name: data.name,
      expires: data.expires * 1000, // 后端返回秒，转毫秒
    };

    if (remember) {
      localStorage.setItem(SESSION_KEY, JSON.stringify(sessionData));
    } else {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(sessionData));
    }
    setSession(sessionData);
    return true;
  };

  const logout = () => {
    localStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_KEY);
    setSession(null);
  };

  return { session, login, logout, isAuthenticated: !!session };
}

/* ---- 内联 SVG 图标 ---- */

function Eye({ closed = false }) {
  return closed
    ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
    : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>;
}

function Check() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  );
}

function AlertCircle() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  );
}

/* ---- 登录页面 ---- */

export default function AuthGate({ children, auth }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [remember, setRemember] = useState(false);
  const usernameRef = useRef(null);
  const pwdRef = useRef(null);

  useEffect(() => { usernameRef.current?.focus(); }, []);

  if (auth.isAuthenticated) return children;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const username = usernameRef.current?.value.trim() || '';
    const password = pwdRef.current?.value.trim() || '';
    if (!username || !password) {
      setError('请完整填写管理员账号和密码');
      return;
    }
    setLoading(true);
    try {
      const ok = await auth.login(username, password, remember);
      if (!ok) {
        setError('管理员账号或密码错误，请重试');
        if (pwdRef.current) pwdRef.current.value = '';
        pwdRef.current?.focus();
      }
    } catch {
      setError('服务暂不可达，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-glow-1" />
      <div className="auth-glow-2" />

      <div className="auth-card glass">
        <div className="auth-brand">
          <div className="auth-logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" width="20" height="20">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
          </div>
          <div className="auth-brand-text">
            <h1>Kemo Adapter</h1>
            <p>管理面板 · 身份验证</p>
          </div>
        </div>

        <div className="auth-header">
          <h2>鉴权登录</h2>
          <p>使用管理员凭证进入管理后台</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} autoComplete="off">
          {error && (
            <div className="auth-error show">
              <AlertCircle />
              <span>{error}</span>
            </div>
          )}

          <div className="auth-field">
            <label htmlFor="auth-user">管理员账号</label>
            <input
              id="auth-user"
              ref={usernameRef}
              type="text"
              placeholder="输入管理员账号"
              autoComplete="off"
              spellCheck="false"
              defaultValue=""
            />
          </div>

          <div className="auth-field">
            <label htmlFor="auth-pwd">密码</label>
            <div className="auth-input-wrap">
              <input
                id="auth-pwd"
                ref={pwdRef}
                type={showPwd ? 'text' : 'password'}
                placeholder="输入密码"
                autoComplete="off"
                defaultValue=""
              />
              <button
                type="button"
                className="auth-toggle-vis"
                onClick={() => setShowPwd((v) => !v)}
                tabIndex={-1}
                aria-label={showPwd ? '隐藏密码' : '显示密码'}
              >
                <Eye closed={!showPwd} />
              </button>
            </div>
          </div>

          <div className="auth-options">
            <label className="auth-remember">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              <span className="auth-check-box"><Check /></span>
              记住此设备
            </label>
          </div>

          <button
            type="submit"
            className={`auth-btn${loading ? ' loading' : ''}`}
            disabled={loading}
          >
            <span className="auth-btn-text">验证身份</span>
            <span className="auth-spinner" />
          </button>
        </form>

        <div className="auth-footer">
          <span className="auth-chip">系统在线</span>
          <span className="auth-version">v0.1.0</span>
        </div>
      </div>
    </div>
  );
}
