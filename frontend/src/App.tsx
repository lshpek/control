import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import {
  Activity,
  AlertCircle,
  Archive,
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  BriefcaseBusiness,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Code2,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  LoaderCircle,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  TerminalSquare,
  Users,
  X,
  Zap,
} from 'lucide-react';
import { api } from './api';
import type { AuthUser, DashboardData, Entity, ProjectAssignment } from './types';
import { formatDate as fmtDate, formatDateTime as fmtDateTime, isOverdue } from './formatting';
import OrdersPage from './OrdersPage';
import AdminAccessPage from './AdminAccessPage';

type Section =
  | 'dashboard'
  | 'clients'
  | 'projects'
  | 'tasks'
  | 'services'
  | 'activity'
  | 'logs'
  | 'tests'
  | 'deployments'
  | 'settings'
  | 'orders'
  | 'access';

type AppProps = {
  profile?: AuthUser;
  onLogout?: () => void;
};

type FieldType = 'text' | 'textarea' | 'select' | 'date' | 'number';

type Field = {
  name: string;
  label: string;
  type?: FieldType;
  required?: boolean;
  options?: Array<{ value: string; label: string }>;
  placeholder?: string;
  hint?: string;
};

type Column = {
  key: string;
  label: string;
  format?: (value: unknown, row: Record<string, unknown>) => string;
};

type Config = {
  section: Section;
  title: string;
  singular: string;
  endpoint: string;
  icon: typeof Users;
  fields: Field[];
  columns: Column[];
  archive?: boolean;
};

const API = '/api/v1';

const labels: Record<string, string> = {
  lead: 'Лид',
  active: 'Активен',
  paused: 'На паузе',
  archived: 'В архиве',
  planning: 'Планирование',
  on_hold: 'Приостановлен',
  completed: 'Завершён',
  low: 'Низкий',
  normal: 'Обычный',
  high: 'Высокий',
  urgent: 'Срочный',
  backlog: 'В очереди',
  in_progress: 'В работе',
  blocked: 'Заблокирована',
  review: 'На проверке',
  done: 'Готово',
  bot: 'Telegram-бот',
  api: 'API',
  external: 'Внешний сервис',
  manual: 'Вручную',
  probe: 'HTTP-проверка',
  unknown: 'Неизвестно',
  healthy: 'Штатный режим',
  degraded: 'Деградация',
  down: 'Недоступен',
  debug: 'Отладка',
  info: 'Информация',
  warning: 'Предупреждение',
  error: 'Ошибка',
  passed: 'Успешно',
  failed: 'Ошибка',
  skipped: 'Пропущен',
  recorded: 'Записан вручную',
  success: 'Успешно (вручную)',
  rolled_back: 'Откат',
  local: 'Локально',
  production: 'Production',
  staging: 'Staging',
  created: 'Создано',
  updated: 'Изменено',
  archived_action: 'Архивировано',
  probed: 'Проверено',
};

const label = (v: unknown) =>
  labels[String(v ?? '')] || (v === null || v === undefined || v === '' ? '—' : String(v));

const idLabel = (v: unknown) => (v ? `#${v}` : '—');

const configs: Record<'clients' | 'projects' | 'tasks' | 'services' | 'logs' | 'tests' | 'deployments', Config> = {
  clients: {
    section: 'clients',
    title: 'Клиенты',
    singular: 'клиента',
    endpoint: `${API}/clients`,
    icon: Users,
    archive: true,
    fields: [
      { name: 'name', label: 'Наименование контрагента', required: true, placeholder: 'Например, FlowLead' },
      { name: 'contact_person', label: 'Контактное лицо', placeholder: 'ФИО представителя' },
      { name: 'contacts', label: 'Каналы связи', placeholder: 'Telegram, email или телефон' },
      {
        name: 'status',
        label: 'Статус',
        type: 'select',
        options: [
          { value: 'lead', label: 'Лид' },
          { value: 'active', label: 'Активен' },
          { value: 'paused', label: 'На паузе' },
        ],
      },
      {
        name: 'notes',
        label: 'Операционные заметки',
        type: 'textarea',
        hint: 'Запрещено размещать пароли, криптографические ключи и токены доступа.',
      },
    ],
    columns: [
      { key: 'name', label: 'Клиент' },
      { key: 'contact_person', label: 'Контактное лицо' },
      { key: 'contacts', label: 'Контакты' },
      { key: 'status', label: 'Статус', format: (v) => label(v) },
      { key: 'updated_at', label: 'Обновлён', format: (v) => fmtDate(v) },
    ],
  },
  projects: {
    section: 'projects',
    title: 'Проекты',
    singular: 'проект',
    endpoint: `${API}/projects`,
    icon: BriefcaseBusiness,
    archive: true,
    fields: [
      { name: 'name', label: 'Наименование проекта', required: true, placeholder: 'Например, Order Bot' },
      { name: 'description', label: 'Описание контура', type: 'textarea' },
      { name: 'client_id', label: 'Контрагент', type: 'select', options: [] },
      {
        name: 'status',
        label: 'Статус',
        type: 'select',
        options: [
          { value: 'planning', label: 'Планирование' },
          { value: 'active', label: 'Активен' },
          { value: 'on_hold', label: 'Приостановлен' },
          { value: 'completed', label: 'Завершён' },
        ],
      },
      {
        name: 'priority',
        label: 'Приоритет',
        type: 'select',
        options: [
          { value: 'low', label: 'Низкий' },
          { value: 'normal', label: 'Обычный' },
          { value: 'high', label: 'Высокий' },
          { value: 'urgent', label: 'Срочный' },
        ],
      },
      { name: 'due_date', label: 'Целевой срок', type: 'date' },
      { name: 'repository_url', label: 'Репозиторий / ссылка', placeholder: 'https://github.com/…' },
      { name: 'environment', label: 'Среда эксплуатации', placeholder: 'local / staging / production' },
      {
        name: 'requirements',
        label: 'Технические требования (по одному в строке)',
        type: 'textarea',
        hint: 'Каждая непустая строка фиксируется как отдельное требование.',
      },
      { name: 'acceptance_criteria', label: 'Критерии приёмки (по одному в строке)', type: 'textarea' },
      { name: 'notes', label: 'Заметки', type: 'textarea' },
    ],
    columns: [
      { key: 'name', label: 'Проект' },
      { key: 'client_id', label: 'Клиент', format: idLabel },
      { key: 'status', label: 'Статус', format: (v) => label(v) },
      { key: 'priority', label: 'Приоритет', format: (v) => label(v) },
      { key: 'due_date', label: 'Дедлайн', format: (v) => fmtDate(v) },
    ],
  },
  tasks: {
    section: 'tasks',
    title: 'Задачи',
    singular: 'задачу',
    endpoint: `${API}/tasks`,
    icon: CheckCircle2,
    archive: true,
    fields: [
      { name: 'title', label: 'Наименование задачи', required: true, placeholder: 'Формулировка задачи' },
      { name: 'description', label: 'Техническое описание', type: 'textarea' },
      { name: 'project_id', label: 'Проект', type: 'select', options: [] },
      {
        name: 'status',
        label: 'Статус',
        type: 'select',
        options: [
          { value: 'backlog', label: 'В очереди' },
          { value: 'in_progress', label: 'В работе' },
          { value: 'blocked', label: 'Заблокирована' },
          { value: 'review', label: 'На проверке' },
          { value: 'done', label: 'Готово' },
        ],
      },
      {
        name: 'priority',
        label: 'Приоритет',
        type: 'select',
        options: [
          { value: 'low', label: 'Низкий' },
          { value: 'normal', label: 'Обычный' },
          { value: 'high', label: 'Высокий' },
          { value: 'urgent', label: 'Срочный' },
        ],
      },
      { name: 'due_date', label: 'Контрольный срок', type: 'date' },
      { name: 'notes', label: 'Заметки', type: 'textarea' },
    ],
    columns: [
      { key: 'title', label: 'Задача' },
      { key: 'project_id', label: 'Проект', format: idLabel },
      { key: 'status', label: 'Статус', format: (v) => label(v) },
      { key: 'priority', label: 'Приоритет', format: (v) => label(v) },
      { key: 'due_date', label: 'Срок', format: (v) => fmtDate(v) },
    ],
  },
  services: {
    section: 'services',
    title: 'Сервисы и боты',
    singular: 'сервис',
    endpoint: `${API}/services`,
    icon: Bot,
    archive: true,
    fields: [
      { name: 'name', label: 'Наименование узла', required: true, placeholder: 'Название бота / API' },
      {
        name: 'type',
        label: 'Тип узла',
        type: 'select',
        options: [
          { value: 'bot', label: 'Telegram-бот' },
          { value: 'api', label: 'API' },
          { value: 'external', label: 'Внешний сервис' },
        ],
      },
      { name: 'project_id', label: 'Проект', type: 'select', options: [] },
      { name: 'url', label: 'Базовый URL', placeholder: 'https://example.com' },
      {
        name: 'health_endpoint',
        label: 'Health endpoint (для SSRF-защищённой проверки)',
        placeholder: 'https://example.com/health',
      },
      { name: 'environment', label: 'Среда', placeholder: 'local / staging / production' },
      { name: 'version', label: 'Версия' },
      { name: 'hosting', label: 'Площадка размещения' },
      {
        name: 'status',
        label: 'Статус',
        type: 'select',
        options: [
          { value: 'unknown', label: 'Неизвестно' },
          { value: 'manual', label: 'Вручную' },
          { value: 'healthy', label: 'Штатный режим' },
          { value: 'degraded', label: 'Деградация' },
          { value: 'down', label: 'Недоступен' },
        ],
      },
      {
        name: 'notes',
        label: 'Заметки',
        type: 'textarea',
        hint: 'Запрещено указывать токены, пароли и секреты.',
      },
    ],
    columns: [
      { key: 'name', label: 'Сервис' },
      { key: 'type', label: 'Тип', format: (v) => label(v) },
      { key: 'status', label: 'Статус', format: (v) => label(v) },
      { key: 'status_source', label: 'Источник', format: (v) => label(v) },
      { key: 'hosting', label: 'Хостинг' },
    ],
  },
  logs: {
    section: 'logs',
    title: 'Журнал записей',
    singular: 'запись',
    endpoint: `${API}/log-entries`,
    icon: FileText,
    fields: [
      {
        name: 'level',
        label: 'Уровень важности',
        type: 'select',
        options: [
          { value: 'info', label: 'Информация' },
          { value: 'warning', label: 'Предупреждение' },
          { value: 'error', label: 'Ошибка' },
          { value: 'debug', label: 'Отладка' },
        ],
      },
      { name: 'service_id', label: 'Связанный сервис', type: 'select', options: [] },
      {
        name: 'message',
        label: 'Сообщение оператора',
        type: 'textarea',
        required: true,
        hint: 'Журнал операционных событий, зафиксированных вручную.',
      },
    ],
    columns: [
      { key: 'level', label: 'Уровень', format: (v) => label(v) },
      { key: 'message', label: 'Сообщение' },
      { key: 'service_id', label: 'Сервис', format: idLabel },
      { key: 'source', label: 'Источник', format: (v) => label(v) },
      { key: 'created_at', label: 'Время', format: (v) => fmtDateTime(v) },
    ],
  },
  tests: {
    section: 'tests',
    title: 'Реестр тестов',
    singular: 'набор тестов',
    endpoint: `${API}/test-suites`,
    icon: FlaskConical,
    fields: [
      { name: 'name', label: 'Наименование набора', required: true, placeholder: 'API smoke tests' },
      { name: 'project_id', label: 'Связанный проект', type: 'select', options: [] },
      { name: 'description', label: 'Описание проверок', type: 'textarea' },
    ],
    columns: [
      { key: 'name', label: 'Набор тестов' },
      { key: 'project_id', label: 'Проект', format: idLabel },
      { key: 'last_status', label: 'Последний результат', format: (v) => label(v) },
      { key: 'updated_at', label: 'Обновлён', format: (v) => fmtDateTime(v) },
    ],
  },
  deployments: {
    section: 'deployments',
    title: 'История релизов',
    singular: 'запись о релизе',
    endpoint: `${API}/deployments`,
    icon: Zap,
    fields: [
      { name: 'version', label: 'Версия / сборка', required: true, placeholder: 'v0.1.0' },
      { name: 'project_id', label: 'Связанный проект', type: 'select', options: [] },
      {
        name: 'environment',
        label: 'Контур размещения',
        type: 'select',
        options: [
          { value: 'local', label: 'Локально' },
          { value: 'staging', label: 'Staging' },
          { value: 'production', label: 'Production' },
        ],
      },
      {
        name: 'status',
        label: 'Статус выкладки',
        type: 'select',
        options: [
          { value: 'recorded', label: 'Записан вручную' },
          { value: 'success', label: 'Успешно (вручную)' },
          { value: 'failed', label: 'Ошибка (вручную)' },
          { value: 'rolled_back', label: 'Откат (вручную)' },
        ],
      },
      { name: 'url', label: 'URL релиза (необязательно)' },
      {
        name: 'note',
        label: 'Примечание к релизу',
        type: 'textarea',
        hint: 'Журнал фиксации релизов в операционном контуре.',
      },
    ],
    columns: [
      { key: 'version', label: 'Версия' },
      { key: 'project_id', label: 'Проект', format: idLabel },
      { key: 'environment', label: 'Среда', format: (v) => label(v) },
      { key: 'status', label: 'Статус', format: (v) => label(v) },
      { key: 'created_at', label: 'Запись', format: (v) => fmtDateTime(v) },
    ],
  },
};

