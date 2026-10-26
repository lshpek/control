import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  ArrowLeft,
  CalendarDays,
  CheckCircle2,
  CircleDollarSign,
  FileDiff,
  FileText,
  LogOut,
  MessageCircle,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { api } from './api';
import { formatDate, formatDateTime } from './formatting';
import type {
  AuthUser,
  ClientOrderMessage,
  OrderChangeRequest,
  OrderEvent,
  OrderPortalRecord,
  PortalPaymentSummary,
} from './types';

type Props = {
  user: AuthUser;
  onLogout: () => void;
};

type PortalIdentity = {
  id: number;
  username: string;
  customer_id: number;
  customer_name: string;
};

type ListResult = {
  items: OrderPortalRecord[];
  total: number;
  limit: number;
  offset: number;
};

type PortalMessage = {
  id: number;
  author_username: string | null;
  body: string;
  created_at: string;
};

const statusLabels: Record<string, string> = {
  awaiting_proposal_approval: 'Ожидает согласования коммерческого предложения',
  awaiting_customer_information: 'Ожидается информация от контрагента',
  approved: 'Условия согласованы',
  in_progress: 'В разработке',
  internal_review: 'Внутренняя верификация',
  awaiting_customer_review: 'Ожидает проверки заказчиком',
  changes_requested: 'Запрошены доработки',
  ready_for_delivery: 'Готов к передаче',
  delivered: 'Передан заказчику',
  completed: 'Выполнен и закрыт',
  on_hold: 'Приостановлен',
  cancelled: 'Отменён',
  draft: 'Черновик',
};

