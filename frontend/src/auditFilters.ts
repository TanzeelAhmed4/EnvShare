export type AuditFilterValues = Record<string, string | number | '' | undefined>;

export function serializeAuditFilters(filters: AuditFilterValues = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : '';
}

export function auditDisplayState({ loading, error, variableCount, accessCount }: {
  loading: boolean; error: string; variableCount: number; accessCount: number;
}) {
  if (loading) return 'loading';
  if (error) return 'error';
  if (variableCount + accessCount === 0) return 'empty';
  return 'results';
}
