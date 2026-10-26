import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  Archive,
  ArrowLeft,
  CalendarDays,
  Check,
  CircleDollarSign,
  FileDiff,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  X,
} from 'lucide-react';
import { api } from './api';
import { formatDate, formatDateTime } from './formatting';
import type {
  AuthUser,
  OrderChangeRequest,
  OrderEvent,
  OrderMessage,
  OrderPaymentSummary,
  OrderRecord,
  OrderStatus,
} from './types';

type Props = {
  profile: AuthUser;
  notify: (message: string, error?: boolean) => void;
};

type Page = {
  items: OrderRecord[];
  total: number;
  limit: number;
  offset: number;
};

type Client = { id: number; name: string; is_archived?: boolean };
type Project = { id: number; name: string; client_id: number | null; is_archived?: boolean };

type Values = {
  client_id: string;
  project_id: string;
  title: string;
  scope: string;
  client_visible_summary: string;
  internal_notes: string;
  amount: string;
  amount_type: 'estimate' | 'fixed';
  currency: string;
  target_delivery_date: string;
};

const PAGE_SIZE = 20;

const labels: Record<string, string> = {
  draft: 'Черновик',
  awaiting_proposal_approval: 'Ожидает согласования КП',
  awaiting_customer_information: 'Требуются данные от контрагента',
  approved: 'Согласован',
  in_progress: 'В работе',
  internal_review: 'Внутренняя верификация',
  awaiting_customer_review: 'На проверке у контрагента',
  changes_requested: 'Запрошены доработки',
  ready_for_delivery: 'Готов к передаче',
  delivered: 'Передан контрагенту',
  completed: 'Завершён',
  on_hold: 'Приостановлен',
  cancelled: 'Отменён',
};

const transitions: Record<string, OrderStatus[]> = {
  draft: ['awaiting_proposal_approval', 'cancelled'],
  awaiting_proposal_approval: ['awaiting_customer_information', 'approved', 'on_hold', 'cancelled'],
  awaiting_customer_information: ['awaiting_proposal_approval', 'approved', 'on_hold', 'cancelled'],
  approved: ['in_progress', 'on_hold', 'cancelled'],
  in_progress: ['internal_review', 'on_hold'],
  internal_review: ['in_progress', 'awaiting_customer_review'],
  awaiting_customer_review: ['changes_requested', 'ready_for_delivery'],
  changes_requested: ['in_progress', 'awaiting_customer_review'],
  ready_for_delivery: ['delivered', 'changes_requested'],
  delivered: ['completed', 'changes_requested'],
  on_hold: ['approved', 'in_progress', 'cancelled'],
  completed: [],
  cancelled: [],
};

const empty: Values = {
  client_id: '',
  project_id: '',
  title: '',
  scope: '',
  client_visible_summary: '',
  internal_notes: '',
  amount: '',
  amount_type: 'estimate',
  currency: 'RUB',
  target_delivery_date: '',
};

const can = (u: AuthUser, key: string) =>
  u.is_owner || u.permissions['*'] === 'all' || Object.prototype.hasOwnProperty.call(u.permissions, key);

const statusClass = (s: string) =>
  ['completed', 'approved', 'delivered', 'ready_for_delivery'].includes(s)
    ? 'order-status-good'
    : ['cancelled', 'changes_requested', 'on_hold'].includes(s)
      ? 'order-status-warning'
      : ['in_progress', 'internal_review', 'awaiting_customer_review'].includes(s)
        ? 'order-status-active'
        : 'order-status-neutral';

