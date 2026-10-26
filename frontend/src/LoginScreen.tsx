import { useState, type FormEvent } from 'react';
import { ArrowRight, Code2, LockKeyhole, ShieldCheck } from 'lucide-react';
import { api } from './api';
import type { AuthUser } from './types';

type Props = {
  onLogin: (user: AuthUser) => void;
  connectionError?: string;
};

export default function LoginScreen({ onLogin, connectionError }: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const user = await api.post<AuthUser>('/api/v1/auth/login', {
        username: username.trim(),
        password,
      });
      onLogin(user);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось выполнить вход в систему.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="login-heading">
        <div className="auth-brand">
          <span className="auth-brand-mark">
            <Code2 size={23} />
          </span>
          <span>
            <strong>BOTVEX</strong>
            <small>CONTROL CENTER</small>
          </span>
        </div>
        <p className="auth-eyebrow">BOTVEX CONTROL CENTER // АВТОРИЗАЦИЯ ОПЕРАТОРА</p>
        <h1 id="login-heading">Вход в систему управления операциями</h1>
        <p className="auth-intro">
          Доступ разрешён только авторизованным сотрудникам и верифицированным контрагентам. Все действия фиксируются в журнале безопасности.
        </p>
        {connectionError && (
          <div className="auth-alert" role="alert">
            {connectionError}
          </div>
        )}
        {error && (
          <div className="auth-alert" role="alert">
            {error}
          </div>
        )}
        <form className="auth-form" onSubmit={submit}>
          <label className="form-field">
            <span>Учётный идентификатор (логин)</span>
            <input
              autoComplete="username"
              name="username"
              required
              maxLength={100}
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Введите логин оператора"
              autoFocus
            />
          </label>
          <label className="form-field">
            <span>Пароль доступа</span>
            <input
              autoComplete="current-password"
              name="password"
              type="password"
              required
              maxLength={1024}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Введите пароль"
            />
          </label>
          <button className="primary-button auth-submit" type="submit" disabled={busy}>
            {busy ? 'Верификация учётных данных…' : 'Авторизоваться в системе'}
            {!busy && <ArrowRight size={16} />}
          </button>
        </form>
        <div className="auth-security">
          <ShieldCheck size={17} />
          <span>
            Контур безопасности активен. Сессия изолирована в HttpOnly-cookie (SHA-256), полномочия проверяются сервером на каждом запросе.
          </span>
        </div>
        <p className="auth-help">
          <LockKeyhole size={13} />
          Самостоятельная регистрация отключена. Учётные записи выпускаются администратором безопасности.
        </p>
      </section>
      <footer className="auth-footer">
        BOTVEX OPERATIONS // ЦЕНТРАЛЬНЫЙ ДИСПЕТЧЕРСКИЙ КОНТУР
      </footer>
    </main>
  );
}
