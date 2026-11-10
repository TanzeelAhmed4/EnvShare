export function invitationTokenFromHash(hash: string): string {
  const match = hash.match(/^#invite=(.+)$/);
  if (!match) return '';
  try { return decodeURIComponent(match[1]); } catch { return ''; }
}

export function clearInvitationFragment(
  history: Pick<History, 'replaceState'>,
  pathname: string,
  search: string,
): void {
  history.replaceState(null, '', `${pathname}${search}`);
}
