export function isAuthSessionExpired(status: number, payload: unknown): boolean {
  if (status === 401) return true;
  if (status !== 403 || !payload || typeof payload !== 'object') return false;
  const detail = (payload as Record<string, unknown>).detail;
  return detail === 'Authentication credentials were not provided.' || detail === 'Not authenticated.';
}
