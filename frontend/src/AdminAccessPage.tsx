import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  Check,
  Copy,
  History,
  KeyRound,
  Plus,
  RefreshCw,
  Search,
  Shield,
  ShieldCheck,
  UserCog,
  Users,
} from 'lucide-react';
import { api } from './api';
import type { AuthUser } from './types';

type Props = {
  profile: AuthUser;
  notify: (message: string, error?: boolean) => void;
};

type Role = {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  is_system: boolean;
  is_active: boolean;
  users_count: number;
  permissions: Record<string, string>;
};

type Permission = {
  key: string;
  description: string;
};

type UserRow = {
  id: number;
  username: string;
  roles: string[];
  permissions: Record<string, string>;
  customer_id: number | null;
  telegram_user_id: string | null;
  is_active: boolean;
  is_owner: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
};

type SessionRow = {
  id: number;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  user_agent: string | null;
  is_active: boolean;
  is_current: boolean;
};

type Client = {
  id: number;
  name: string;
};

type Scope = 'all' | 'assigned' | 'own_customer';

const scopeLabels: Record<Scope, string> = {
  all: 'Все записи',
  assigned: 'Назначенные записи',
  own_customer: 'Собственный клиент',
};

const can = (u: AuthUser, key: string) =>
  u.is_owner || u.permissions['*'] === 'all' || Object.prototype.hasOwnProperty.call(u.permissions, key);

