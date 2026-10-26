import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { AlertCircle, KeyRound, LogOut, ShieldCheck } from 'lucide-react';
import { api, ApiError } from './api';
import App from './App';
import LoginScreen from './LoginScreen';
import PortalApp from './PortalApp';
import { initTelegramMiniApp } from './telegram';
import type { AuthUser } from './types';

function ChangePassword({
  user,
  onChanged,
  onLogout,
}: {
  user: AuthUser;
  onChanged: (user: AuthUser) => void;
  onLogout: () => void;
}) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    if (next.length < 12) {
      setError('Новый пароль должен содержать минимум 12 символов.');
      return;
    }
    if (next !== confirm) {
      setError('Введённые пароли не совпадают.');
      return;
    }
    if (next === current) {
      setError('Новый пароль должен отличаться от временного.');
      return;
    }
    setBusy(true);
    try {
      const updated = await api.post<AuthUser>('/api/v1/auth/change-password', {
        current_password: current,
        new_password: next,
      });
      setCurrent('');
      setNext('');
      setConfirm('');
      onChanged(updated);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось изменить пароль.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="password-heading">
        <div className="auth-brand">
          <span className="auth-brand-mark">
            <KeyRound size={22} />
          </span>
          <span>
            <strong>BOTVEX</strong>
            <small>КОНТУР БЕЗОПАСНОСТИ</small>
          </span>
        </div>
        <p className="auth-eyebrow">РЕГЛАМЕНТ БЕЗОПАСНОСТИ // ОБЯЗАТЕЛЬНАЯ СМЕНА КЛЮЧА</p>
        <h1 id="password-heading">Замена временного пароля</h1>
        <p className="auth-intro">
          Для учётной записи <strong>{user.username}</strong> установлен одноразовый временный пароль. Доступ к диспетчерским разделам заблокирован до установки постоянного пароля.
        </p>
        {error && (
          <div className="auth-alert" role="alert">
            <AlertCircle size={16} />
            {error}
          </div>
        )}
        <form className="auth-form" onSubmit={submit}>
          <label className="form-field">
            <span>Текущий временный пароль</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </label>
          <label className="form-field">
            <span>Новый постоянный пароль</span>
            <input
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              required
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
            <small className="field-hint">
              Минимум 12 символов. Используйте уникальную парольную фразу.
            </small>
          </label>
          <label className="form-field">
            <span>Подтверждение нового пароля</span>
            <input
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </label>
          <button className="primary-button auth-submit" type="submit" disabled={busy}>
            {busy ? 'Применение учётных данных…' : 'Подтвердить и активировать доступ'}
          </button>
        </form>
        <div className="auth-security">
          <ShieldCheck size={17} />
          <span>
            При установке нового пароля все прочие активные сессии данной учётной записи принудительно отзываются.
          </span>
        </div>
        <button className="secondary-button auth-logout" onClick={onLogout}>
          <LogOut size={15} />
          Завершить сеанс
        </button>
      </section>
    </main>
  );
}

export default function AuthGate() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [connectionError, setConnectionError] = useState('');

  const refresh = useCallback(async () => {
    setConnectionError('');
    try {
      const current = await api.get<AuthUser>('/api/v1/auth/me');
      setUser(current);
      return;
    } catch (reason) {
      if (!(reason instanceof ApiError) || reason.status !== 401) {
        setConnectionError(
          reason instanceof Error ? reason.message : 'Не удалось установить соединение с сервером управления.',
        );
        return;
      }
    }
    try {
      const telegramUser = await api.telegramLogin<AuthUser>();
      setUser(telegramUser);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status >= 500) {
        setConnectionError(reason.message);
      }
    }
  }, []);

  useEffect(() => {
    const cleanupTelegram = initTelegramMiniApp();
    let active = true;
    void refresh().finally(() => {
      if (active) setReady(true);
    });
    return () => {
      active = false;
      cleanupTelegram();
    };
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await api.post('/api/v1/auth/logout');
    } finally {
      setUser(null);
      setConnectionError('');
    }
  }, []);

  if (!ready) {
    return (
      <main className="auth-shell">
        <div className="auth-loading" role="status">
          Инициализация защищённого контура управления BOTVEX · Проверка серверной сессии и матрицы допусков RBAC…
        </div>
      </main>
    );
  }
  if (!user) return <LoginScreen onLogin={setUser} connectionError={connectionError} />;
  if (user.must_change_password) {
    return <ChangePassword user={user} onChanged={setUser} onLogout={() => void logout()} />;
  }
  if (user.roles.includes('client') && !user.is_owner) {
    return <PortalApp user={user} onLogout={() => void logout()} />;
  }
  return <App profile={user} onLogout={() => void logout()} />;
}
