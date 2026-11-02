import {useCallback, useEffect, useState, type FormEvent} from 'react';
import {ArrowLeft, CalendarDays, FileText, LogOut, MessageCircle, RefreshCw, ShieldCheck} from 'lucide-react';
import {api} from './api';
import {formatDate, formatDateTime} from './formatting';
import type {AuthUser, ClientOrderMessage, OrderEvent, OrderPortalRecord} from './types';

type Props = {user: AuthUser; onLogout: () => void};
type PortalIdentity = {id: number; username: string; customer_id: number; customer_name: string};
type ListResult = {items: OrderPortalRecord[]; total: number; limit: number; offset: number};
type PortalMessage = {id: number; author_username: string|null; body: string; created_at: string};
const statusLabels: Record<string,string> = {
  awaiting_proposal_approval:'Ожидает согласования предложения', awaiting_customer_information:'Нужна информация от клиента', approved:'Согласован', in_progress:'В работе', internal_review:'Внутренняя проверка', awaiting_customer_review:'Ожидает проверки клиента', changes_requested:'Запрошены изменения', ready_for_delivery:'Готов к передаче', delivered:'Передан', completed:'Завершён', on_hold:'Приостановлен', cancelled:'Отменён', draft:'Черновик',
};

export default function PortalApp({user, onLogout}: Props) {
  const [identity, setIdentity] = useState<PortalIdentity|null>(null);
  const [orders, setOrders] = useState<OrderPortalRecord[]>([]);
  const [selected, setSelected] = useState<OrderPortalRecord|null>(null);
  const [events, setEvents] = useState<OrderEvent[]>([]);
  const [messages, setMessages] = useState<PortalMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [refreshCount, setRefreshCount] = useState(0);

  const loadOrders = useCallback(async () => {
    setBusy(true); setError('');
    try {
      const [me, result] = await Promise.all([
        api.get<PortalIdentity>('/api/v1/portal/me'),
        api.get<ListResult>('/api/v1/portal/orders?limit=50&offset=0'),
      ]);
      setIdentity(me); setOrders(result.items);
      setSelected(current => current ? result.items.find(item=>item.id===current.id) ?? null : null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось загрузить заказы.'); }
    finally { setBusy(false); }
  }, []);

  const loadDetails = useCallback(async (order: OrderPortalRecord) => {
    setSelected(order); setError('');
    try {
      const [detail, history, chat] = await Promise.all([
        api.get<OrderPortalRecord>(`/api/v1/portal/orders/${order.id}`),
        api.get<OrderEvent[]>(`/api/v1/portal/orders/${order.id}/events`),
        api.get<PortalMessage[]>(`/api/v1/portal/orders/${order.id}/messages`),
      ]);
      setSelected(detail); setEvents(history); setMessages(chat);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось загрузить заказ.'); }
  }, []);

  useEffect(() => { void loadOrders(); }, [loadOrders, refreshCount]);

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if(!selected || !draft.trim()) return;
    setSending(true); setError('');
    try {
      await api.post<ClientOrderMessage>(`/api/v1/portal/orders/${selected.id}/messages`, {body:draft.trim()});
      setDraft('');
      setMessages(await api.get<PortalMessage[]>(`/api/v1/portal/orders/${selected.id}/messages`));
    } catch(reason) { setError(reason instanceof Error ? reason.message : 'Не удалось отправить сообщение.'); }
    finally { setSending(false); }
  }

  return <div className="portal-shell">
    <header className="portal-header"><div className="auth-brand"><span className="auth-brand-mark"><FileText size={21}/></span><span><strong>BOTVEX</strong><small>КЛИЕНТСКИЙ ПОРТАЛ</small></span></div><div className="portal-user"><span>{identity?.customer_name ?? user.username}</span><button className="secondary-button" onClick={onLogout}><LogOut size={15}/>Выйти</button></div></header>
    <main className="portal-main">
      {error && <div className="auth-alert" role="alert">{error}<button className="text-button" onClick={()=>setRefreshCount(n=>n+1)}>Повторить</button></div>}
      {selected ? <>
        <button className="portal-back" onClick={()=>{setSelected(null);setEvents([]);setMessages([]);setError('');}}><ArrowLeft size={16}/> Все заказы</button>
        <section className="portal-order-head"><div><p className="auth-eyebrow">ЗАКАЗ {selected.order_number}</p><h1>{selected.title}</h1><span className={`order-status order-status-${selected.status}`}>{statusLabels[selected.status] ?? selected.status}</span></div><button className="secondary-button" onClick={()=>void loadDetails(selected)}><RefreshCw size={15}/>Обновить</button></section>
        <div className="portal-detail-grid"><section className="portal-panel"><h2>Сведения о заказе</h2><p className="portal-summary">{selected.client_visible_summary || 'Пока нет дополнительного описания для клиента.'}</p><div className="portal-data-row"><span><CalendarDays size={15}/>Целевой срок</span><strong>{formatDate(selected.target_delivery_date)}</strong></div><div className="portal-data-row"><span>Стоимость</span><strong>{selected.amount ? `${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(Number(selected.amount))} ${selected.currency}${selected.amount_type==='estimate'?' · оценка':''}`:'Уточняется'}</strong></div></section>
          <section className="portal-panel"><h2>История и этапы</h2>{events.length ? <ol className="portal-timeline">{events.map(item=><li key={item.id}><i/><div><strong>{item.to_status ? statusLabels[item.to_status] ?? item.to_status : 'Обновление заказа'}</strong>{item.message&&<p>{item.message}</p>}<time>{formatDateTime(item.created_at)}</time></div></li>)}</ol>:<div className="portal-empty">Обновления появятся здесь по мере движения заказа.</div>}</section>
        </div>
        <section className="portal-panel portal-messages"><div className="portal-section-title"><div><h2>Переписка по заказу</h2><p>Сообщения доступны вам и команде BOTVEX.</p></div><MessageCircle size={19}/></div>{messages.length ? <div className="portal-chat-list">{messages.map(message=><article className={`portal-chat-message ${message.author_username===user.username?'portal-chat-mine':''}`} key={message.id}><div><strong>{message.author_username===user.username?'Вы':message.author_username||'Команда BOTVEX'}</strong><time>{formatDateTime(message.created_at)}</time></div><p>{message.body}</p></article>)}</div>:<div className="portal-empty">Пока сообщений нет. Можно задать вопрос в форме ниже.</div>}
          <form className="portal-message-form" onSubmit={sendMessage}><label className="form-field"><span>Сообщение</span><textarea required maxLength={10000} rows={3} value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Напиши вопрос или уточнение…"/></label><button className="primary-button" disabled={sending||!draft.trim()}>{sending?'Отправка…':'Отправить сообщение'}</button></form>
        </section>
      </> : <>
        <section className="portal-welcome"><p className="auth-eyebrow">ЛИЧНЫЙ КАБИНЕТ</p><h1>Здравствуйте, {identity?.customer_name ?? user.username}</h1><p>Здесь находятся только заказы, привязанные к вашему аккаунту.</p></section>
        <div className="portal-list-heading"><h2>Мои заказы</h2><button className="secondary-button" onClick={()=>setRefreshCount(n=>n+1)}><RefreshCw size={15}/>Обновить</button></div>
        {busy ? <div className="auth-loading">Загрузка заказов…</div> : orders.length ? <div className="portal-order-list">{orders.map(order=><button className="portal-order-card" key={order.id} onClick={()=>void loadDetails(order)}><div><small>{order.order_number}</small><strong>{order.title}</strong><p>{order.client_visible_summary || 'Дополнительной информации пока нет.'}</p><span className={`order-status order-status-${order.status}`}>{statusLabels[order.status] ?? order.status}</span></div><ArrowLeft className="portal-order-arrow" size={17}/></button>)}</div> : <div className="portal-panel portal-empty-panel"><ShieldCheck size={25}/><h2>Заказов пока нет</h2><p>Когда в BOTVEX появится заказ, доступный вашему аккаунту, он отобразится здесь.</p></div>}
      </>}
      <footer className="portal-footer">Данные доступны согласно правам вашего аккаунта. Файловый обмен и внешние уведомления пока не подключены.</footer>
    </main>
  </div>;
}
