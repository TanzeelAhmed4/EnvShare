const RESERVED_SUFFIXES = [
  '.localhost', '.local', '.internal', '.lan', '.home', '.test', '.invalid', '.example',
];

export function shouldValidateProductionApi(command: string, _mode: string): boolean {
  return command === 'build';
}

export function validateProductionApiUrl(value: string | undefined): string {
  if (!value?.trim()) throw new Error('VITE_API_BASE_URL is required for production builds.');
  let apiUrl: URL;
  try {
    apiUrl = new URL(value.trim());
  } catch {
    throw new Error('VITE_API_BASE_URL must be an absolute HTTPS URL ending in /api.');
  }
  const hostname = apiUrl.hostname.toLowerCase().replace(/^\[|\]$/g, '');
  let unsafeAddress = false;
  if (/^[0-9.]+$/.test(hostname) || hostname.includes(':')) {
    const octets = hostname.split('.').map(Number);
    unsafeAddress = hostname.includes(':') || octets.length !== 4 || octets.some((part) => part > 255);
    if (!unsafeAddress) {
      const [a, b] = octets;
      unsafeAddress = a === 0 || a === 10 || a === 127 || a >= 224
        || (a === 100 && b >= 64 && b <= 127)
        || (a === 169 && b === 254)
        || (a === 172 && b >= 16 && b <= 31)
        || (a === 192 && (b === 0 || b === 2 || b === 168))
        || (a === 198 && (b === 18 || b === 19 || (b === 51 && octets[2] === 100)))
        || (a === 203 && b === 0 && octets[2] === 113);
    }
  }
  const reservedName = !hostname.includes('.') || RESERVED_SUFFIXES.some((suffix) => hostname.endsWith(suffix));
  const allowedPath = /^\/(?:[A-Za-z0-9._~-]+\/)*api\/?$/.test(apiUrl.pathname);
  if (
    apiUrl.protocol !== 'https:' || apiUrl.username || apiUrl.password || apiUrl.search || apiUrl.hash
    || reservedName || unsafeAddress || !allowedPath
  ) {
    throw new Error('VITE_API_BASE_URL must be a public HTTPS API URL with no credentials, query, or fragment.');
  }
  return `${apiUrl.origin}${apiUrl.pathname.replace(/\/$/, '')}`;
}