export default function OrdersPage({ profile, notify }: Props) {
  const [page, setPage] = useState<Page>({ items: [], total: 0, limit: PAGE_SIZE, offset: 0 });
  const [clients, setClients] = useState<Client[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);

  const [selected, setSelected] = useState<OrderRecord | null>(null);
  const [events, setEvents] = useState<OrderEvent[]>([]);
  const [messages, setMessages] = useState<OrderMessage[]>([]);
  const [changeRequests, setChangeRequests] = useState<OrderChangeRequest[]>([]);
  const [paymentSummary, setPaymentSummary] = useState<OrderPaymentSummary | null>(null);

  const [message, setMessage] = useState('');
  const [internal, setInternal] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [values, setValues] = useState<Values>(empty);
  const [formError, setFormError] = useState('');

  const [nextStatus, setNextStatus] = useState<OrderStatus | ''>('');
  const [stageMessage, setStageMessage] = useState('');
  const [stagePublic, setStagePublic] = useState(false);

  const [crTitle, setCrTitle] = useState('');
  const [crScopeDelta, setCrScopeDelta] = useState('');
  const [crAmountDelta, setCrAmountDelta] = useState('');
  const [crNewDate, setCrNewDate] = useState('');

  const [payKind, setPayKind] = useState<'payment' | 'expense'>('payment');
  const [payAmount, setPayAmount] = useState('');
  const [payStatus, setPayStatus] = useState<'planned' | 'paid'>('planned');
  const [payNote, setPayNote] = useState('');

  const canCreate = can(profile, 'orders:create');
  const canEdit = can(profile, 'orders:edit');
  const canTransition = can(profile, 'orders:transition');
  const canInternal = can(profile, 'orders:view_internal') || can(profile, 'orders:messages:internal');
  const canMessages = can(profile, 'orders:messages:view');
  const canSend = can(profile, 'orders:messages:create');
  const canArchive = can(profile, 'orders:archive');
  const canRestore = can(profile, 'orders:restore');

  const loadList = useCallback(async () => {
    setBusy(true);
    setError('');
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page.offset) });
    if (query.trim()) params.set('q', query.trim());
    if (status) params.set('status', status);
    if (showArchived) params.set('include_archived', 'true');
    try {
      const data = await api.get<Page>(`/api/v1/orders?${params}`);
      setPage(data);
      if (selected) {
        const updated = data.items.find((x) => x.id === selected.id);
        if (updated) setSelected(updated);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить реестр заказов.');
    } finally {
      setBusy(false);
    }
  }, [page.offset, query, status, showArchived, refresh]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    let active = true;
    Promise.all([
      api.get<Client[]>('/api/v1/clients?limit=250'),
      api.get<Project[]>('/api/v1/projects?limit=250'),
    ])
      .then(([cs, ps]) => {
        if (active) {
          setClients(cs.filter((x) => !x.is_archived));
          setProjects(ps.filter((x) => !x.is_archived));
        }
      })
      .catch(() => {
        if (active) {
          setClients([]);
          setProjects([]);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const loadDetails = useCallback(
    async (id: number) => {
      setError('');
      try {
        const detail = await api.get<OrderRecord>(`/api/v1/orders/${id}`);
        setSelected(detail);
        setNextStatus('');
        const [history, chat, crs, payments] = await Promise.all([
          api.get<OrderEvent[]>(`/api/v1/orders/${id}/events`),
          canMessages ? api.get<OrderMessage[]>(`/api/v1/orders/${id}/messages`) : Promise.resolve([] as OrderMessage[]),
          api.get<OrderChangeRequest[]>(`/api/v1/orders/${id}/change-requests`).catch(() => [] as OrderChangeRequest[]),
          api.get<OrderPaymentSummary>(`/api/v1/orders/${id}/payments`).catch(() => null),
        ]);
        setEvents(history);
        setMessages(chat);
        setChangeRequests(crs);
        setPaymentSummary(payments);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось загрузить карточку заказа.');
      }
    },
    [canMessages],
  );

  const availableProjects = useMemo(
    () =>
      projects.filter(
        (p) => !values.client_id || p.client_id === null || p.client_id === Number(values.client_id),
      ),
    [projects, values.client_id],
  );

  function openEditModal(order: OrderRecord) {
    setValues({
      client_id: String(order.client_id),
      project_id: order.project_id ? String(order.project_id) : '',
      title: order.title,
      scope: order.scope,
      client_visible_summary: order.client_visible_summary || '',
      internal_notes: order.internal_notes || '',
      amount: order.amount || '',
      amount_type: order.amount_type,
      currency: order.currency,
      target_delivery_date: order.target_delivery_date || '',
    });
    setFormError('');
    setEditOpen(true);
  }

  async function createOrder(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError('');
    if (!values.client_id) {
      setFormError('Выберите контрагента.');
      return;
    }
    if (values.amount_type === 'fixed' && !values.amount.trim()) {
      setFormError('Для фиксированной стоимости необходимо указать сумму.');
      return;
    }
    if (values.amount.trim() && (!Number.isFinite(Number(values.amount)) || Number(values.amount) <= 0)) {
      setFormError('Сумма должна быть положительным числом.');
      return;
    }
    setCreating(true);
    try {
      const body = {
        client_id: Number(values.client_id),
        project_id: values.project_id ? Number(values.project_id) : null,
        title: values.title.trim(),
        scope: values.scope.trim(),
        client_visible_summary: values.client_visible_summary.trim() || null,
        internal_notes: values.internal_notes.trim() || null,
        amount: values.amount.trim() || null,
        amount_type: values.amount_type,
        currency: values.currency,
        target_delivery_date: values.target_delivery_date || null,
      };
      const created = await api.post<OrderRecord>('/api/v1/orders', body);
      setCreateOpen(false);
      setValues(empty);
      setPage((p) => ({ ...p, offset: 0 }));
      setRefresh((n) => n + 1);
      notify('Черновик заказа зарегистрирован');
      await loadDetails(created.id);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Не удалось создать заказ.');
    } finally {
      setCreating(false);
    }
  }

  async function saveOrderEdit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected) return;
    setFormError('');
    const commercialEditable = ['draft', 'awaiting_proposal_approval'].includes(selected.status);
    if (commercialEditable && values.amount_type === 'fixed' && !values.amount.trim()) {
      setFormError('Для фиксированной стоимости необходимо указать сумму.');
      return;
    }
    setCreating(true);
    try {
      const payload: Record<string, unknown> = {
        project_id: values.project_id ? Number(values.project_id) : null,
        title: values.title.trim(),
        client_visible_summary: values.client_visible_summary.trim() || null,
      };
      if (canInternal) {
        payload.internal_notes = values.internal_notes.trim() || null;
      }
      if (commercialEditable) {
        payload.scope = values.scope.trim();
        payload.amount = values.amount.trim() || null;
        payload.amount_type = values.amount_type;
        payload.currency = values.currency;
        payload.target_delivery_date = values.target_delivery_date || null;
      }
      await api.patch<OrderRecord>(`/api/v1/orders/${selected.id}`, payload);
      setEditOpen(false);
      notify('Параметры заказа обновлены');
      await loadDetails(selected.id);
      setRefresh((n) => n + 1);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Не удалось обновить параметры заказа.');
    } finally {
      setCreating(false);
    }
  }

  async function changeStage(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected || !nextStatus) return;
    setCreating(true);
    try {
      await api.post(`/api/v1/orders/${selected.id}/transition`, {
        status: nextStatus,
        message: stageMessage.trim() || null,
        client_visible: stagePublic,
      });
      setStageMessage('');
      setStagePublic(false);
      notify('Этап заказа обновлён');
      await loadDetails(selected.id);
      setRefresh((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось изменить статус заказа.');
    } finally {
      setCreating(false);
    }
  }

  async function createChangeRequest(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected || !crTitle.trim() || !crScopeDelta.trim()) return;
    setCreating(true);
    try {
      await api.post(`/api/v1/orders/${selected.id}/change-requests`, {
        title: crTitle.trim(),
        scope_delta: crScopeDelta.trim(),
        amount_delta: crAmountDelta.trim() || null,
        new_delivery_date: crNewDate || null,
      });
      setCrTitle('');
      setCrScopeDelta('');
      setCrAmountDelta('');
      setCrNewDate('');
      notify('Запрос на изменение (CR) зарегистрирован');
      await loadDetails(selected.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось создать запрос на изменение.');
    } finally {
      setCreating(false);
    }
  }

  async function decideChangeRequest(crId: number, decision: 'approved' | 'rejected') {
    if (!selected) return;
    try {
      await api.post(`/api/v1/orders/${selected.id}/change-requests/${crId}/decision`, {
        status: decision,
        decision_note: decision === 'approved' ? 'Утверждено оператором' : 'Отклонено оператором',
      });
      notify(decision === 'approved' ? 'Запрос на изменение утверждён' : 'Запрос на изменение отклонён');
      await loadDetails(selected.id);
      setRefresh((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось обработать запрос на изменение.');
    }
  }

  async function addPayment(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected || !payAmount.trim()) return;
    setCreating(true);
    try {
      await api.post(`/api/v1/orders/${selected.id}/payments`, {
        kind: payKind,
        amount: payAmount.trim(),
        currency: selected.currency,
        status: payStatus,
        note: payNote.trim() || null,
      });
      setPayAmount('');
      setPayNote('');
      notify('Финансовая операция зафиксирована');
      await loadDetails(selected.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось добавить финансовую запись.');
    } finally {
      setCreating(false);
    }
  }

  async function updatePaymentStatus(paymentId: number, newStatus: 'paid' | 'cancelled') {
    if (!selected) return;
    try {
      await api.patch(`/api/v1/orders/${selected.id}/payments/${paymentId}`, { status: newStatus });
      notify('Статус платежа обновлён');
      await loadDetails(selected.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось обновить статус платежа.');
    }
  }

  async function sendMessage(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected || !message.trim()) return;
    try {
      await api.post(`/api/v1/orders/${selected.id}/messages`, {
        body: message.trim(),
        is_internal: internal,
      });
      setMessage('');
      setInternal(false);
      setMessages(await api.get<OrderMessage[]>(`/api/v1/orders/${selected.id}/messages`));
      notify('Сообщение зафиксировано');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось отправить сообщение.');
    }
  }

  async function archiveOrder() {
    if (!selected) return;
    if (!window.confirm(`Переместить заказ ${selected.order_number} в архив? Журнал событий сохранится.`)) return;
    try {
      await api.post(`/api/v1/orders/${selected.id}/archive`, {});
      notify('Заказ перемещён в архив');
      setSelected(null);
      setEvents([]);
      setMessages([]);
      setRefresh((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось архивировать заказ.');
    }
  }

  async function restoreOrder(item: OrderRecord) {
    if (!window.confirm(`Восстановить заказ ${item.order_number} из архива?`)) return;
    try {
      await api.post(`/api/v1/orders/${item.id}/restore`, {});
      notify('Заказ восстановлен в активный реестр');
      setRefresh((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось восстановить заказ.');
    }
  }

  const renderForm = (isEditing = false) => {
    const commercialFrozen =
      isEditing && selected !== null && !['draft', 'awaiting_proposal_approval'].includes(selected.status);
    return (
      <div className="form-grid">
        {!isEditing && (
          <label className="form-field">
            <span>
              Клиент <i>*</i>
            </span>
            <select
              required
              value={values.client_id}
              onChange={(e) => setValues((p) => ({ ...p, client_id: e.target.value, project_id: '' }))}
            >
              <option value="">Выбрать клиента</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className={`form-field ${isEditing ? 'field-full' : ''}`}>
          <span>Связанный проект</span>
          <select
            value={values.project_id}
            onChange={(e) => setValues((p) => ({ ...p, project_id: e.target.value }))}
          >
            <option value="">Без проекта</option>
            {availableProjects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field field-full">
          <span>
            Название заказа <i>*</i>
          </span>
          <input
            required
            minLength={2}
            maxLength={180}
            value={values.title}
            onChange={(e) => setValues((p) => ({ ...p, title: e.target.value }))}
          />
        </label>
        <label className="form-field field-full">
          <span>
            Объём работ <i>*</i>
          </span>
          <textarea
            required
            disabled={commercialFrozen}
            minLength={1}
            maxLength={20000}
            rows={3}
            value={values.scope}
            onChange={(e) => setValues((p) => ({ ...p, scope: e.target.value }))}
          />
          {commercialFrozen && (
            <small className="field-hint">
              Согласованный объём, цена и срок заморожены. Используйте «Запрос на изменение (CR)» для корректировки.
            </small>
          )}
        </label>
        <label className="form-field field-full">
          <span>Описание для клиента</span>
          <textarea
            maxLength={10000}
            rows={2}
            value={values.client_visible_summary}
            onChange={(e) => setValues((p) => ({ ...p, client_visible_summary: e.target.value }))}
          />
        </label>
        {canInternal && (
          <label className="form-field field-full">
            <span>Внутренние заметки</span>
            <textarea
              maxLength={20000}
              rows={2}
              value={values.internal_notes}
              onChange={(e) => setValues((p) => ({ ...p, internal_notes: e.target.value }))}
            />
          </label>
        )}
        <label className="form-field">
          <span>Цена</span>
          <input
            type="number"
            disabled={commercialFrozen}
            min="0.01"
            step="0.01"
            value={values.amount}
            onChange={(e) => setValues((p) => ({ ...p, amount: e.target.value }))}
          />
        </label>
        <label className="form-field">
          <span>Тип цены</span>
          <select
            disabled={commercialFrozen}
            value={values.amount_type}
            onChange={(e) => setValues((p) => ({ ...p, amount_type: e.target.value as Values['amount_type'] }))}
          >
            <option value="estimate">Предварительная оценка</option>
            <option value="fixed">Фиксированная цена</option>
          </select>
        </label>
        <label className="form-field">
          <span>Валюта</span>
          <select
            disabled={commercialFrozen}
            value={values.currency}
            onChange={(e) => setValues((p) => ({ ...p, currency: e.target.value }))}
          >
            <option value="RUB">RUB — рубль</option>
            <option value="USD">USD — доллар</option>
            <option value="EUR">EUR — евро</option>
          </select>
        </label>
        <label className="form-field">
          <span>Дата сдачи</span>
          <input
            type="date"
            disabled={commercialFrozen}
            value={values.target_delivery_date}
            onChange={(e) => setValues((p) => ({ ...p, target_delivery_date: e.target.value }))}
          />
        </label>
      </div>
    );
  };

  const pages = Math.max(1, Math.ceil(page.total / PAGE_SIZE));

  if (selected) {
    return (
      <section className="orders-workspace">
        <button
          className="portal-back"
          onClick={() => {
            setSelected(null);
            setEvents([]);
            setMessages([]);
            setRefresh((n) => n + 1);
          }}
        >
          <ArrowLeft size={16} /> Все заказы
        </button>
        {error && (
          <div className="notice notice-error" role="alert">
            {error}
          </div>
        )}
        <div className="order-detail-heading">
          <div>
            <p className="eyebrow">ЗАКАЗ {selected.order_number}</p>
            <h2>{selected.title}</h2>
            <p>
              {selected.client_name} · зарегистрирован {formatDateTime(selected.created_at)}
            </p>
            <span className={`order-status ${statusClass(selected.status)}`}>
              {labels[selected.status] || selected.status}
            </span>
          </div>
          <div className="access-user-actions">
            {canEdit && !selected.is_archived && (
              <button className="secondary-button" onClick={() => openEditModal(selected)}>
                <Settings2 size={15} /> Редактировать параметры
              </button>
            )}
            {canArchive && !selected.is_archived && (
              <button className="secondary-button" onClick={() => void archiveOrder()}>
                <Archive size={15} /> В архив
              </button>
            )}
            <button className="secondary-button" onClick={() => void loadDetails(selected.id)}>
              <RefreshCw size={15} /> Обновить
            </button>
          </div>
        </div>

        <div className="order-detail-grid">
          <section className="panel order-panel">
            <div className="panel-heading">
              <div>
                <h2>Паспорт заказа</h2>
                <p>Коммерческие параметры и технический объём</p>
              </div>
              <CircleDollarSign size={18} />
            </div>
            <div className="order-facts">
              <div>
                <span>Контрагент</span>
                <strong>{selected.client_name}</strong>
              </div>
              <div>
                <span>Стоимость</span>
                <strong>
                  {selected.amount
                    ? `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(Number(selected.amount))} ${selected.currency}${selected.amount_type === 'estimate' ? ' · оценка' : ''}`
                    : 'Уточняется'}
                </strong>
              </div>
              <div>
                <span>Целевой срок сдачи</span>
                <strong>{formatDate(selected.target_delivery_date)}</strong>
              </div>
              <div>
                <span>Текущий статус</span>
                <strong>{labels[selected.status] || selected.status}</strong>
              </div>
            </div>
            <div className="order-text-block">
              <h3>Согласованный объём работ</h3>
              <p>{selected.scope}</p>
            </div>
            <div className="order-text-block">
              <h3>Описание для клиентского портала</h3>
              <p>{selected.client_visible_summary || 'Не указано.'}</p>
            </div>
            {canInternal && selected.internal_notes && (
              <div className="order-text-block order-internal">
                <h3>
                  <ShieldCheck size={14} /> Внутренние технические заметки
                </h3>
                <p>{selected.internal_notes}</p>
              </div>
            )}
          </section>

          <section className="panel order-panel">
            <div className="panel-heading">
              <div>
                <h2>Журнал этапов и переходов</h2>
                <p>Хронология жизненного цикла заказа</p>
              </div>
              <CalendarDays size={18} />
            </div>
            {events.length ? (
              <ol className="portal-timeline">
                {events.map((ev) => (
                  <li key={ev.id}>
                    <i />
                    <div>
                      <strong>{ev.to_status ? labels[ev.to_status] || ev.to_status : 'Событие'}</strong>
                      {ev.message && <p>{ev.message}</p>}
                      <time>{formatDateTime(ev.created_at)}</time>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="portal-empty">Записи появятся после изменения этапа заказа.</div>
            )}
            {canTransition && (transitions[selected.status] || []).length > 0 && (
              <form className="transition-form" onSubmit={changeStage}>
                <h3>Перевод этапа</h3>
                <label className="form-field">
                  <span>Следующий статус</span>
                  <select
                    required
                    value={nextStatus}
                    onChange={(e) => setNextStatus(e.target.value as OrderStatus | '')}
                  >
                    <option value="">Выбрать этап</option>
                    {transitions[selected.status].map((s) => (
                      <option key={s} value={s}>
                        {labels[s]}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-field">
                  <span>Комментарий оператора</span>
                  <textarea
                    rows={2}
                    maxLength={2000}
                    value={stageMessage}
                    onChange={(e) => setStageMessage(e.target.value)}
                  />
                </label>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={stagePublic}
                    onChange={(e) => setStagePublic(e.target.checked)}
                  />
                  <span>Опубликовать событие в клиентском портале</span>
                </label>
                <button className="primary-button" disabled={creating || !nextStatus}>
                  {creating ? 'Применение…' : 'Сохранить этап'}
                </button>
              </form>
            )}
          </section>
        </div>

        <div className="order-detail-grid">
          <section className="panel order-panel">
            <div className="panel-heading">
              <div>
                <h2>Запросы на изменение (Change Requests)</h2>
                <p>Контролируемая модификация согласованного объёма, бюджета и сроков</p>
              </div>
              <FileDiff size={18} />
            </div>
            {changeRequests.length ? (
              <div className="activity-list">
                {changeRequests.map((cr) => (
                  <div className="activity-row" key={cr.id}>
                    <div className="row-info">
                      <strong>
                        #{cr.id} · {cr.title} (
                        {cr.status === 'approved'
                          ? 'Согласован'
                          : cr.status === 'rejected'
                            ? 'Отклонён'
                            : 'На согласовании'}
                        )
                      </strong>
                      <small>
                        {cr.scope_delta}
                        {cr.amount_delta ? ` · Дельта: ${cr.amount_delta} ${selected.currency}` : ''}
                        {cr.new_delivery_date ? ` · Новый срок: ${formatDate(cr.new_delivery_date)}` : ''}
                      </small>
                    </div>
                    {canEdit && cr.status === 'pending' && (
                      <div className="row-actions">
                        <button
                          className="icon-button"
                          title="Утвердить изменение"
                          onClick={() => void decideChangeRequest(cr.id, 'approved')}
                        >
                          <Check size={14} />
                        </button>
                        <button
                          className="icon-button"
                          title="Отклонить изменение"
                          onClick={() => void decideChangeRequest(cr.id, 'rejected')}
                        >
                          <X size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="portal-empty">Запросов на изменение условий не зарегистрировано.</div>
            )}
            {canEdit && !selected.is_archived && (
              <form className="transition-form" onSubmit={createChangeRequest}>
                <h3>Новый запрос на изменение (CR)</h3>
                <label className="form-field">
                  <span>Наименование изменения</span>
                  <input
                    required
                    minLength={2}
                    maxLength={180}
                    value={crTitle}
                    onChange={(e) => setCrTitle(e.target.value)}
                    placeholder="Например, Интеграция дополнительного платёжного шлюза"
                  />
                </label>
                <label className="form-field">
                  <span>Описание изменений объёма</span>
                  <textarea
                    required
                    rows={2}
                    value={crScopeDelta}
                    onChange={(e) => setCrScopeDelta(e.target.value)}
                  />
                </label>
                <div className="form-grid">
                  <label className="form-field">
                    <span>Изменение стоимости (+/-)</span>
                    <input
                      type="number"
                      step="0.01"
                      value={crAmountDelta}
                      onChange={(e) => setCrAmountDelta(e.target.value)}
                      placeholder="15000.00"
                    />
                  </label>
                  <label className="form-field">
                    <span>Новый срок сдачи</span>
                    <input type="date" value={crNewDate} onChange={(e) => setCrNewDate(e.target.value)} />
                  </label>
                </div>
                <button className="primary-button" disabled={creating || !crTitle.trim() || !crScopeDelta.trim()}>
                  Создать запрос на изменение
                </button>
              </form>
            )}
          </section>

          <section className="panel order-panel">
            <div className="panel-heading">
              <div>
                <h2>Финансовый реестр заказа</h2>
                <p>Учёт платежей контрагента, операционных расходов и остатка по договору</p>
              </div>
              <CircleDollarSign size={18} />
            </div>
            {paymentSummary && (
              <div className="order-facts">
                <div>
                  <span>Оплачено</span>
                  <strong>
                    {paymentSummary.paid_amount} {paymentSummary.currency}
                  </strong>
                </div>
                <div>
                  <span>Остаток к оплате</span>
                  <strong>
                    {paymentSummary.balance_due} {paymentSummary.currency}
                  </strong>
                </div>
                <div>
                  <span>Ожидается (план)</span>
                  <strong>
                    {paymentSummary.planned_amount} {paymentSummary.currency}
                  </strong>
                </div>
                <div>
                  <span>Расходы контура</span>
                  <strong>
                    {paymentSummary.expenses_amount} {paymentSummary.currency}
                  </strong>
                </div>
              </div>
            )}
            {paymentSummary?.items.length ? (
              <div className="activity-list">
                {paymentSummary.items.map((p) => (
                  <div className="activity-row" key={p.id}>
                    <div className="row-info">
                      <strong>
                        {p.kind === 'payment' ? 'Платёж клиента' : 'Внутренний расход'}: {p.amount} {p.currency} (
                        {p.status === 'paid' ? 'Проведён' : p.status === 'cancelled' ? 'Отменён' : 'Запланирован'})
                      </strong>
                      <small>{p.note || 'Без примечания'}</small>
                    </div>
                    {canEdit && p.status === 'planned' && (
                      <div className="row-actions">
                        <button
                          className="icon-button"
                          title="Отметить как проведённый"
                          onClick={() => void updatePaymentStatus(p.id, 'paid')}
                        >
                          <Check size={14} />
                        </button>
                        <button
                          className="icon-button"
                          title="Отменить запись"
                          onClick={() => void updatePaymentStatus(p.id, 'cancelled')}
                        >
                          <X size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="portal-empty">Финансовые записи по заказу отсутствуют.</div>
            )}
            {canEdit && !selected.is_archived && (
              <form className="transition-form" onSubmit={addPayment}>
                <h3>Зафиксировать платёж / расход</h3>
                <div className="form-grid">
                  <label className="form-field">
                    <span>Тип операции</span>
                    <select
                      value={payKind}
                      onChange={(e) => setPayKind(e.target.value as 'payment' | 'expense')}
                    >
                      <option value="payment">Платёж от клиента</option>
                      <option value="expense">Операционный расход</option>
                    </select>
                  </label>
                  <label className="form-field">
                    <span>Статус</span>
                    <select value={payStatus} onChange={(e) => setPayStatus(e.target.value as 'planned' | 'paid')}>
                      <option value="planned">Запланирован</option>
                      <option value="paid">Оплачен / проведён</option>
                    </select>
                  </label>
                </div>
                <div className="form-grid">
                  <label className="form-field">
                    <span>Сумма ({selected.currency})</span>
                    <input
                      type="number"
                      required
                      min="0.01"
                      step="0.01"
                      value={payAmount}
                      onChange={(e) => setPayAmount(e.target.value)}
                    />
                  </label>
                  <label className="form-field">
                    <span>Примечание / назначение</span>
                    <input
                      maxLength={1000}
                      value={payNote}
                      onChange={(e) => setPayNote(e.target.value)}
                      placeholder="Аванс 50% / оплата хостинга"
                    />
                  </label>
                </div>
                <button className="primary-button" disabled={creating || !payAmount.trim()}>
                  Добавить запись
                </button>
              </form>
            )}
          </section>
        </div>

        {canMessages && (
          <section className="panel order-panel order-chat-panel">
            <div className="panel-heading">
              <div>
                <h2>Протокол коммуникации</h2>
                <p>Сообщения по выбранному заказу (внешние и внутренние)</p>
              </div>
              <MessageSquare size={18} />
            </div>
            {messages.length ? (
              <div className="portal-chat-list">
                {messages.map((m) => (
                  <article
                    className={`portal-chat-message ${m.is_internal ? 'portal-chat-internal' : ''}`}
                    key={m.id}
                  >
                    <div>
                      <strong>
                        {m.author_username || 'Оператор'}
                        {m.is_internal ? ' · внутренний контур' : ''}
                      </strong>
                      <time>{formatDateTime(m.created_at)}</time>
                    </div>
                    <p>{m.body}</p>
                  </article>
                ))}
              </div>
            ) : (
              <div className="portal-empty">Сообщений в протоколе пока нет.</div>
            )}
            {canSend && (
              <form className="portal-message-form" onSubmit={sendMessage}>
                <label className="form-field">
                  <span>Новое сообщение</span>
                  <textarea
                    rows={3}
                    required
                    maxLength={10000}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="Введите сообщение по заказу…"
                  />
                </label>
                {canInternal && (
                  <label className="checkbox-field">
                    <input
                      type="checkbox"
                      checked={internal}
                      onChange={(e) => setInternal(e.target.checked)}
                    />
                    <span>Внутреннее сообщение (скрыто от клиентского портала)</span>
                  </label>
                )}
                <button className="primary-button" disabled={!message.trim()}>
                  <Send size={15} /> Отправить
                </button>
              </form>
            )}
          </section>
        )}

        {editOpen && (
          <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(e) => {
              if (e.target === e.currentTarget) setEditOpen(false);
            }}
          >
            <section
              className="modal-card"
              role="dialog"
              aria-modal="true"
              aria-labelledby="edit-order-heading"
            >
              <div className="modal-heading">
                <div>
                  <p className="eyebrow">КОРРЕКТИРОВКА ПАРАМЕТРОВ</p>
                  <h2 id="edit-order-heading">Редактировать заказ {selected.order_number}</h2>
                </div>
                <button
                  className="icon-button"
                  aria-label="Закрыть"
                  type="button"
                  onClick={() => setEditOpen(false)}
                >
                  ×
                </button>
              </div>
              <form onSubmit={saveOrderEdit}>
                {renderForm(true)}
                {formError && (
                  <p className="field-error" role="alert">
                    {formError}
                  </p>
                )}
                <div className="modal-footer">
                  <button type="button" className="secondary-button" onClick={() => setEditOpen(false)}>
                    Отмена
                  </button>
                  <button className="primary-button" disabled={creating}>
                    {creating ? 'Сохранение…' : 'Сохранить изменения'}
                  </button>
                </div>
              </form>
            </section>
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="orders-workspace">
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
          <button className="text-button" onClick={() => setRefresh((n) => n + 1)}>
            Повторить
          </button>
        </div>
      )}
      <div className="orders-toolbar">
        <form
          className="search-field"
          onSubmit={(e) => {
            e.preventDefault();
            setPage((p) => ({ ...p, offset: 0 }));
            setQuery(q);
          }}
        >
          <Search size={15} />
          <input
            aria-label="Поиск заказов"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Поиск по наименованию или номеру заказа…"
          />
          <button type="submit" aria-label="Найти">
            <Search size={14} />
          </button>
        </form>
        <select
          aria-label="Фильтр по статусу"
          className="filter-select"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage((p) => ({ ...p, offset: 0 }));
          }}
        >
          <option value="">Все статусы</option>
          {Object.entries(labels).map(([key, value]) => (
            <option key={key} value={key}>
              {value}
            </option>
          ))}
        </select>
        <label className="sort-due archived-toggle">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => {
              setShowArchived(e.target.checked);
              setPage((p) => ({ ...p, offset: 0 }));
            }}
          />
          Включая архив
        </label>
        {canCreate && (
          <button
            className="primary-button"
            onClick={() => {
              setValues(empty);
              setFormError('');
              setCreateOpen(true);
            }}
          >
            <Plus size={15} /> Новый заказ
          </button>
        )}
      </div>

      <div className="order-list-summary">
        <span>
          {page.total} {page.total === 1 ? 'заказ' : page.total > 1 && page.total < 5 ? 'заказа' : 'заказов'}
        </span>
        <button className="text-button" onClick={() => setRefresh((n) => n + 1)}>
          <RefreshCw size={13} /> Обновить
        </button>
      </div>

      {busy ? (
        <div className="loading">Загрузка реестра заказов…</div>
      ) : page.items.length ? (
        <div className="admin-order-list">
          {page.items.map((item) => (
            <article
              className={`admin-order-card${item.is_archived ? ' order-card-archived' : ''}`}
              key={item.id}
            >
              <button
                className="admin-order-main admin-order-main-button"
                aria-label={`Открыть заказ ${item.order_number}`}
                disabled={item.is_archived}
                onClick={() => void loadDetails(item.id)}
              >
                <small>
                  {item.order_number} · {item.client_name}
                  {item.is_archived ? ' · В архиве' : ''}
                </small>
                <strong>{item.title}</strong>
                <p>{item.client_visible_summary || item.scope}</p>
              </button>
              <div className="admin-order-meta">
                <span className={`order-status ${statusClass(item.status)}`}>
                  {labels[item.status] || item.status}
                </span>
                <strong>
                  {item.amount
                    ? `${Number(item.amount).toLocaleString('ru-RU')} ${item.currency}`
                    : 'Цена уточняется'}
                </strong>
                <small>Срок: {formatDate(item.target_delivery_date)}</small>
                {item.is_archived && canRestore && (
                  <button className="secondary-button" onClick={() => void restoreOrder(item)}>
                    <RefreshCw size={14} /> Восстановить
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="portal-panel portal-empty-panel">
          <CircleDollarSign size={24} />
          <h2>Заказов пока нет</h2>
          <p>
            {query
              ? 'Измените параметры поискового фильтра.'
              : 'Зарегистрируйте первый черновик заказа для фиксации договорённостей с контрагентом.'}
          </p>
          {canCreate && (
            <button className="primary-button" onClick={() => setCreateOpen(true)}>
              <Plus size={15} /> Создать заказ
            </button>
          )}
        </div>
      )}

      {page.total > PAGE_SIZE && (
        <div className="orders-pagination">
          <span>
            Страница {Math.floor(page.offset / PAGE_SIZE) + 1} из {pages}
          </span>
          <div>
            <button
              className="secondary-button"
              disabled={page.offset === 0 || busy}
              onClick={() => setPage((p) => ({ ...p, offset: Math.max(0, p.offset - PAGE_SIZE) }))}
            >
              Назад
            </button>
            <button
              className="secondary-button"
              disabled={page.offset + PAGE_SIZE >= page.total || busy}
              onClick={() => setPage((p) => ({ ...p, offset: p.offset + PAGE_SIZE }))}
            >
              Дальше
            </button>
          </div>
        </div>
      )}

      {createOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setCreateOpen(false);
          }}
        >
          <section
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-order-heading"
          >
            <div className="modal-heading">
              <div>
                <p className="eyebrow">РЕГИСТРАЦИЯ ЗАКАЗА</p>
                <h2 id="create-order-heading">Создать заказ</h2>
              </div>
              <button
                className="icon-button"
                type="button"
                aria-label="Закрыть"
                onClick={() => setCreateOpen(false)}
              >
                ×
              </button>
            </div>
            <form onSubmit={createOrder}>
              {renderForm(false)}
              {formError && (
                <p className="field-error" role="alert">
                  {formError}
                </p>
              )}
              <div className="modal-footer">
                <button type="button" className="secondary-button" onClick={() => setCreateOpen(false)}>
                  Отмена
                </button>
                <button className="primary-button" disabled={creating}>
                  {creating ? 'Создание…' : 'Создать черновик'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
