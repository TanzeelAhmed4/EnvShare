import assert from 'node:assert/strict';
import { isAuthSessionExpired } from '../src/authSession.ts';
import { clearInvitationFragment, invitationTokenFromHash } from '../src/invitationLink.ts';
import { auditDisplayState, serializeAuditFilters } from '../src/auditFilters.ts';
import { csrfTokenFromResponse } from '../src/csrfToken.ts';
import { shouldValidateProductionApi, validateProductionApiUrl } from '../src/productionApiConfig.ts';

assert.equal(isAuthSessionExpired(401, { detail: 'Unauthorized' }), true);
assert.equal(isAuthSessionExpired(403, { detail: 'Authentication credentials were not provided.' }), true);

assert.equal(isAuthSessionExpired(403, { detail: 'CSRF verification failed.' }), false);
assert.equal(isAuthSessionExpired(403, { detail: 'You do not have permission to perform this action.' }), false);
assert.equal(isAuthSessionExpired(404, { detail: 'Not found.' }), false);
assert.equal(invitationTokenFromHash('#invite=token%2Fvalue'), 'token/value');
assert.equal(invitationTokenFromHash('#home'), '');
let replacedUrl = '';
clearInvitationFragment({ replaceState: (_state, _title, url) => { replacedUrl = url; } }, '/workspace', '?tab=projects');
assert.equal(replacedUrl, '/workspace?tab=projects');
assert.equal(serializeAuditFilters({ search: 'deploy key', action: 'updated', page: 2, actor: '' }), '?search=deploy+key&action=updated&page=2');
assert.equal(auditDisplayState({ loading: true, error: '', variableCount: 0, accessCount: 0 }), 'loading');
assert.equal(auditDisplayState({ loading: false, error: 'Network error', variableCount: 0, accessCount: 0 }), 'error');
assert.equal(auditDisplayState({ loading: false, error: '', variableCount: 0, accessCount: 0 }), 'empty');
assert.equal(auditDisplayState({ loading: false, error: '', variableCount: 1, accessCount: 0 }), 'results');
assert.equal(await csrfTokenFromResponse({ ok: true, json: async () => ({ csrfToken: 'masked-csrf-token' }) }), 'masked-csrf-token');
await assert.rejects(() => csrfTokenFromResponse({ ok: false, json: async () => ({}) }));
await assert.rejects(() => csrfTokenFromResponse({ ok: true, json: async () => ({}) }));
assert.equal(validateProductionApiUrl('https://api.envshare.com/api/'), 'https://api.envshare.com/api');
assert.equal(validateProductionApiUrl('https://8.8.8.8/api'), 'https://8.8.8.8/api');
for (const invalidUrl of [
  'http://api.envshare.com/api', 'http://localhost:8000/api', 'https://localhost/api',
  'https://127.0.0.1/api', 'https://10.1.2.3/api', 'https://172.16.0.1/api',
  'https://192.168.1.5/api', 'https://169.254.1.2/api', 'https://203.0.113.4/api',
  'https://api.envshare.local/api',
  'https://user:pass@api.envshare.com/api', 'https://api.envshare.com/api?mode=test',
  'https://api.envshare.com/api#fragment', 'https://api.envshare.com/not-api',
]) assert.throws(() => validateProductionApiUrl(invalidUrl));
assert.throws(() => validateProductionApiUrl(undefined));
assert.equal(shouldValidateProductionApi('build', 'development'), true);
assert.equal(shouldValidateProductionApi('serve', 'production'), false);
process.stdout.write('Frontend auth, invitation-link, CSRF, API-config, and audit-filter assertions passed.\n');
