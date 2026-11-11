import { isAuthSessionExpired } from './authSession';
import { csrfTokenFromResponse } from './csrfToken';

export type AuthUser = {
  id: number;
  username: string;
  email: string;
};

type Credentials = {
  username: string;
  password: string;
  email?: string;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api').replace(/\/$/, '');
let sessionExpiredHandler: (() => void) | null = null;

export function onSessionExpired(handler: () => void): () => void {
  sessionExpiredHandler = handler;
  return () => {
    if (sessionExpiredHandler === handler) sessionExpiredHandler = null;
  };
}

async function csrfToken(): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/csrf/`, { credentials: 'include' });
  } catch {
    throw new Error('Cannot connect to EnvShare. Make sure the backend is running.');
  }
  return csrfTokenFromResponse(response);
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    headers.set('X-CSRFToken', await csrfToken());
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      method,
      headers,
      credentials: 'include',
    });
  } catch {
    throw new Error('Cannot connect to EnvShare. Make sure the backend is running.');
  }
  const payload: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  if (isAuthSessionExpired(response.status, payload)) sessionExpiredHandler?.();
  if (!response.ok) throw new Error(errorMessage(payload, response.status));
  return payload as T;
}

function errorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object') {
    const body = payload as Record<string, unknown>;
    if (typeof body.detail === 'string') return body.detail;
    for (const [field, value] of Object.entries(body)) {
      if (Array.isArray(value) && typeof value[0] === 'string') {
        const label = field === 'non_field_errors' ? '' : `${field[0].toUpperCase()}${field.slice(1)}: `;
        return `${label}${value[0]}`;
      }
    }
  }
  if (status === 0) return 'Cannot connect to EnvShare. Make sure the backend is running.';
  return 'Something went wrong. Please try again.';
}

export const authApi = {
  me: () => apiRequest<AuthUser>('/auth/me/'),
  register: (credentials: Credentials) => apiRequest<AuthUser>('/auth/register/', {
    method: 'POST',
    body: JSON.stringify(credentials),
  }),
  login: (credentials: Credentials) => apiRequest<AuthUser>('/auth/login/', {
    method: 'POST',
    body: JSON.stringify(credentials),
  }),
  logout: () => apiRequest<null>('/auth/logout/', { method: 'POST' }),
};
