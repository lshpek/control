import {getTelegramInitData} from './telegram';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function decodeResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Ошибка запроса (${response.status})`;
    try {
      const body = await response.json();
      message = body?.error?.message || body?.detail || message;
    } catch {
      // The server returned an empty or non-JSON error response.
    }
    throw new ApiError(String(message), response.status);
  }
  return response.json() as Promise<T>;
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: options.credentials ?? 'include',
  });
  return decodeResponse<T>(response);
}

async function telegramLogin<T>(): Promise<T> {
  const initData = getTelegramInitData();
  if (!initData) throw new ApiError('Telegram initData недоступен в этом окне.', 401);
  const headers = new Headers({'X-Telegram-Init-Data': initData});
  return request<T>('/api/v1/auth/telegram', {method: 'POST', headers});
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, value?: unknown) => request<T>(path, {
    method: 'POST',
    ...(value === undefined ? {} : {body: JSON.stringify(value)}),
  }),
  patch: <T>(path: string, value: unknown) => request<T>(path, {method: 'PATCH', body: JSON.stringify(value)}),
  delete: <T>(path: string) => request<T>(path, {method: 'DELETE'}),
  telegramLogin,
};