export default function AdminAccessPage({ profile, notify }: Props) {
  const [tab, setTab] = useState<'users' | 'roles'>(can(profile, 'admin:users:view') ? 'users' : 'roles');
  const [users, setUsers] = useState<UserRow[]>([]);
  const [userTotal, setUserTotal] = useState(0);
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);

  const [sessionTarget, setSessionTarget] = useState<UserRow | null>(null);
  const [sessionRows, setSessionRows] = useState<SessionRow[]>([]);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [sessionError, setSessionError] = useState('');

  const [newUser, setNewUser] = useState(false);
  const [username, setUsername] = useState('');
  const [newRole, setNewRole] = useState('manager');
  const [customerId, setCustomerId] = useState('');
  const [newTelegramId, setNewTelegramId] = useState('');
  const [userBusy, setUserBusy] = useState(false);
  const [temporaryCredential, setTemporaryCredential] = useState<{ username: string; password: string } | null>(null);

  const [editingUser, setEditingUser] = useState<UserRow | null>(null);
  const [editRole, setEditRole] = useState('manager');
  const [editCustomer, setEditCustomer] = useState('');
  const [editTelegramId, setEditTelegramId] = useState('');

  const [roleEdit, setRoleEdit] = useState<Role | null>(null);
  const [roleEditorOpen, setRoleEditorOpen] = useState(false);
  const [roleName, setRoleName] = useState('');
  const [roleSlug, setRoleSlug] = useState('');
  const [roleDescription, setRoleDescription] = useState('');
  const [matrix, setMatrix] = useState<Record<string, Scope | ''>>({});
  const [roleBusy, setRoleBusy] = useState(false);

  const mayViewUsers = can(profile, 'admin:users:view');
  const mayCreateUsers = can(profile, 'admin:users:create');
  const mayEditUsers = can(profile, 'admin:users:edit');
  const maySuspend = can(profile, 'admin:users:suspend');
  const mayReset = can(profile, 'admin:users:reset_password');
  const maySessions = can(profile, 'admin:users:sessions');
  const mayViewRoles = can(profile, 'admin:roles:view');
  const mayCreateRoles = can(profile, 'admin:roles:create');
  const mayEditRoles = can(profile, 'admin:roles:edit');

  const isOwnerOnlyPermission = (key: string) =>
    key.startsWith('admin:') || key === 'settings:view' || key === 'settings:edit';

  const assignableRoles = roles.filter(
    (role) =>
      role.is_active &&
      role.slug !== 'owner' &&
      (profile.is_owner || (role.is_system && !Object.keys(role.permissions).some(isOwnerOnlyPermission))),
  );

  const load = useCallback(async () => {
    setBusy(true);
    setError('');
    const params = new URLSearchParams({ limit: '50', offset: String(offset) });
    if (query) params.set('q', query);
    try {
      const jobs: Promise<unknown>[] = [];
      if (mayViewUsers) {
        jobs.push(api.get<{ items: UserRow[]; total: number }>(`/api/v1/admin/users?${params}`));
      } else {
        jobs.push(Promise.resolve({ items: [], total: 0 }));
      }
      if (mayViewRoles) {
        jobs.push(api.get<Role[]>('/api/v1/admin/roles'), api.get<Permission[]>('/api/v1/admin/permissions'));
      } else {
        jobs.push(Promise.resolve([]), Promise.resolve([]));
      }
      jobs.push(api.get<Client[]>('/api/v1/clients?limit=250').catch(() => []));
      const [us, rs, ps, cs] = (await Promise.all(jobs)) as [
        { items: UserRow[]; total: number },
        Role[],
        Permission[],
        Client[],
      ];
      setUsers(us.items);
      setUserTotal(us.total);
      setRoles(rs);
      setPermissions(ps);
      setClients(cs.filter((c) => !(c as Client & { is_archived?: boolean }).is_archived));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось загрузить учётные записи и матрицу ролей.');
    } finally {
      setBusy(false);
    }
  }, [offset, query, refreshKey, mayViewUsers, mayViewRoles]);

  useEffect(() => {
    void load();
  }, [load]);

  function startRole(role?: Role, clone = false) {
    setRoleEditorOpen(true);
    if (role) {
      setRoleEdit(clone ? null : role);
      setRoleName(clone ? `${role.name} — копия` : role.name);
      setRoleSlug(clone ? `${role.slug}-copy` : role.slug);
      setRoleDescription(role.description || '');
      setMatrix({ ...role.permissions } as Record<string, Scope>);
    } else {
      setRoleEdit(null);
      setRoleName('');
      setRoleSlug('');
      setRoleDescription('');
      setMatrix({});
    }
    setError('');
  }

  async function createAccount(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setUserBusy(true);
    setError('');
    try {
      const result = await api.post<{ user: UserRow; temporary_password: string }>('/api/v1/admin/users', {
        username: username.trim(),
        role_slugs: [newRole],
        customer_id: newRole === 'client' && customerId ? Number(customerId) : null,
        telegram_user_id: newTelegramId.trim() || null,
      });
      setTemporaryCredential({ username: result.user.username, password: result.temporary_password });
      setUsername('');
      setCustomerId('');
      setNewTelegramId('');
      setNewUser(false);
      notify('Учётная запись создана. Временный пароль выдан однократно.');
      setRefreshKey((n) => n + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось создать учётную запись.');
    } finally {
      setUserBusy(false);
    }
  }

  async function saveUser(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!editingUser) return;
    setUserBusy(true);
    setError('');
    try {
      await api.patch(`/api/v1/admin/users/${editingUser.id}`, {
        role_slugs: [editRole],
        customer_id: editCustomer ? Number(editCustomer) : null,
        telegram_user_id: editTelegramId.trim() || null,
      });
      setEditingUser(null);
      notify('Параметры допуска учётной записи обновлены');
      setRefreshKey((n) => n + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось сохранить параметры учётной записи.');
    } finally {
      setUserBusy(false);
    }
  }

  async function toggleUser(user: UserRow) {
    try {
      await api.patch(`/api/v1/admin/users/${user.id}`, { is_active: !user.is_active });
      notify(user.is_active ? 'Учётная запись деактивирована' : 'Учётная запись активирована');
      setRefreshKey((n) => n + 1);
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : 'Не удалось изменить статус активности.', true);
    }
  }

  async function resetPassword(user: UserRow) {
    if (!window.confirm(`Выпустить новый временный пароль для ${user.username}? Все активные сессии будут отозваны.`)) {
      return;
    }
    try {
      const result = await api.post<{ username: string; temporary_password: string }>(
        `/api/v1/admin/users/${user.id}/reset-password`,
      );
      setTemporaryCredential({ username: result.username, password: result.temporary_password });
      notify('Пароль сброшен. Передайте временный пароль по защищённому каналу.');
      setRefreshKey((n) => n + 1);
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : 'Не удалось выполнить сброс пароля.', true);
    }
  }

  async function saveRole(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setRoleBusy(true);
    setError('');
    const chosen = Object.fromEntries(
      Object.entries(matrix).filter((entry): entry is [string, Scope] => entry[1] !== ''),
    );
    try {
      if (roleEdit) {
        await api.patch(`/api/v1/admin/roles/${roleEdit.id}`, {
          name: roleName.trim(),
          description: roleDescription.trim() || null,
          permissions: chosen,
        });
      } else {
        await api.post('/api/v1/admin/roles', {
          slug: roleSlug.trim(),
          name: roleName.trim(),
          description: roleDescription.trim() || null,
          permissions: chosen,
        });
      }
      notify(roleEdit ? 'Конфигурация роли обновлена' : 'Создана пользовательская роль');
      setRoleEditorOpen(false);
      setRoleEdit(null);
      setRoleName('');
      setRoleSlug('');
      setRoleDescription('');
      setMatrix({});
      setRefreshKey((n) => n + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось сохранить роль.');
    } finally {
      setRoleBusy(false);
    }
  }

  async function deactivateRole(role: Role) {
    if (!window.confirm(`Деактивировать роль «${role.name}»? Учётные записи с этой ролью утратят её полномочия.`)) {
      return;
    }
    try {
      await api.patch(`/api/v1/admin/roles/${role.id}`, { is_active: false });
      notify('Роль деактивирована');
      setRefreshKey((n) => n + 1);
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : 'Не удалось деактивировать роль.', true);
    }
  }

  async function copyCredential() {
    if (!temporaryCredential) return;
    try {
      await navigator.clipboard.writeText(temporaryCredential.password);
      notify('Временный пароль скопирован в буфер обмена.');
    } catch {
      setError('Буфер обмена недоступен. Выделите и скопируйте пароль вручную.');
    }
  }

  async function openSessions(user: UserRow) {
    setSessionTarget(user);
    setSessionRows([]);
    setSessionBusy(true);
    setSessionError('');
    try {
      const result = await api.get<{ items: SessionRow[]; total: number }>(
        `/api/v1/admin/users/${user.id}/sessions?limit=50&offset=0`,
      );
      setSessionRows(result.items);
    } catch (reason) {
      setSessionError(reason instanceof Error ? reason.message : 'Не удалось загрузить реестр сессий.');
    } finally {
      setSessionBusy(false);
    }
  }

  async function revokeSession(row: SessionRow) {
    if (!sessionTarget || !row.is_active || row.is_current) return;
    if (!window.confirm(`Принудительно отозвать сессию #${row.id} оператора ${sessionTarget.username}?`)) return;
    try {
      await api.post(`/api/v1/admin/users/${sessionTarget.id}/sessions/${row.id}/revoke`, {});
      notify('Сессия отозвана');
      await openSessions(sessionTarget);
      setRefreshKey((n) => n + 1);
    } catch (reason) {
      setSessionError(reason instanceof Error ? reason.message : 'Не удалось отозвать сессию.');
    }
  }

  if (!mayViewUsers && !mayViewRoles) {
    return (
      <section className="panel access-denied">
        <Shield size={26} />
        <h2>Доступ ограничен</h2>
        <p>Текущая учётная запись не обладает полномочиями на просмотр реестра операторов и матрицы ролей.</p>
      </section>
    );
  }

  return (
    <section className="access-workspace">
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}
      <div className="access-toolbar">
        <div className="access-tabs" role="tablist" aria-label="Управление доступом">
          {mayViewUsers && (
            <button
              role="tab"
              aria-selected={tab === 'users'}
              className={tab === 'users' ? 'access-tab access-tab-active' : 'access-tab'}
              onClick={() => {
                setTab('users');
                setRoleEdit(null);
              }}
            >
              <Users size={15} /> Учётные записи
            </button>
          )}
          {mayViewRoles && (
            <button
              role="tab"
              aria-selected={tab === 'roles'}
              className={tab === 'roles' ? 'access-tab access-tab-active' : 'access-tab'}
              onClick={() => {
                setTab('roles');
                setEditingUser(null);
              }}
            >
              <ShieldCheck size={15} /> Матрица ролей и допусков
            </button>
          )}
        </div>
        <button className="secondary-button" onClick={() => setRefreshKey((n) => n + 1)}>
          <RefreshCw size={14} /> Обновить реестр
        </button>
      </div>

      {temporaryCredential && (
        <section className="credential-reveal" aria-live="polite">
          <div>
            <strong>Одноразовый временный пароль для {temporaryCredential.username}</strong>
            <p>Отображается только в момент выпуска. При первом входе система потребует его замены.</p>
            <code>{temporaryCredential.password}</code>
          </div>
          <button className="secondary-button" onClick={() => void copyCredential()}>
            <Copy size={14} /> Скопировать
          </button>
          <button className="text-button" onClick={() => setTemporaryCredential(null)} aria-label="Скрыть временный пароль">
            Скрыть
          </button>
        </section>
      )}

      {tab === 'users' && (
        <>
          <div className="access-list-heading">
            <div>
              <h2>Реестр учётных записей</h2>
              <p>Контроль сессий, ролевых допусков и привязки к Telegram Mini App осуществляется на стороне сервера.</p>
            </div>
            {mayCreateUsers && (
              <button className="primary-button" onClick={() => setNewUser((v) => !v)}>
                <Plus size={15} />
                {newUser ? 'Закрыть форму' : 'Создать аккаунт'}
              </button>
            )}
          </div>

          {newUser && (
            <form className="panel access-form" onSubmit={createAccount}>
              <h3>Регистрация новой учётной записи</h3>
              <div className="form-grid">
                <label className="form-field">
                  <span>Имя пользователя</span>
                  <input
                    required
                    minLength={3}
                    maxLength={100}
                    pattern="[A-Za-z0-9_.-]+"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="operator.login"
                  />
                </label>
                <label className="form-field">
                  <span>Роль</span>
                  <select
                    value={newRole}
                    onChange={(e) => {
                      setNewRole(e.target.value);
                      setCustomerId('');
                    }}
                  >
                    {assignableRoles.map((r) => (
                      <option key={r.slug} value={r.slug}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-field">
                  <span>Telegram User ID (необязательно)</span>
                  <input
                    pattern="[0-9]+"
                    maxLength={64}
                    value={newTelegramId}
                    onChange={(e) => setNewTelegramId(e.target.value)}
                    placeholder="Числовой ID для входа через Mini App"
                  />
                </label>
                {newRole === 'client' && (
                  <label className="form-field">
                    <span>Привязанный клиент</span>
                    <select required value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
                      <option value="">Выбрать клиента</option>
                      {clients.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
              <p className="field-hint">
                Временный криптографический пароль генерируется сервером и выдаётся однократно.
              </p>
              <button className="primary-button" disabled={userBusy}>
                {userBusy ? 'Создание…' : 'Выпустить учётную запись'}
              </button>
            </form>
          )}

          <form
            className="search-field access-search"
            onSubmit={(e) => {
              e.preventDefault();
              setOffset(0);
              setQuery(q.trim());
            }}
          >
            <Search size={15} />
            <input
              aria-label="Поиск аккаунтов"
              placeholder="Поиск по логину оператора…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <button type="submit">Найти</button>
          </form>

          {busy ? (
            <div className="loading">Загрузка реестра учётных записей…</div>
          ) : users.length ? (
            <div className="access-user-list">
              {users.map((u) => (
                <article className="panel access-user-card" key={u.id}>
                  <div className="access-user-summary">
                    <span className="access-user-avatar">
                      <UserCog size={17} />
                    </span>
                    <div>
                      <strong>
                        {u.username}
                        {u.is_owner && <span className="owner-tag">Владелец</span>}
                        {u.telegram_user_id && <span className="system-tag">TG ID: {u.telegram_user_id}</span>}
                      </strong>
                      <p>
                        {u.roles.map((r) => roles.find((role) => role.slug === r)?.name || r).join(', ') ||
                          'Нет активных ролей'}
                      </p>
                      <small>
                        {!u.is_active
                          ? 'Учётная запись деактивирована'
                          : u.must_change_password
                            ? 'Требуется смена временного пароля'
                            : u.last_login_at
                              ? `Последняя авторизация: ${new Date(u.last_login_at).toLocaleString('ru-RU')}`
                              : 'Вход ещё не выполнялся'}
                      </small>
                    </div>
                  </div>
                  <div className="access-user-actions">
                    {mayEditUsers && !u.is_owner && (
                      <button
                        className="secondary-button"
                        onClick={() => {
                          setEditingUser(u);
                          setEditRole(u.roles.find((r) => r !== 'owner') || 'manager');
                          setEditCustomer(u.customer_id ? String(u.customer_id) : '');
                          setEditTelegramId(u.telegram_user_id || '');
                        }}
                      >
                        Изменить доступ
                      </button>
                    )}
                    {mayReset && (
                      <button
                        className="secondary-button"
                        disabled={!u.is_active || (!profile.is_owner && u.is_owner)}
                        onClick={() => void resetPassword(u)}
                      >
                        <KeyRound size={14} /> Сбросить пароль
                      </button>
                    )}
                    {maySessions && (!u.is_owner || profile.is_owner) && (
                      <button className="secondary-button" onClick={() => void openSessions(u)}>
                        <History size={14} /> Сессии
                      </button>
                    )}
                    {maySuspend && !u.is_owner && (
                      <button className="secondary-button" onClick={() => void toggleUser(u)}>
                        {u.is_active ? 'Отключить' : 'Активировать'}
                      </button>
                    )}
                  </div>

                  {editingUser?.id === u.id && (
                    <form className="access-inline-form" onSubmit={saveUser}>
                      <label className="form-field">
                        <span>Роль</span>
                        <select value={editRole} onChange={(e) => setEditRole(e.target.value)}>
                          {assignableRoles.map((r) => (
                            <option key={r.slug} value={r.slug}>
                              {r.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="form-field">
                        <span>Привязанный клиент</span>
                        <select value={editCustomer} onChange={(e) => setEditCustomer(e.target.value)}>
                          <option value="">Нет привязки</option>
                          {clients.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="form-field">
                        <span>Telegram User ID (необязательно)</span>
                        <input
                          pattern="[0-9]+"
                          maxLength={64}
                          value={editTelegramId}
                          onChange={(e) => setEditTelegramId(e.target.value)}
                          placeholder="Числовой Telegram ID"
                        />
                      </label>
                      <button className="primary-button" disabled={userBusy}>
                        Сохранить
                      </button>
                      <button className="secondary-button" type="button" onClick={() => setEditingUser(null)}>
                        Отмена
                      </button>
                    </form>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <div className="portal-panel portal-empty-panel">
              <Users size={24} />
              <h2>Учётные записи не найдены</h2>
              <p>Создайте учётную запись сотрудника или привяжите клиентский профиль.</p>
            </div>
          )}

          {userTotal > 50 && (
            <div className="orders-pagination">
              <span>
                {Math.min(offset + 1, userTotal)}–{Math.min(offset + users.length, userTotal)} из {userTotal}
              </span>
              <div>
                <button
                  className="secondary-button"
                  disabled={!offset}
                  onClick={() => setOffset((n) => Math.max(0, n - 50))}
                >
                  Назад
                </button>
                <button
                  className="secondary-button"
                  disabled={offset + 50 >= userTotal}
                  onClick={() => setOffset((n) => n + 50)}
                >
                  Дальше
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'roles' && (
        <>
          <div className="access-list-heading">
            <div>
              <h2>Роли и матрица допусков</h2>
              <p>Принцип минимальных привилегий с серверной фильтрацией по области данных (Scope).</p>
            </div>
            {mayCreateRoles && (
              <button className="primary-button" onClick={() => startRole()}>
                <Plus size={15} /> Новая роль
              </button>
            )}
          </div>

          <div className="role-list">
            {roles.map((role) => (
              <article className={`panel role-card ${!role.is_active ? 'role-inactive' : ''}`} key={role.id}>
                <div className="role-card-heading">
                  <div>
                    <h3>
                      {role.name}
                      {role.is_system && <span className="system-tag">Системная</span>}
                    </h3>
                    <p>{role.description || 'Описание не задано'}</p>
                    <small>
                      {role.slug} · {role.users_count} аккаунт(ов) · {role.is_active ? 'Активна' : 'Отключена'}
                    </small>
                  </div>
                  <div className="access-user-actions">
                    {mayEditRoles && !role.is_system && (
                      <button className="secondary-button" onClick={() => startRole(role)}>
                        <Shield size={14} /> Редактировать
                      </button>
                    )}
                    {mayCreateRoles && (
                      <button className="secondary-button" onClick={() => startRole(role, true)}>
                        Копировать
                      </button>
                    )}
                    {mayEditRoles && !role.is_system && role.is_active && (
                      <button className="secondary-button" onClick={() => void deactivateRole(role)}>
                        Отключить
                      </button>
                    )}
                  </div>
                </div>
                <div className="role-permission-summary">
                  {Object.entries(role.permissions)
                    .slice(0, 7)
                    .map(([key, scope]) => (
                      <span key={key}>
                        <Check size={12} />
                        {key}
                        <small>{scopeLabels[scope as Scope] || scope}</small>
                      </span>
                    ))}
                  {Object.keys(role.permissions).length > 7 && (
                    <small>Ещё прав: {Object.keys(role.permissions).length - 7}</small>
                  )}
                  {!Object.keys(role.permissions).length && <span>Нет назначенных разрешений</span>}
                </div>
              </article>
            ))}
          </div>

          {roleEditorOpen && (
            <form className="panel role-editor" onSubmit={saveRole}>
              <div className="panel-heading">
                <div>
                  <h2>{roleEdit ? 'Редактирование роли' : 'Создание пользовательской роли'}</h2>
                  <p>Назначайте только минимально необходимые разрешения для рабочего контура.</p>
                </div>
                <ShieldCheck size={18} />
              </div>
              <div className="form-grid">
                <label className="form-field">
                  <span>Системный идентификатор (slug)</span>
                  <input
                    required
                    pattern="[a-z][a-z0-9_-]+"
                    minLength={2}
                    maxLength={50}
                    disabled={!!roleEdit}
                    value={roleSlug}
                    onChange={(e) => setRoleSlug(e.target.value)}
                  />
                </label>
                <label className="form-field">
                  <span>Название роли</span>
                  <input
                    required
                    minLength={2}
                    maxLength={100}
                    value={roleName}
                    onChange={(e) => setRoleName(e.target.value)}
                  />
                </label>
                <label className="form-field field-full">
                  <span>Описание</span>
                  <input
                    maxLength={500}
                    value={roleDescription}
                    onChange={(e) => setRoleDescription(e.target.value)}
                  />
                </label>
              </div>
              <div className="permission-matrix">
                <div className="permission-matrix-head">
                  <span>Разрешение</span>
                  <span>Область доступа (Scope)</span>
                </div>
                {permissions
                  .filter((p) => profile.is_owner || !isOwnerOnlyPermission(p.key))
                  .map((p) => (
                    <label className="permission-row" key={p.key}>
                      <span>
                        <strong>{p.key}</strong>
                        <small>{p.description}</small>
                      </span>
                      <select
                        aria-label={`Область доступа: ${p.key}`}
                        value={matrix[p.key] || ''}
                        onChange={(e) =>
                          setMatrix((current) => ({ ...current, [p.key]: e.target.value as Scope | '' }))
                        }
                      >
                        <option value="">Не выдавать</option>
                        <option value="all">Все записи</option>
                        <option value="assigned">Назначенные записи</option>
                        <option value="own_customer">Записи своего клиента</option>
                      </select>
                    </label>
                  ))}
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    setRoleEditorOpen(false);
                    setRoleEdit(null);
                  }}
                >
                  Отмена
                </button>
                <button
                  className="primary-button"
                  disabled={roleBusy || (!mayEditRoles && !!roleEdit) || (!mayCreateRoles && !roleEdit)}
                >
                  {roleBusy ? 'Сохранение…' : roleEdit ? 'Сохранить роль' : 'Создать роль'}
                </button>
              </div>
            </form>
          )}
        </>
      )}

      {sessionTarget && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSessionTarget(null);
          }}
        >
          <section
            className="modal-card session-manager"
            role="dialog"
            aria-modal="true"
            aria-labelledby="session-manager-title"
          >
            <div className="modal-heading">
              <div>
                <p className="eyebrow">КОНТРОЛЬ СЕССИЙ</p>
                <h2 id="session-manager-title">Сессии · {sessionTarget.username}</h2>
              </div>
              <button
                className="icon-button"
                type="button"
                aria-label="Закрыть список сессий"
                onClick={() => setSessionTarget(null)}
              >
                ×
              </button>
            </div>
            <div className="session-manager-body">
              {sessionError && (
                <p className="field-error" role="alert">
                  {sessionError}
                </p>
              )}
              {sessionBusy ? (
                <div className="loading">Загрузка сессий…</div>
              ) : sessionRows.length ? (
                <div className="session-list">
                  {sessionRows.map((row) => (
                    <article className="session-row" key={row.id}>
                      <div className="session-row-main">
                        <strong>
                          Сессия #{row.id}
                          {row.is_current && <span className="system-tag">Текущая</span>}
                        </strong>
                        <p>Создана: {new Date(row.created_at).toLocaleString('ru-RU')}</p>
                        <p>Истекает: {new Date(row.expires_at).toLocaleString('ru-RU')}</p>
                        <small>{row.user_agent || 'User-Agent не передан'}</small>
                        <span className={`badge ${row.is_active ? 'badge-green' : 'badge-slate'}`}>
                          {row.is_current
                            ? 'Текущая активная сессия'
                            : row.is_active
                              ? 'Активна'
                              : row.revoked_at
                                ? 'Отозвана'
                                : 'Истекла или неактивна'}
                        </span>
                      </div>
                      <button
                        className="secondary-button"
                        disabled={!row.is_active || row.is_current}
                        onClick={() => void revokeSession(row)}
                      >
                        {row.is_current ? 'Текущая' : 'Отозвать'}
                      </button>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="portal-empty">Для данной учётной записи не найдено сессий.</div>
              )}
            </div>
            <div className="modal-footer">
              <button className="secondary-button" type="button" onClick={() => setSessionTarget(null)}>
                Закрыть
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
