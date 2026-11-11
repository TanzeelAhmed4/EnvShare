export async function csrfTokenFromResponse(response: { ok: boolean; json: () => Promise<unknown> }): Promise<string> {
  if (!response.ok) throw new Error('Could not start a secure session. Refresh and try again.');
  const payload: unknown = await response.json().catch(() => null);
  if (!payload || typeof payload !== 'object' || typeof (payload as { csrfToken?: unknown }).csrfToken !== 'string') {
    throw new Error('Could not start a secure session. Refresh and try again.');
  }
  return (payload as { csrfToken: string }).csrfToken;
}