const nav: Array<{ section: Section; label: string; icon: typeof LayoutDashboard; group: string }> = [
  { section: 'dashboard', label: 'Обзор', icon: LayoutDashboard, group: 'Рабочее пространство' },
  { section: 'clients', label: 'Клиенты', icon: Users, group: 'Рабочее пространство' },
  { section: 'orders', label: 'Заказы', icon: BriefcaseBusiness, group: 'Рабочее пространство' },
  { section: 'projects', label: 'Проекты', icon: BriefcaseBusiness, group: 'Рабочее пространство' },
  { section: 'tasks', label: 'Задачи', icon: CheckCircle2, group: 'Рабочее пространство' },
  { section: 'services', label: 'Сервисы и боты', icon: Bot, group: 'Инфраструктура' },
  { section: 'logs', label: 'Журнал записей', icon: FileText, group: 'Инфраструктура' },
  { section: 'tests', label: 'Реестр тестов', icon: FlaskConical, group: 'Инфраструктура' },
  { section: 'deployments', label: 'Релизы', icon: TerminalSquare, group: 'Инфраструктура' },
  { section: 'activity', label: 'Активность', icon: Activity, group: 'Система' },
  { section: 'access', label: 'Пользователи и доступ', icon: ShieldCheck, group: 'Система' },
  { section: 'settings', label: 'Настройки', icon: Gauge, group: 'Система' },
];

function hasPermission(profile: AuthUser | undefined, key: string): boolean {
  return (
    !profile ||
    profile.is_owner ||
    profile.permissions['*'] === 'all' ||
    Object.prototype.hasOwnProperty.call(profile.permissions, key)
  );
}

function resourceForSection(section: Section): string | undefined {
  return (
    {
      clients: 'clients',
      projects: 'projects',
      tasks: 'tasks',
      services: 'services',
      logs: 'logs',
      tests: 'test_suites',
      deployments: 'deployments',
    } as Partial<Record<Section, string>>
  )[section];
}

function sectionAllowed(profile: AuthUser | undefined, section: Section): boolean {
  if (!profile) return true;
  if (profile.is_owner || profile.permissions['*'] === 'all') return true;
  const permission: Partial<Record<Section, string>> = {
    dashboard: 'dashboard:view',
    clients: 'clients:view',
    projects: 'projects:view',
    tasks: 'tasks:view',
    services: 'services:view',
    activity: 'activity:view',
    logs: 'logs:view',
    tests: 'test_suites:view',
    deployments: 'deployments:view',
    settings: 'settings:view',
    orders: 'orders:view',
  };
  if (section === 'access') {
    return hasPermission(profile, 'admin:users:view') || hasPermission(profile, 'admin:roles:view');
  }
  const required = permission[section];
  return !!required && hasPermission(profile, required);
}

function sectionActionAllowed(
  profile: AuthUser | undefined,
  section: Section,
  action: 'create' | 'edit' | 'archive' | 'restore',
): boolean {
  if (!profile) return true;
  if (profile.is_owner || profile.permissions['*'] === 'all') return true;
  const resource = resourceForSection(section);
  return !!resource && hasPermission(profile, `${resource}:${action}`);
}

function initials(value: string) {
  return value
    .split(/\s+/)
    .slice(0, 2)
    .map((x) => x[0]?.toUpperCase() || '')
    .join('');
}

