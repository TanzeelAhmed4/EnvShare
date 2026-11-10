import assert from 'node:assert/strict';
import { isAuthSessionExpired } from '../src/authSession.ts';
import { clearInvitationFragment, invitationTokenFromHash } from '../src/invitationLink.ts';

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
process.stdout.write('Passed 8 auth session and invitation-link assertions.\n');
