/** Locale-safe formatters for API dates. Date-only strings are calendar dates, not UTC instants. */
function parseDate(value: unknown): Date | null {
  if (value === null || value === undefined || value === '') return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value !== 'string' && typeof value !== 'number') return null;

  const raw = String(value).trim();
  if (!raw) return null;
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (dateOnly) {
    const year = Number(dateOnly[1]);
    const month = Number(dateOnly[2]);
    const day = Number(dateOnly[3]);
    const date = new Date(year, month - 1, day);
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
    return date;
  }

  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatDate(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Без срока';
  const date = parseDate(value);
  return date
    ? date.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' })
    : 'Некорректная дата';
}

export function formatDateTime(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  const date = parseDate(value);
  return date
    ? date.toLocaleString('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
    : 'Некорректная дата';
}

export function isOverdue(dueDate: unknown, status: unknown, now = new Date()): boolean {
  if (!dueDate || status === 'done') return false;
  const date = parseDate(dueDate);
  if (!date) return false;
  const key = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
  return key(date) < key(now);
}