function formValues(item: Record<string, unknown> | undefined, fields: Field[]) {
  const result: Record<string, string> = {};
  fields.forEach((f) => {
    const v = item?.[f.name];
    result[f.name] =
      f.name === 'requirements' || f.name === 'acceptance_criteria'
        ? Array.isArray(v)
? v.join('\n')
          : ''
        : v === null || v === undefined
          ? ''
          : String(v);
  });
  return result;
}

function formPayload(values: Record<string, string>, fields: Field[], editing: boolean) {
  const data: Record<string, unknown> = {};
  const idFields = new Set(['client_id', 'project_id', 'service_id']);
  for (const field of fields) {
    const value = (values[field.name] ?? '').trim();
    if (field.name === 'requirements' || field.name === 'acceptance_criteria') {
      data[field.name] = value
        ? value
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean)
        : [];
      continue;
    }
    if (!value) {
      if (editing) {
        data[field.name] =
          field.type === 'number' || field.type === 'date' || idFields.has(field.name)
            ? null
            : field.required
              ? ''
              : null;
      }
      continue;
    }
    data[field.name] = field.type === 'number' || idFields.has(field.name) ? Number(value) : value;
  }
  return data;
}

function Badge({ value }: { value: unknown }) {
  const raw = String(value ?? 'unknown');
  const cls = ['active', 'healthy', 'done', 'passed', 'success'].includes(raw)
    ? 'green'
    : ['blocked', 'down', 'failed', 'urgent', 'error'].includes(raw)
      ? 'red'
      : ['in_progress', 'review', 'high', 'warning', 'degraded', 'probe'].includes(raw)
        ? 'amber'
        : 'slate';
  return <span className={`badge badge-${cls}`}>{label(raw)}</span>;
}

function EmptyState({
  icon: Icon = CircleHelp,
  title,
  detail,
  action,
}: {
  icon?: typeof CircleHelp;
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon size={22} />
      </span>
      <h3>{title}</h3>
      <p>{detail}</p>
      {action}
    </div>
  );
}

function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="notice notice-error">
      <AlertCircle size={17} />
      <div>
        <strong>Сбой загрузки данных контура</strong>
        <p>{message}</p>
        {retry && (
          <button className="text-button" onClick={retry}>
            Повторить запрос
          </button>
        )}
      </div>
    </div>
  );
}