export default function PortalApp({ user, onLogout }: Props) {
  const [identity, setIdentity] = useState<PortalIdentity | null>(null);
  const [orders, setOrders] = useState<OrderPortalRecord[]>([]);
  const [selected, setSelected] = useState<OrderPortalRecord | null>(null);
  const [events, setEvents] = useState<OrderEvent[]>([]);
  const [messages, setMessages] = useState<PortalMessage[]>([]);
  const [changeRequests, setChangeRequests] = useState<OrderChangeRequest[]>([]);
  const [payments, setPayments] = useState<PortalPaymentSummary | null>(null);
  const [draft, setDraft] = useState('');
  const [decisionNote, setDecisionNote] = useState('');
  const [busy, setBusy] = useState(true);
  const [sending, setSending] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [error, setError] = useState('');
  const [refreshCount, setRefreshCount] = useState(0);

  const loadOrders = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [me, result] = await Promise.all([
        api.get<PortalIdentity>('/api/v1/portal/me'),
        api.get<ListResult>('/api/v1/portal/orders?limit=50&offset=0'),
      ]);
      setIdentity(me);
      setOrders(result.items);
      setSelected((current) =>
        current ? result.items.find((item) => item.id === current.id) ?? null : null,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось загрузить реестр заказов.');
    } finally {
      setBusy(false);
    }
  }, []);

  const loadDetails = useCallback(async (order: OrderPortalRecord) => {
    setSelected(order);
    setError('');
    try {
      const [detail, history, chat, crs, pay] = await Promise.all([
        api.get<OrderPortalRecord>(`/api/v1/portal/orders/${order.id}`),
        api.get<OrderEvent[]>(`/api/v1/portal/orders/${order.id}/events`),
        api.get<PortalMessage[]>(`/api/v1/portal/orders/${order.id}/messages`),
        api.get<OrderChangeRequest[]>(`/api/v1/portal/orders/${order.id}/change-requests`).catch(() => []),
        api.get<PortalPaymentSummary>(`/api/v1/portal/orders/${order.id}/payments`).catch(() => null),
      ]);
      setSelected(detail);
      setEvents(history);
      setMessages(chat);
      setChangeRequests(crs);
      setPayments(pay);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось загрузить данные заказа.');
    }
  }, []);

  useEffect(() => {
    void loadOrders();
  }, [loadOrders, refreshCount]);

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !draft.trim()) return;
    setSending(true);
    setError('');
    try {
      await api.post<ClientOrderMessage>(`/api/v1/portal/orders/${selected.id}/messages`, {
        body: draft.trim(),
      });
      setDraft('');
      setMessages(await api.get<PortalMessage[]>(`/api/v1/portal/orders/${selected.id}/messages`));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось отправить сообщение.');
    } finally {
      setSending(false);
    }
  }

  async function submitDecision(
    action: 'approve_proposal' | 'request_info' | 'accept_delivery' | 'request_changes',
  ) {
    if (!selected) return;
    if (action === 'request_changes' && !decisionNote.trim()) {
      setError('Укажите перечень замечаний в поле комментария перед отправкой запроса на доработку.');
      return;
    }
    setDeciding(true);
    setError('');
    try {
      const updated = await api.post<OrderPortalRecord>(
        `/api/v1/portal/orders/${selected.id}/decision`,
        {
          action,
          comment: decisionNote.trim() || null,
        },
      );
      setDecisionNote('');
      await loadDetails(updated);
      setRefreshCount((n) => n + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось зафиксировать решение по заказу.');
    } finally {
      setDeciding(false);
    }
  }

  async function decideChangeRequest(crId: number, status: 'approved' | 'rejected') {
    if (!selected) return;
    setDeciding(true);
    setError('');
    try {
      await api.post(`/api/v1/portal/orders/${selected.id}/change-requests/${crId}/decision`, {
        status,
        decision_note: status === 'approved' ? 'Согласовано заказчиком в портале' : 'Отклонено заказчиком',
      });
      await loadDetails(selected);
      setRefreshCount((n) => n + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось обработать запрос на изменение.');
    } finally {
      setDeciding(false);
    }
  }

  const actionableStage =
    selected &&
    ['awaiting_proposal_approval', 'awaiting_customer_review', 'delivered'].includes(selected.status);

  return (
    <div className="portal-shell">
      <header className="portal-header">
        <div className="auth-brand">
          <span className="auth-brand-mark">
            <FileText size={21} />
          </span>
          <span>
            <strong>BOTVEX</strong>
            <small>КЛИЕНТСКИЙ КОНТУР УПРАВЛЕНИЯ ЗАКАЗАМИ</small>
          </span>
        </div>
        <div className="portal-user">
          <span>{identity?.customer_name ?? user.username}</span>
          <button className="secondary-button" onClick={onLogout}>
            <LogOut size={15} />
            Выйти
          </button>
        </div>
      </header>

      <main className="portal-main">
        {error && (
          <div className="auth-alert" role="alert">
            {error}
            <button className="text-button" onClick={() => setRefreshCount((n) => n + 1)}>
              Повторить
            </button>
          </div>
        )}

        {selected ? (
          <>
            <button
              className="portal-back"
              onClick={() => {
                setSelected(null);
                setEvents([]);
                setMessages([]);
                setError('');
              }}
            >
              <ArrowLeft size={16} /> Все заказы
            </button>

            <section className="portal-order-head">
              <div>
                <p className="auth-eyebrow">ЗАКАЗ {selected.order_number}</p>
                <h1>{selected.title}</h1>
                <span className={`order-status order-status-${selected.status}`}>
                  {statusLabels[selected.status] ?? selected.status}
                </span>
              </div>
              <button className="secondary-button" onClick={() => void loadDetails(selected)}>
                <RefreshCw size={15} />
                Обновить данные
              </button>
            </section>

            {actionableStage && (
              <section className="portal-panel" style={{ marginBottom: 14 }}>
                <div className="portal-section-title">
                  <div>
                    <h2>Требуется подтверждение со стороны заказчика</h2>
                    <p>
                      {selected.status === 'awaiting_proposal_approval'
                        ? 'Проверьте параметры коммерческого предложения и подтвердите запуск работ.'
                        : 'Проверьте переданный результат работ и подтвердите приёмку либо укажите замечания.'}
                    </p>
                  </div>
                  <CheckCircle2 size={19} />
                </div>
                <label className="form-field" style={{ marginTop: 12 }}>
                  <span>Комментарий или замечания (обязательно при запросе доработок)</span>
                  <textarea
                    rows={2}
                    maxLength={2000}
                    value={decisionNote}
                    onChange={(e) => setDecisionNote(e.target.value)}
                    placeholder="Укажите комментарий к решению…"
                  />
                </label>
                <div className="access-user-actions">
                  {selected.status === 'awaiting_proposal_approval' ? (
                    <>
                      <button
                        className="primary-button"
                        disabled={deciding}
                        onClick={() => void submitDecision('approve_proposal')}
                      >
                        Согласовать коммерческое предложение
                      </button>
                      <button
                        className="secondary-button"
                        disabled={deciding}
                        onClick={() => void submitDecision('request_info')}
                      >
                        Запросить уточнение условий
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        className="primary-button"
                        disabled={deciding}
                        onClick={() => void submitDecision('accept_delivery')}
                      >
                        Принять результат этапа / поставку
                      </button>
                      <button
                        className="secondary-button"
                        disabled={deciding}
                        onClick={() => void submitDecision('request_changes')}
                      >
                        Запросить доработки
                      </button>
                    </>
                  )}
                </div>
              </section>
            )}

            <div className="portal-detail-grid">
              <section className="portal-panel">
                <h2>Параметры заказа</h2>
                <p className="portal-summary">
                  {selected.client_visible_summary || 'Дополнительное описание для портала не указано.'}
                </p>
                <div className="portal-data-row">
                  <span>
                    <CalendarDays size={15} />
                    Целевой срок сдачи
                  </span>
                  <strong>{formatDate(selected.target_delivery_date)}</strong>
                </div>
                <div className="portal-data-row">
                  <span>Стоимость</span>
                  <strong>
                    {selected.amount
                      ? `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(Number(selected.amount))} ${selected.currency}${selected.amount_type === 'estimate' ? ' · оценка' : ''}`
                      : 'Уточняется'}
                  </strong>
                </div>
                {payments && (
                  <>
                    <div className="portal-data-row">
                      <span>
                        <CircleDollarSign size={15} />
                        Оплачено по договору
                      </span>
                      <strong>
                        {payments.paid_amount} {payments.currency}
                      </strong>
                    </div>
                    <div className="portal-data-row">
                      <span>Остаток к оплате</span>
                      <strong>
                        {payments.balance_due} {payments.currency}
                      </strong>
                    </div>
                  </>
                )}
              </section>

              <section className="portal-panel">
                <h2>История и этапы</h2>
                {events.length ? (
                  <ol className="portal-timeline">
                    {events.map((item) => (
                      <li key={item.id}>
                        <i />
                        <div>
                          <strong>
                            {item.to_status
                              ? statusLabels[item.to_status] ?? item.to_status
                              : 'Обновление заказа'}
                          </strong>
                          {item.message && <p>{item.message}</p>}
                          <time>{formatDateTime(item.created_at)}</time>
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <div className="portal-empty">Записи появятся по мере движения заказа по этапам.</div>
                )}
              </section>
            </div>

            {changeRequests.length > 0 && (
              <section className="portal-panel" style={{ marginTop: 14 }}>
                <div className="portal-section-title">
                  <div>
                    <h2>Запросы на изменение условий (Change Requests)</h2>
                    <p>Дополнительные работы и корректировки сроков по заказу</p>
                  </div>
                  <FileDiff size={19} />
                </div>
                <div className="portal-chat-list">
                  {changeRequests.map((cr) => (
                    <article className="portal-chat-message" key={cr.id}>
                      <div>
                        <strong>
                          #{cr.id} · {cr.title}
                        </strong>
                        <time>
                          {cr.status === 'approved'
                            ? 'Согласован'
                            : cr.status === 'rejected'
                              ? 'Отклонён'
                              : 'Ожидает решения'}
                        </time>
                      </div>
                      <p>
                        {cr.scope_delta}
                        {cr.amount_delta ? ` | Изменение суммы: ${cr.amount_delta} ${selected.currency}` : ''}
                        {cr.new_delivery_date ? ` | Новый срок: ${formatDate(cr.new_delivery_date)}` : ''}
                      </p>
                      {cr.status === 'pending' && (
                        <div className="access-user-actions">
                          <button
                            className="primary-button"
                            disabled={deciding}
                            onClick={() => void decideChangeRequest(cr.id, 'approved')}
                          >
                            Согласовать изменение
                          </button>
                          <button
                            className="secondary-button"
                            disabled={deciding}
                            onClick={() => void decideChangeRequest(cr.id, 'rejected')}
                          >
                            Отклонить
                          </button>
                        </div>
                      )}
                    </article>
                  ))}
                </div>
              </section>
            )}

            <section className="portal-panel portal-messages">
              <div className="portal-section-title">
                <div>
                  <h2>Протокол сообщений по заказу</h2>
                  <p>Прямой канал связи с диспетчерской и проектной группой BOTVEX.</p>
                </div>
                <MessageCircle size={19} />
              </div>
              {messages.length ? (
                <div className="portal-chat-list">
                  {messages.map((message) => (
                    <article
                      className={`portal-chat-message ${message.author_username === user.username ? 'portal-chat-mine' : ''}`}
                      key={message.id}
                    >
                      <div>
                        <strong>
                          {message.author_username === user.username
                            ? 'Вы'
                            : message.author_username || 'Команда BOTVEX'}
                        </strong>
                        <time>{formatDateTime(message.created_at)}</time>
                      </div>
                      <p>{message.body}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="portal-empty">Сообщений пока нет. Вы можете направить запрос через форму ниже.</div>
              )}
              <form className="portal-message-form" onSubmit={sendMessage}>
                <label className="form-field">
                  <span>Сообщение</span>
                  <textarea
                    required
                    maxLength={10000}
                    rows={3}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="Введите вопрос или комментарий по заказу…"
                  />
                </label>
                <button className="primary-button" disabled={sending || !draft.trim()}>
                  {sending ? 'Отправка…' : 'Отправить сообщение'}
                </button>
              </form>
            </section>
          </>
        ) : (
          <>
            <section className="portal-welcome">
              <p className="auth-eyebrow">BOTVEX CLIENT PORTAL // АВТОРИЗОВАННЫЙ ДОСТУП КОНТРАГЕНТА</p>
              <h1>Здравствуйте, {identity?.customer_name ?? user.username}</h1>
              <p>
                В данном контуре отображаются активные заказы, этапы выполнения, расчёты и протоколы согласования, привязанные к вашей организации.
              </p>
            </section>
            <div className="portal-list-heading">
              <h2>Активные заказы контрагента</h2>
              <button className="secondary-button" onClick={() => setRefreshCount((n) => n + 1)}>
                <RefreshCw size={15} />
                Обновить
              </button>
            </div>
            {busy ? (
              <div className="auth-loading">Загрузка реестра заказов…</div>
            ) : orders.length ? (
              <div className="portal-order-list">
                {orders.map((order) => (
                  <button
                    className="portal-order-card"
                    key={order.id}
                    onClick={() => void loadDetails(order)}
                  >
                    <div>
                      <small>{order.order_number}</small>
                      <strong>{order.title}</strong>
                      <p>{order.client_visible_summary || 'Техническое описание уточняется.'}</p>
                      <span className={`order-status order-status-${order.status}`}>
                        {statusLabels[order.status] ?? order.status}
                      </span>
                    </div>
                    <ArrowLeft className="portal-order-arrow" size={17} />
                  </button>
                ))}
              </div>
            ) : (
              <div className="portal-panel portal-empty-panel">
                <ShieldCheck size={25} />
                <h2>Заказов пока нет</h2>
                <p>
                  После регистрации и публикации заказа проектной командой BOTVEX он автоматически появится в вашем контуре.
                </p>
              </div>
            )}
          </>
        )}
        <footer className="portal-footer">
          КОНТУР БЕЗОПАСНОСТИ BOTVEX · Доступ разграничен на уровне сервера (RBAC own_customer).
        </footer>
      </main>
    </div>
  );
}
