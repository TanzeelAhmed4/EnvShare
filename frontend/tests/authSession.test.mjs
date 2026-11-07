import assert from 'node:assert/strict';
import { isAuthSessionExpired } from '../src/authSession.ts';

assert.equal(isAuthSessionExpired(401, { detail: 'Unauthorized' }), true);
assert.equal(isAuthSessionExpired(403, { detail: 'Authentication credentials were not provided.' }), true);

assert.equal(isAuthSessionExpired(403, { detail: 'CSRF verification failed.' }), false);
assert.equal(isAuthSessionExpired(403, { detail: 'You do not have permission to perform this action.' }), false);
assert.equal(isAuthSessionExpired(404, { detail: 'Not found.' }), false);
process.stdout.write('Passed 5 auth session response assertions.\n');