export default function App({ profile, onLogout }: AppProps = {}) {
  const allowedNav = nav.filter((n) => sectionAllowed(profile, n.section));
  const initialSection = allowedNav[0]?.section ?? 'dashboard';
  const [section, setSection] = useState<Section>(initialSection);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [dashError, setDashError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [toast, setToast] = useState<{ message: string; error?: boolean } | null>(null);
  const [apiState, setApiState] = useState<'checking' | 'online' | 'offline'>('checking');

  const go = (s: Section) => {
    if (!sectionAllowed(profile, s)) return;
    setSection(s);
    setMobileOpen(false);
  };
  const notify = (message: string, error = false) => setToast({ message, error });
  const refresh = () => setRefreshKey((x) => x + 1);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setDashError('');
    try {
      setDashboard(await api.get<DashboardData>(`${API}/dashboard`));
    } catch (e) {
      setDashError(e instanceof Error ? e.message : 'Неизвестная ошибка');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (section === 'dashboard') void loadDashboard();
  }, [loadDashboard, refreshKey, section]);

  useEffect(() => {
    let active = true;
    api
      .get<Record<string, unknown>>('/health')
      .then(() => {
        if (active) setApiState('online');
      })
      .catch(() => {
        if (active) setApiState('offline');
      });
    return () => {
      active = false;
    };
  }, [refreshKey]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const active = nav.find((n) => n.section === section) ?? allowedNav[0] ?? nav[0];

  return (
    <div className="app-shell">
      {mobileOpen && (
        <button
          className="mobile-backdrop"
          aria-label="Закрыть меню"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <span className="brand-mark">
            <Code2 size={20} />
          </span>
          <span className="brand-copy">
            <strong>BOTVEX</strong>
            <small>CONTROL CENTER</small>
          </span>
          <button
            className="icon-button sidebar-close"
            aria-label="Закрыть меню"
            onClick={() => setMobileOpen(false)}
          >
            <X size={17} />
          </button>
        </div>
        <div className="workspace-switch">
          <span className="workspace-avatar">B</span>
          <span className="workspace-copy">
            <strong>Диспетчерский контур</strong>
            <small>Enterprise · RBAC Scope</small>
          </span>
          <ChevronDown size={14} />
        </div>
        <nav id="primary-navigation" className="main-nav" aria-label="Основная навигация">
          {['Рабочее пространство', 'Инфраструктура', 'Система'].map((group) => (
            <div className="nav-group" key={group}>
              <div className="nav-group-label">{group}</div>
              {allowedNav
                .filter((n) => n.group === group)
                .map((n) => {
                  const Icon = n.icon;
                  return (
                    <button
                      className={`nav-item ${section === n.section ? 'nav-item-active' : ''}`}
                      key={n.section}
                      aria-current={section === n.section ? 'page' : undefined}
                      onClick={() => go(n.section)}
                    >
                      <Icon size={18} />
                      <span>{n.label}</span>
                      {n.section === 'tasks' && dashboard?.metrics.open_tasks ? (
                        <span className="nav-count">{dashboard.metrics.open_tasks}</span>
                      ) : null}
                    </button>
                  );
                })}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="security-card">
            <ShieldCheck size={16} />
            <span>
              <strong>Защищённый сеанс</strong>
              <small>Верификация прав на сервере</small>
            </span>
            <i />
          </div>
          <div className="profile-row">
            <span className="profile-avatar">{initials(profile?.username ?? 'BOTVEX')}</span>
            <span>
              <strong>{profile?.username ?? 'Оператор'}</strong>
              <small>{profile?.roles.join(' · ') ?? 'Системный контур'}</small>
            </span>
          </div>
          <div className="version-line">
            Control Center <span>v0.1.0</span>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-menu-button"
              aria-label={mobileOpen ? 'Закрыть меню' : 'Открыть меню'}
              aria-expanded={mobileOpen}
              aria-controls="primary-navigation"
              onClick={() => setMobileOpen((value) => !value)}
            >
              <Menu size={18} />
            </button>
            <div className="breadcrumbs">
              <span>BOTVEX</span>
              <i>/</i>
              <strong>{active.label}</strong>
            </div>
          </div>
          <div className="topbar-right">
            <span className={`connection-state ${apiState}`}>
              <i />
              {apiState === 'online'
                ? 'Ядро API активно'
                : apiState === 'offline'
                  ? 'Ядро API недоступно'
                  : 'Опрос ядра API'}
            </span>
            <button
              className="topbar-icon"
              aria-label="Обновить данные"
              title="Обновить телеметрию"
              onClick={refresh}
            >
              <Activity size={16} />
            </button>
            <span className="topbar-avatar">{initials(profile?.username ?? 'B')}</span>
            {onLogout && (
              <button className="secondary-button header-logout" onClick={onLogout}>
                Выйти
              </button>
            )}
          </div>
        </header>

        <div className="content-area">
          <div className="telemetry-banner" role="status">
            <ShieldCheck size={14} />
            <span>
              КОНТУР БЕЗОПАСНОСТИ: АКТИВЕН · СЕССИЯ: ВЕРИФИЦИРОВАНА (SHA-256 / HTTP-ONLY) · ИЗОЛЯЦИЯ ДАННЫХ: RBAC + SQL SCOPE
            </span>
          </div>

          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {section === 'dashboard'
                  ? 'BOTVEX OPERATIONS // ЦЕНТРАЛЬНЫЙ ДИСПЕТЧЕРСКИЙ КОНТУР'
                  : `BOTVEX OPERATIONS // ${section.toUpperCase()}`}
              </div>
              <h1>
                {section === 'dashboard'
                  ? 'Панель операционного управления'
                  : section === 'access'
                    ? 'Управление доступом и матрицей ролей'
                    : active.label}
              </h1>
              <p>
                {section === 'dashboard'
                  ? 'Сводный контроль коммерческих заказов, проектных контуров, регламентных задач и состояния эксплуатируемых сервисов'
                  : section === 'settings'
                    ? 'Конфигурация системного ядра и параметры безопасности'
                    : section === 'orders'
                      ? 'Коммерческие обязательства, этапы выполнения, запросы на изменение и финансовый реестр'
                      : section === 'access'
                        ? 'Учётные записи операторов, клиентские привязки, роли и область видимости записей'
                        : `Операционное управление разделом «${active.label.toLowerCase()}»`}
              </p>
            </div>
            {section !== 'dashboard' &&
            section !== 'activity' &&
            section !== 'settings' &&
            section !== 'orders' &&
            section !== 'access' &&
            sectionActionAllowed(profile, section, 'create') ? (
              <button
                className="primary-button"
                onClick={() => window.dispatchEvent(new CustomEvent('botvex:create'))}
              >
                <Plus size={16} />
                Добавить запись
              </button>
            ) : null}
          </div>

          {section === 'dashboard' ? (
            <Dashboard
              data={dashboard}
              loading={loading}
              error={dashError}
              go={go}
              retry={() => void loadDashboard()}
            />
          ) : section === 'activity' ? (
            <ActivityPage key={refreshKey} />
          ) : section === 'settings' ? (
            <SettingsPage notify={notify} />
          ) : section === 'orders' && profile ? (
            <OrdersPage key={refreshKey} profile={profile} notify={notify} />
          ) : section === 'access' && profile ? (
            <AdminAccessPage key={refreshKey} profile={profile} notify={notify} />
          ) : (
            <ResourcePage
              key={`${section}-${refreshKey}`}
              config={configs[section as keyof typeof configs]}
              profile={profile}
              refresh={refresh}
              notify={notify}
            />
          )}

          <footer className="page-footer">
            <span>BOTVEX Control Center · Промышленный контур управления</span>
            <span>
              <i />
              Полномочия верифицируются сервером (RBAC + SQL Scope)
            </span>
          </footer>
        </div>
      </main>

      {toast && (
        <div className={`toast ${toast.error ? 'toast-error' : ''}`} role="status">
          {toast.error ? <AlertCircle size={17} /> : <CheckCircle2 size={17} />}
          <span>{toast.message}</span>
          <button aria-label="Закрыть уведомление" onClick={() => setToast(null)}>
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

function Dashboard({
  data,
  loading,
  error,
  go,
  retry,
}: {
  data: DashboardData | null;
  loading: boolean;
  error: string;
  go: (s: Section) => void;
  retry: () => void;
}) {
  const metrics = data?.metrics;
  const cards = [
    {
      label: 'Контрагенты в базе',
      value: metrics?.clients ?? 0,
      icon: Users,
      tone: 'blue',
      section: 'clients' as Section,
      foot: 'Активный реестр клиентов',
    },
    {
      label: 'Проектные контуры',
      value: metrics?.projects ?? 0,
      icon: BriefcaseBusiness,
      tone: 'violet',
      section: 'projects' as Section,
      foot: 'В работе и планировании',
    },
    {
      label: 'Открытые задачи',
      value: metrics?.open_tasks ?? 0,
      icon: CheckCircle2,
      tone: 'amber',
      section: 'tasks' as Section,
      foot: 'Требуют выполнения',
    },
    {
      label: 'Сервисы и узлы',
      value: metrics?.services ?? 0,
      icon: Bot,
      tone: 'green',
      section: 'services' as Section,
      foot: 'Эксплуатируемые единицы',
    },
  ];

  if (loading && !data) {
    return (
      <div className="loading">
        <LoaderCircle className="spin" size={25} />
        Синхронизация диспетчерской телеметрии…
      </div>
    );
  }
  if (error && !data) return <ErrorNotice message={error} retry={retry} />;

  return (
    <div className="dashboard-layout">
      <section className="metrics-grid">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <button key={card.label} className="metric-card" onClick={() => go(card.section)}>
              <div className="metric-head">
                <span>{card.label}</span>
                <i className={`metric-icon ${card.tone}`}>
                  <Icon size={18} />
                </i>
              </div>
              <strong className="metric-value">{card.value}</strong>
              <div className="metric-foot">
                <span>{card.foot}</span>
                <span>
                  Перейти <ArrowUpRight size={12} />
                </span>
              </div>
            </button>
          );
        })}
      </section>

      <div className="dashboard-columns">
        <section className="panel">
          <PanelHeading
            title="Приоритетная очередь задач"
            subtitle="Ближайшие контрольные сроки выполнения"
            action={
              <button className="text-button" onClick={() => go('tasks')}>
                Все задачи <ArrowDownRight size={13} />
              </button>
            }
          />
          {data?.next_tasks.length ? (
            <div className="task-list">
              {data.next_tasks.map((task) => {
                const overdue = isOverdue(task.due_date, task.status);
                return (
                  <div className={`task-row${overdue ? ' task-row-overdue' : ''}`} key={task.id}>
                    <span className="task-check">{task.status === 'done' ? <Check size={12} /> : null}</span>
                    <div className="row-info">
                      <strong>{task.title}</strong>
                      <small className={overdue ? 'task-due-overdue' : undefined}>
                        {overdue ? 'Просрочено · ' : ''}
                        {task.due_date ? `Срок: ${fmtDate(task.due_date)}` : 'Без установленного срока'}
                      </small>
                    </div>
                    <Badge value={task.status} />
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon={CheckCircle2}
              title="Очередь задач пуста"
              detail="Зарегистрируйте новую задачу для фиксации следующего регламентного этапа."
              action={
                <button className="secondary-button" onClick={() => go('tasks')}>
                  <Plus size={14} />
                  Создать задачу
                </button>
              }
            />
          )}
        </section>

        <section className="panel">
          <PanelHeading
            title="Состояние эксплуатируемых узлов"
            subtitle="Статус и источник последней верификации"
            action={
              <button className="icon-button" aria-label="Открыть сервисы" onClick={() => go('services')}>
                <ArrowUpRight size={15} />
              </button>
            }
          />
          {data?.service_summary.length ? (
            <div className="service-list">
              {data.service_summary.map((s) => (
                <div className="service-row" key={s.id}>
                  <span className="service-icon">
                    <Bot size={16} />
                  </span>
                  <div className="row-info">
                    <strong>{s.name}</strong>
                    <small>
                      {s.last_checked_at
                        ? `Проверено (${label(s.status_source)}): ${fmtDateTime(s.last_checked_at)}`
                        : 'HTTP-проверка ещё не запускалась'}
                    </small>
                  </div>
                  <Badge value={s.status} />
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={Bot}
              title="Узлы не зарегистрированы"
              detail="Добавьте сервис или Telegram-бота для ведения учёта и SSRF-защищённой проверки доступности."
              action={
                <button className="secondary-button" onClick={() => go('services')}>
                  <Plus size={14} />
                  Добавить сервис
                </button>
              }
            />
          )}
        </section>
      </div>

      <section className="panel">
        <PanelHeading
          title="Журнал операционной активности"
          subtitle="Аудит действий операторов и системных переходов"
          action={
            <button className="text-button" onClick={() => go('activity')}>
              Полный журнал <ArrowDownRight size={13} />
            </button>
          }
        />
        {data?.recent_activity.length ? (
          <div className="activity-list">
            {data.recent_activity.map((e) => (
              <div className="activity-row" key={e.id}>
                <span className="activity-symbol">
                  <Activity size={15} />
                </span>
                <div className="row-info">
                  <strong>{e.summary}</strong>
                  <small>
                    {e.actor} · {label(e.entity_type)} #{e.entity_id ?? '—'}
                  </small>
                </div>
                <time>{fmtDateTime(e.created_at)}</time>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Activity}
            title="События отсутствуют"
            detail="Любые операции создания, модификации и смены статусов фиксируются в журнале."
            action={
              <button className="secondary-button" onClick={() => go('clients')}>
                Перейти к клиентам
              </button>
            }
          />
        )}
      </section>

      <div className="notice notice-neutral">
        <ShieldCheck size={16} />
        <span>
          <strong>Достоверность телеметрии.</strong> Панель отображает только верифицированные серверные записи. Источник статуса каждого узла («Вручную» или «HTTP-проверка») фиксируется явно.
        </span>
      </div>
    </div>
  );
}

function PanelHeading({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel-heading">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

function ResourcePage({
  config,
  profile,
  refresh,
  notify,
}: {
  config: Config;
  profile?: AuthUser;
  refresh: () => void;
  notify: (message: string, error?: boolean) => void;
}) {
  const [items, setItems] = useState<Entity[]>([]);
  const [clients, setClients] = useState<Array<{ id: number; name: string }>>([]);
  const [projects, setProjects] = useState<Array<{ id: number; name: string }>>([]);
  const [services, setServices] = useState<Array<{ id: number; name: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [modal, setModal] = useState<{ mode: 'create' | 'edit'; item?: Entity } | null>(null);
  const [runTarget, setRunTarget] = useState<Entity | null>(null);
  const [membersTarget, setMembersTarget] = useState<Entity | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [projectFilter, setProjectFilter] = useState('all');
  const [sortDue, setSortDue] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [viewMode, setViewMode] = useState<'table' | 'kanban'>('table');

  const resource = resourceForSection(config.section);
  const mayCreate = !!resource && sectionActionAllowed(profile, config.section, 'create');
  const mayEdit = !!resource && sectionActionAllowed(profile, config.section, 'edit');
  const mayArchive = !!resource && sectionActionAllowed(profile, config.section, 'archive');
  const mayRestore = !!resource && sectionActionAllowed(profile, config.section, 'restore');
  const mayRecordRun = config.section === 'tests' && sectionActionAllowed(profile, 'tests', 'create');
  const mayAssignProject = config.section === 'projects' && hasPermission(profile, 'projects:assign');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.get<Entity[]>(
        `${config.endpoint}?limit=250&include_archived=${showArchived}`,
      );
      setItems(data);
      if (['projects', 'tasks', 'services', 'tests', 'deployments'].includes(config.section)) {
        const [c, p] = await Promise.all([
          api.get<Array<{ id: number; name: string }>>(`${API}/clients?limit=250`).catch(() => []),
          api.get<Array<{ id: number; name: string }>>(`${API}/projects?limit=250`).catch(() => []),
        ]);
        setClients(c);
        setProjects(p);
      }
      if (config.section === 'logs') {
        const s = await api
          .get<Array<{ id: number; name: string }>>(`${API}/services?limit=250`)
          .catch(() => []);
        setServices(s);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки данных');
    } finally {
      setLoading(false);
    }
  }, [config, showArchived]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const handler = () => {
      if (mayCreate) setModal({ mode: 'create' });
    };
    window.addEventListener('botvex:create', handler);
    return () => window.removeEventListener('botvex:create', handler);
  }, [mayCreate]);

  const clientMap = useMemo(() => new Map(clients.map((c) => [c.id, c.name])), [clients]);
  const projectMap = useMemo(() => new Map(projects.map((p) => [p.id, p.name])), [projects]);
  const serviceMap = useMemo(() => new Map(services.map((s) => [s.id, s.name])), [services]);

  const resolveCell = (col: Column, item: Entity) => {
    const raw = item[col.key];
    if (col.key === 'client_id' && typeof raw === 'number') {
      const name = clientMap.get(raw);
      return name ? `${name} (#${raw})` : `#${raw}`;
    }
    if (col.key === 'project_id' && typeof raw === 'number') {
      const name = projectMap.get(raw);
      return name ? `${name} (#${raw})` : `#${raw}`;
    }
    if (col.key === 'service_id' && typeof raw === 'number') {
      const name = serviceMap.get(raw);
      return name ? `${name} (#${raw})` : `#${raw}`;
    }
    return col.format ? col.format(raw, item) : String(raw ?? '—');
  };

  const fields = useMemo(
    () =>
      config.fields.map((field) => {
        if (field.name === 'client_id') {
          return {
            ...field,
            options: [
              { value: '', label: 'Без клиента' },
              ...clients.map((c) => ({ value: String(c.id), label: `${c.name} (#${c.id})` })),
            ],
          };
        }
        if (field.name === 'project_id' && field.type === 'select') {
          return {
            ...field,
            options: [
              { value: '', label: 'Без проекта' },
              ...projects.map((p) => ({ value: String(p.id), label: `${p.name} (#${p.id})` })),
            ],
          };
        }
        if (field.name === 'service_id' && field.type === 'select') {
          return {
            ...field,
            options: [
              { value: '', label: 'Без привязки к сервису' },
              ...services.map((s) => ({ value: String(s.id), label: `${s.name} (#${s.id})` })),
            ],
          };
        }
        return field;
      }),
    [config.fields, clients, projects, services],
  );

  const visible = useMemo(() => {
    let list = items.filter((item) =>
      Object.values(item).some((v) => String(v ?? '').toLowerCase().includes(query.toLowerCase())),
    );
    if (config.section === 'tasks') {
      if (statusFilter !== 'all') list = list.filter((i) => i.status === statusFilter);
      if (priorityFilter !== 'all') list = list.filter((i) => i.priority === priorityFilter);
      if (projectFilter !== 'all') list = list.filter((i) => String(i.project_id ?? '') === projectFilter);
      if (sortDue) {
        list = [...list].sort((a, b) =>
          String(a.due_date ?? '9999').localeCompare(String(b.due_date ?? '9999')),
        );
      }
    }
    return list;
  }, [items, query, config.section, statusFilter, priorityFilter, projectFilter, sortDue]);

  const save = async (values: Record<string, string>) => {
    setSaving(true);
    try {
      const data = formPayload(values, fields, modal?.mode === 'edit');
      if (modal?.mode === 'edit' && modal.item) {
        await api.patch(`${config.endpoint}/${modal.item.id}`, data);
      } else {
        await api.post(config.endpoint, data);
      }
      setModal(null);
      await load();
      refresh();
      notify(modal?.mode === 'edit' ? 'Изменения сохранены' : 'Запись зарегистрирована');
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Не удалось сохранить запись', true);
    } finally {
      setSaving(false);
    }
  };

  const archive = async (item: Entity) => {
    const name = String(item.name ?? item.title ?? item.version ?? `#${item.id}`);
    if (!window.confirm(`Переместить «${name}» в архив? Запись сохранится в БД.`)) return;
    setBusy(true);
    try {
      await api.post(`${config.endpoint}/${item.id}/archive`, {});
      await load();
      refresh();
      notify('Запись перемещена в архив');
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Не удалось архивировать запись', true);
    } finally {
      setBusy(false);
    }
  };

  const restore = async (item: Entity) => {
    const name = String(item.name ?? item.title ?? item.version ?? `#${item.id}`);
    if (!window.confirm(`Восстановить «${name}» из архива?`)) return;
    setBusy(true);
    try {
      await api.post(`${config.endpoint}/${item.id}/restore`, {});
      await load();
      refresh();
      notify('Запись восстановлена');
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Не удалось восстановить запись', true);
    } finally {
      setBusy(false);
    }
  };

  const probeService = async (item: Entity) => {
    setBusy(true);
    try {
      const updated = await api.post<Entity>(`${API}/services/${item.id}/probe`, {});
      await load();
      refresh();
      notify(`Проверка узла завершена: ${label(updated.status)}`);
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Ошибка проверки узла', true);
    } finally {
      setBusy(false);
    }
  };

  const quickTaskStatus = async (task: Entity, nextStatus: string) => {
    setBusy(true);
    try {
      await api.patch(`${API}/tasks/${task.id}`, { status: nextStatus });
      await load();
      refresh();
      notify(`Статус задачи переведён в «${label(nextStatus)}»`);
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Не удалось обновить статус задачи', true);
    } finally {
      setBusy(false);
    }
  };

  const recordRun = async (values: { status: string; duration_ms: number | null; note: string }) => {
    if (!runTarget) return;
    setSaving(true);
    try {
      await api.post(`${API}/test-suites/${runTarget.id}/runs`, { ...values, source: 'manual' });
      setRunTarget(null);
      await load();
      refresh();
      notify('Результат тестового прогона зафиксирован');
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Не удалось сохранить результат', true);
    } finally {
      setSaving(false);
    }
  };

  const titleKey = fields.find((f) => ['name', 'title', 'version'].includes(f.name))?.name || 'id';
  const taskStages = ['backlog', 'in_progress', 'blocked', 'review', 'done'] as const;

  return (
    <div className="resource-layout">
      <section className="panel resource-panel">
        <div className="resource-toolbar">
          <div className="search-field">
            <Search size={16} />
            <input
              aria-label="Поиск по списку"
              placeholder="Фильтрация по записям…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="toolbar-right">
            <span className="result-count">{visible.length} записей</span>
            {config.section === 'tasks' && (
              <div className="access-tabs" role="tablist" aria-label="Режим отображения задач">
                <button
                  type="button"
                  className={viewMode === 'table' ? 'access-tab access-tab-active' : 'access-tab'}
                  onClick={() => setViewMode('table')}
                >
                  Таблица
                </button>
                <button
                  type="button"
                  className={viewMode === 'kanban' ? 'access-tab access-tab-active' : 'access-tab'}
                  onClick={() => setViewMode('kanban')}
                >
                  Канбан по этапам
                </button>
              </div>
            )}
            {config.archive && (
              <label className="sort-due archived-toggle">
                <input
                  type="checkbox"
                  checked={showArchived}
                  onChange={(e) => setShowArchived(e.target.checked)}
                />
                Включая архив
              </label>
            )}
            {mayCreate && (
              <button className="primary-button compact" onClick={() => setModal({ mode: 'create' })}>
                <Plus size={15} />
                Добавить
              </button>
            )}
          </div>

          {config.section === 'tasks' && (
            <div className="task-filters">
              <select
                aria-label="Фильтр по статусу"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="all">Все статусы</option>
                {taskStages.map((v) => (
                  <option key={v} value={v}>
                    {label(v)}
                  </option>
                ))}
              </select>
              <select
                aria-label="Фильтр по приоритету"
                value={priorityFilter}
                onChange={(e) => setPriorityFilter(e.target.value)}
              >
                <option value="all">Все приоритеты</option>
                {['low', 'normal', 'high', 'urgent'].map((v) => (
                  <option key={v} value={v}>
                    {label(v)}
                  </option>
                ))}
              </select>
              <select
                aria-label="Фильтр по проекту"
                value={projectFilter}
                onChange={(e) => setProjectFilter(e.target.value)}
              >
                <option value="all">Все проекты</option>
                {projects.map((p) => (
                  <option key={p.id} value={String(p.id)}>
                    {p.name}
                  </option>
                ))}
              </select>
              <label className="sort-due">
                <input
                  type="checkbox"
                  checked={sortDue}
                  onChange={(e) => setSortDue(e.target.checked)}
                />
                По контрольному сроку
              </label>
            </div>
          )}
        </div>

        {error ? (
          <ErrorNotice message={error} retry={() => void load()} />
        ) : loading ? (
          <div className="loading">
            <LoaderCircle className="spin" size={22} />
            Загрузка реестра…
          </div>
        ) : visible.length === 0 ? (
          <EmptyState
            icon={config.icon}
            title={query ? 'Совпадений не обнаружено' : 'Реестр пуст'}
            detail={
              query
                ? 'Измените параметры поискового запроса или сбросьте фильтры.'
                : 'В данном контуре отображаются только верифицированные записи локальной БД.'
            }
            action={
              !query && mayCreate ? (
                <button className="secondary-button" onClick={() => setModal({ mode: 'create' })}>
                  <Plus size={14} />
                  Добавить {config.singular}
                </button>
              ) : undefined
            }
          />
        ) : config.section === 'tasks' && viewMode === 'kanban' ? (
          <div className="kanban-board">
            {taskStages.map((stage) => {
              const stageTasks = visible.filter((t) => t.status === stage);
              return (
                <div className="kanban-column" key={stage}>
                  <div className="kanban-column-head">
                    <strong>{label(stage)}</strong>
                    <span className="nav-count">{stageTasks.length}</span>
                  </div>
                  <div className="kanban-cards">
                    {stageTasks.map((t) => (
                      <article className="kanban-card" key={t.id}>
                        <strong>{String(t.title)}</strong>
                        <small>
                          {typeof t.project_id === 'number'
                            ? projectMap.get(t.project_id) || `#${t.project_id}`
                            : 'Без проекта'}{' '}
                          · {fmtDate(t.due_date)}
                        </small>
                        <div className="kanban-card-foot">
                          <Badge value={t.priority} />
                          {mayEdit && !t.is_archived && (
                            <select
                              aria-label={`Изменить этап задачи ${String(t.title)}`}
                              value={String(t.status)}
                              disabled={busy}
                              onChange={(e) => void quickTaskStatus(t, e.target.value)}
                            >
                              {taskStages.map((st) => (
                                <option key={st} value={st}>
                                  {label(st)}
                                </option>
                              ))}
                            </select>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {config.columns.map((c) => (
                    <th key={c.key}>{c.label}</th>
                  ))}
                  <th className="actions-head">Операции</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => (
                  <tr key={item.id}>
                    <td className="primary-cell" data-label={config.columns[0]?.label}>
                      <span className="row-main-icon">
                        {initials(String(item[titleKey] ?? `#${item.id}`))}
                      </span>
                      <span>
                        <strong>{String(item[titleKey] ?? `#${item.id}`)}</strong>
                        <small>#{item.id}</small>
                      </span>
                    </td>
                    {config.columns.slice(1).map((c) => (
                      <td key={c.key} data-label={c.label}>
                        {['client_id', 'project_id', 'service_id'].includes(c.key) ? (
                          <span className="cell-text">{resolveCell(c, item)}</span>
                        ) : c.format ? (
                          c.format(item[c.key], item)
                        ) : c.key === 'status' || c.key === 'priority' ? (
                          <Badge value={item[c.key]} />
                        ) : (
                          <span className="cell-text">
                            {item[c.key] === null || item[c.key] === undefined || item[c.key] === ''
                              ? '—'
                              : String(item[c.key])}
                          </span>
                        )}
                      </td>
                    ))}
                    <td data-label="Операции">
                      <div className="row-actions">
                        {mayAssignProject && !item.is_archived && (
                          <button
                            className="icon-button row-action"
                            title="Допуск к проекту"
                            aria-label={`Допуск к проекту ${String(item[titleKey] ?? item.id)}`}
                            onClick={() => setMembersTarget(item)}
                          >
                            <Users size={14} />
                          </button>
                        )}
                        {config.section === 'services' && mayEdit && !item.is_archived && (
                          <button
                            className="icon-button row-action"
                            title="Проверить узел (HTTP probe)"
                            aria-label={`Проверить узел ${String(item[titleKey] ?? item.id)}`}
                            disabled={busy}
                            onClick={() => void probeService(item)}
                          >
                            <Activity size={14} />
                          </button>
                        )}
                        {mayEdit && !item.is_archived && (
                          <button
                            className="icon-button row-action"
                            title="Редактировать"
                            aria-label={`Редактировать ${String(item[titleKey] ?? item.id)}`}
                            onClick={() => setModal({ mode: 'edit', item })}
                          >
                            <Settings2 size={14} />
                          </button>
                        )}
                        {mayRecordRun && !item.is_archived && (
                          <button
                            className="icon-button row-action"
                            title="Записать результат тестов"
                            aria-label={`Записать результат тестов ${String(item[titleKey] ?? item.id)}`}
                            onClick={() => setRunTarget(item)}
                          >
                            <FlaskConical size={14} />
                          </button>
                        )}
                        {config.archive && mayArchive && !item.is_archived && (
                          <button
                            className="icon-button row-action"
                            title="В архив"
                            aria-label={`Архивировать ${String(item[titleKey] ?? item.id)}`}
                            disabled={busy}
                            onClick={() => void archive(item)}
                          >
                            <Archive size={14} />
                          </button>
                        )}
                        {config.archive && mayRestore && item.is_archived === true && (
                          <button
                            className="icon-button row-action"
                            title="Восстановить"
                            aria-label={`Восстановить ${String(item[titleKey] ?? item.id)}`}
                            disabled={busy}
                            onClick={() => void restore(item)}
                          >
                            <RefreshCw size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="table-footer">
          <span>Реестр синхронизирован с локальным хранилищем</span>
          <span>
            <Database size={13} />
            SQLite · WAL Mode
          </span>
        </div>
      </section>

      {config.section === 'services' && (
        <div className="notice notice-neutral">
          <CircleHelp size={16} />
          <span>
            <strong>Верификация узлов.</strong> Вы можете зафиксировать статус вручную или запустить разовую SSRF-защищённую HTTP-проверку кнопкой «Проверить узел» в строке сервиса.
          </span>
        </div>
      )}
      {config.section === 'tests' && (
        <div className="notice notice-neutral">
          <FlaskConical size={16} />
          <span>
            <strong>Реестр тестовых прогонов.</strong> Результаты фиксируются оператором без запуска произвольного кода на сервере.
          </span>
        </div>
      )}
      {config.section === 'deployments' && (
        <div className="notice notice-neutral">
          <TerminalSquare size={16} />
          <span>
            <strong>Реестр выкладок.</strong> Журнал предназначен для учёта версий и сред эксплуатации.
          </span>
        </div>
      )}

      {modal && (
        <EntityModal
          key={`${modal.mode}-${modal.item?.id ?? 'new'}`}
          title={modal.mode === 'edit' ? 'Редактировать запись' : `Добавить ${config.singular}`}
          fields={fields}
          initial={formValues(modal.item, fields)}
          saving={saving}
          onClose={() => setModal(null)}
          onSave={save}
        />
      )}
      {runTarget && (
        <TestRunModal
          suiteId={Number(runTarget.id)}
          name={String(runTarget.name ?? 'Набор тестов')}
          saving={saving}
          onClose={() => setRunTarget(null)}
          onSave={recordRun}
        />
      )}
      {membersTarget && (
        <ProjectMembersModal
          projectId={Number(membersTarget.id)}
          projectName={String(membersTarget.name ?? `#${membersTarget.id}`)}
          onClose={() => setMembersTarget(null)}
          notify={notify}
        />
      )}
    </div>
  );
}

function ProjectMembersModal({
  projectId,
  projectName,
  onClose,
  notify,
}: {
  projectId: number;
  projectName: string;
  onClose: () => void;
  notify: (message: string, error?: boolean) => void;
}) {
  const [members, setMembers] = useState<ProjectAssignment[]>([]);
  const [users, setUsers] = useState<Array<{ id: number; username: string; roles: string[]; is_active: boolean }>>([]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [m, u] = await Promise.all([
        api.get<ProjectAssignment[]>(`${API}/admin/projects/${projectId}/members`),
        api
          .get<{ items: Array<{ id: number; username: string; roles: string[]; is_active: boolean }> }>(
            `${API}/admin/users?limit=100`,
          )
          .then((r) => r.items)
          .catch(() => []),
      ]);
      setMembers(m);
      setUsers(u.filter((usr) => usr.is_active && !usr.roles.includes('client')));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить состав проектной группы.');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function assign(e: FormEvent) {
    e.preventDefault();
    if (!selectedUserId) return;
    setBusy(true);
    setError('');
    try {
      await api.post(`${API}/admin/projects/${projectId}/members`, {
        user_id: Number(selectedUserId),
      });
      setSelectedUserId('');
      await load();
      notify('Сотрудник включён в контур проекта');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось назначить сотрудника.');
    } finally {
      setBusy(false);
    }
  }

  async function unassign(userId: number) {
    setBusy(true);
    setError('');
    try {
      await api.delete(`${API}/admin/projects/${projectId}/members/${userId}`);
      await load();
      notify('Доступ сотрудника к проекту отозван');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось отозвать доступ.');
    } finally {
      setBusy(false);
    }
  }

  const assignedIds = new Set(members.map((m) => m.user_id));
  const availableUsers = users.filter((u) => !assignedIds.has(u.id));

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <section className="modal-card small-modal" role="dialog" aria-modal="true" aria-labelledby="members-title">
        <div className="modal-heading">
          <div>
            <div className="eyebrow">PROJECT ACCESS SCOPE // ДОПУСК К ПРОЕКТУ</div>
            <h2 id="members-title">Команда: {projectName}</h2>
          </div>
          <button className="icon-button" aria-label="Закрыть" disabled={busy} onClick={onClose}>
            <X size={17} />
          </button>
        </div>
        <div className="run-history">
          {error && <p className="field-error">{error}</p>}
          {loading ? (
            <p className="field-hint">Загрузка проектной группы…</p>
          ) : members.length === 0 ? (
            <p className="field-hint">Назначенных сотрудников пока нет.</p>
          ) : (
            <div className="activity-list">
              {members.map((m) => (
                <div className="activity-row" key={m.id}>
                  <div className="row-info">
                    <strong>{m.username}</strong>
                    <small>Назначен: {fmtDateTime(m.created_at)}</small>
                  </div>
                  <button
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void unassign(m.user_id)}
                  >
                    Отозвать
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        <form onSubmit={assign}>
          <div className="form-grid">
            <label className="form-field field-full">
              <span>Добавить сотрудника в проект</span>
              <select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)}>
                <option value="">Выбрать учётную запись</option>
                {availableUsers.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.username} ({u.roles.join(', ')})
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="modal-footer">
            <button type="button" className="secondary-button" onClick={onClose}>
              Закрыть
            </button>
            <button type="submit" className="primary-button" disabled={busy || !selectedUserId}>
              Назначить в проект
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function EntityModal({
  title,
  fields,
  initial,
  saving,
  onClose,
  onSave,
}: {
  title: string;
  fields: Field[];
  initial: Record<string, string>;
  saving: boolean;
  onClose: () => void;
  onSave: (values: Record<string, string>) => Promise<void>;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const result: Record<string, string> = { ...initial };
    fields.forEach((f) => {
      if (result[f.name] === undefined) {
        result[f.name] = f.type === 'select' ? (f.options?.[0]?.value ?? '') : '';
      }
    });
    return result;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  const change = (name: string, value: string) => {
    setValues((p) => ({ ...p, [name]: value }));
    setErrors((p) => ({ ...p, [name]: '' }));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    fields.forEach((f) => {
      if (f.required && !values[f.name]?.trim()) next[f.name] = 'Обязательное поле';
      if (
        f.type === 'number' &&
        values[f.name] &&
        (!Number.isFinite(Number(values[f.name])) || Number(values[f.name]) < 0)
      ) {
        next[f.name] = 'Укажите неотрицательное число';
      }
    });
    setErrors(next);
    if (Object.values(next).some(Boolean)) return;
    await onSave(values);
  };

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !saving) onClose();
      }}
    >
      <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="modal-heading">
          <div>
            <div className="eyebrow">BOTVEX // РЕДАКТОР ЗАПИСИ</div>
            <h2 id="modal-title">{title}</h2>
          </div>
          <button className="icon-button" aria-label="Закрыть" disabled={saving} onClick={onClose}>
            <X size={17} />
          </button>
        </div>
        <form onSubmit={submit}>
          <div className="form-grid">
            {fields.map((field) => (
              <label
                className={`form-field ${field.type === 'textarea' ? 'field-full' : ''}`}
                key={field.name}
              >
                <span>
                  {field.label}
                  {field.required && <i> *</i>}
                </span>
                {field.type === 'textarea' ? (
                  <textarea
                    value={values[field.name] ?? ''}
                    onChange={(e) => change(field.name, e.target.value)}
                    rows={3}
                    placeholder={field.placeholder}
                    maxLength={10000}
                  />
                ) : field.type === 'select' ? (
                  <select
                    value={values[field.name] ?? ''}
                    onChange={(e) => change(field.name, e.target.value)}
                  >
                    {(field.options ?? []).map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={field.type === 'number' ? 'number' : field.type === 'date' ? 'date' : 'text'}
                    min={field.type === 'number' ? 0 : undefined}
                    maxLength={field.type === 'number' ? undefined : 500}
                    value={values[field.name] ?? ''}
                    onChange={(e) => change(field.name, e.target.value)}
                    placeholder={field.placeholder}
                  />
                )}
                {errors[field.name] && <small className="field-error">{errors[field.name]}</small>}
                {field.hint && <small className="field-hint">{field.hint}</small>}
              </label>
            ))}
          </div>
          <div className="modal-footer">
            <button type="button" className="secondary-button" disabled={saving} onClick={onClose}>
              Отмена
            </button>
            <button type="submit" className="primary-button" disabled={saving}>
              {saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />}
              {saving ? 'Сохранение…' : 'Сохранить'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function TestRunModal({
  suiteId,
  name,
  saving,
  onClose,
  onSave,
}: {
  suiteId: number;
  name: string;
  saving: boolean;
  onClose: () => void;
  onSave: (v: { status: string; duration_ms: number | null; note: string }) => Promise<void>;
}) {
  const [status, setStatus] = useState('passed');
  const [duration, setDuration] = useState('');
  const [note, setNote] = useState('');
  const [history, setHistory] = useState<
    Array<{
      id: number;
      status: string;
      source: string;
      duration_ms: number | null;
      note: string | null;
      created_at: string;
    }>
  >([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');

  useEffect(() => {
    let active = true;
    api
      .get<
        Array<{
          id: number;
          status: string;
          source: string;
          duration_ms: number | null;
          note: string | null;
          created_at: string;
        }>
      >(`${API}/test-suites/${suiteId}/runs`)
      .then((rows) => {
        if (active) setHistory(rows);
      })
      .catch((e) => {
        if (active) setHistoryError(e instanceof Error ? e.message : 'Не удалось загрузить историю');
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [suiteId]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    await onSave({ status, duration_ms: duration ? Number(duration) : null, note });
  };

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !saving) onClose();
      }}
    >
      <section className="modal-card small-modal" role="dialog" aria-modal="true" aria-labelledby="run-title">
        <div className="modal-heading">
          <div>
            <div className="eyebrow">MANUAL TEST RECORD</div>
            <h2 id="run-title">Результат: {name}</h2>
          </div>
          <button className="icon-button" aria-label="Закрыть" disabled={saving} onClick={onClose}>
            <X size={17} />
          </button>
        </div>
        <div className="run-history">
          <h3>История результатов</h3>
          {historyLoading ? (
            <p className="field-hint">Загрузка истории…</p>
          ) : historyError ? (
            <p className="field-error">{historyError}</p>
          ) : history.length === 0 ? (
            <p className="field-hint">Запусков пока нет.</p>
          ) : (
            <div className="activity-list">
              {history.slice(0, 5).map((run) => (
                <div className="activity-row" key={run.id}>
                  <span className="activity-symbol">
                    <FlaskConical size={15} />
                  </span>
                  <div className="row-info">
                    <strong>
                      {label(run.status)} · {label(run.source)}
                    </strong>
                    <small>
                      {run.duration_ms === null ? 'Длительность не указана' : `${run.duration_ms} мс`}
                      {run.note ? ` · ${run.note}` : ''}
                    </small>
                  </div>
                  <time>{fmtDateTime(run.created_at)}</time>
                </div>
              ))}
            </div>
          )}
        </div>
        <form onSubmit={submit}>
          <div className="form-grid">
            <label className="form-field field-full">
              <span>Результат</span>
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="passed">Успешно</option>
                <option value="failed">Ошибка</option>
                <option value="skipped">Пропущен</option>
                <option value="manual">Ручная отметка</option>
              </select>
            </label>
            <label className="form-field field-full">
              <span>Длительность (мс, необязательно)</span>
              <input
                type="number"
                min="0"
                max="86400000"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
              />
            </label>
            <label className="form-field field-full">
              <span>Заметка оператора</span>
              <textarea
                rows={3}
                maxLength={10000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Что было проверено?"
              />
            </label>
          </div>
          <p className="field-hint">
            Запись помечается как внесённая оператором вручную.
          </p>
          <div className="modal-footer">
            <button type="button" className="secondary-button" onClick={onClose} disabled={saving}>
              Отмена
            </button>
            <button type="submit" className="primary-button" disabled={saving}>
              {saving ? 'Сохранение…' : 'Записать результат'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function ActivityPage() {
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setItems(
        await api.get<Array<Record<string, unknown>>>(
          `${API}/activity?limit=250${filter !== 'all' ? `&entity_type=${encodeURIComponent(filter)}` : ''}`,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="panel activity-page">
      <div className="resource-toolbar">
        <div>
          <h2 className="section-subheading">Системный журнал аудита и операций</h2>
          <p className="panel-subtitle">Фиксация событий безопасности, переходов заказов и модификации реестров.</p>
        </div>
        <select
          className="filter-select"
          aria-label="Фильтр по сущности"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">Все контуры</option>
          <option value="security">Безопасность</option>
          <option value="order">Заказы</option>
          <option value="order_change_request">Запросы на изменение</option>
          <option value="order_payment">Финансы</option>
          <option value="client">Клиенты</option>
          <option value="project">Проекты</option>
          <option value="task">Задачи</option>
          <option value="service">Сервисы</option>
          <option value="settings">Настройки</option>
        </select>
      </div>
      {error ? (
        <ErrorNotice message={error} retry={() => void load()} />
      ) : loading ? (
        <div className="loading">
          <LoaderCircle className="spin" size={22} />
          Загрузка журнала…
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="Записи отсутствуют"
          detail="Зарегистрированные операции и события безопасности отобразятся в этом списке."
        />
      ) : (
        <div className="activity-list">
          {items.map((item) => (
            <div className="activity-row" key={String(item.id)}>
              <span className="activity-symbol">
                <Activity size={15} />
              </span>
              <div className="row-info">
                <strong>{String(item.summary)}</strong>
                <small>
                  {String(item.actor)} · {label(item.entity_type)} #{item.entity_id ?? '—'} ·{' '}
                  {label(item.action)}
                </small>
              </div>
              <time>{fmtDateTime(item.created_at)}</time>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function SettingsPage({ notify }: { notify: (message: string, error?: boolean) => void }) {
  const [settings, setSettings] = useState<Record<string, string>>({
    display_name: 'BOTVEX Control Center',
    timezone: 'Europe/Moscow',
  });
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    Promise.all([
      api.get<Array<{ key: string; value: string }>>(`${API}/settings`),
      api.get<Record<string, unknown>>('/health'),
    ])
      .then(([rows, h]) => {
        if (!active) return;
        const values: Record<string, string> = {};
        rows.forEach((r) => (values[r.key] = r.value));
        setSettings((p) => ({ ...p, ...values }));
        setHealth(h);
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : 'Ошибка загрузки');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const rows = await api.patch<Array<{ key: string; value: string }>>(`${API}/settings`, settings);
      const values: Record<string, string> = {};
      rows.forEach((r) => (values[r.key] = r.value));
      setSettings((p) => ({ ...p, ...values }));
      notify('Системные параметры сохранены');
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Не удалось сохранить';
      setError(message);
      notify(message, true);
    } finally {
      setSaving(false);
    }
  };

  const authModeText =
    health?.auth_mode === 'account_session'
      ? 'Сессии + Telegram Mini App'
      : health?.auth_mode === 'account_session_only'
        ? 'Серверные сессии (Argon2id)'
        : 'Верификация';

  return (
    <div className="settings-grid">
      <section className="panel settings-panel">
        <PanelHeading
          title="Параметры диспетчерского узла"
          subtitle="Базовая конфигурация рабочего пространства"
          action={<Settings2 size={18} />}
        />
        {loading ? (
          <div className="loading">
            <LoaderCircle className="spin" size={22} />
          </div>
        ) : (
          <>
            <label className="form-field">
              <span>Наименование контура</span>
              <input
                value={settings.display_name ?? ''}
                maxLength={100}
                onChange={(e) => setSettings((p) => ({ ...p, display_name: e.target.value }))}
              />
            </label>
            <label className="form-field">
              <span>Системный часовой пояс (IANA)</span>
              <input
                value={settings.timezone ?? ''}
                placeholder="Europe/Moscow"
                onChange={(e) => setSettings((p) => ({ ...p, timezone: e.target.value }))}
              />
            </label>
            <p className="field-hint settings-hint">
              Используйте стандартный идентификатор IANA, например Europe/Moscow или UTC.
            </p>
            {error && <p className="field-error">{error}</p>}
            <button className="primary-button" disabled={saving} onClick={() => void save()}>
              {saving ? 'Применение…' : 'Сохранить конфигурацию'}
            </button>
          </>
        )}
      </section>

      <section className="panel settings-panel">
        <PanelHeading
          title="Телеметрия системного ядра"
          subtitle="Статус БД, контура аутентификации и активных политик"
          action={<Gauge size={18} />}
        />
        <div className="system-list">
          <div className="system-row">
            <span>Ядро Backend API</span>
            <Badge value={health?.status === 'ok' ? 'healthy' : 'unknown'} />
          </div>
          <div className="system-row">
            <span>Хранилище SQLite (WAL)</span>
            <Badge value={health?.database === 'ok' ? 'healthy' : 'unknown'} />
          </div>
          <div className="system-row">
            <span>Версия сборки</span>
            <strong>{String(health?.version ?? '0.1.0')}</strong>
          </div>
          <div className="system-row">
            <span>Режим аутентификации</span>
            <strong>{authModeText}</strong>
          </div>
        </div>
        <div className="notice notice-neutral">
          <ShieldCheck size={15} />
          <span>
            {String(
              health?.startup_banner ??
                '[BOTVEX-CORE] CONTROL CENTER INITIALIZED | DB=SQLITE_WAL | RBAC=STRICT_SCOPE | ORIGIN_GUARD=ACTIVE',
            )}
          </span>
        </div>
      </section>

      <section className="panel settings-panel settings-wide">
        <PanelHeading
          title="Активные регламенты безопасности"
          subtitle="Аппаратно-программные ограничения текущего узла"
          action={<ShieldCheck size={18} />}
        />
        <div className="settings-facts">
          <p>
            <CheckCircle2 size={16} />
            Хеширование паролей Argon2id и хранение сессий в виде SHA-256 дайджестов в HttpOnly-cookie.
          </p>
          <p>
            <CheckCircle2 size={16} />
            Проверка подписи Telegram initData (HMAC-SHA256) с привязкой к верифицированному аккаунту.
          </p>
          <p>
            <CheckCircle2 size={16} />
            SQLite в режиме WAL с контролем внешних ключей и утилитой горячего резервного копирования.
          </p>
          <p>
            <CheckCircle2 size={16} />
            Защита от SSRF при проверке health_endpoint сервисов (блокировка локальных и приватных подсетей).
          </p>
        </div>
      </section>
    </div>
  );
}
