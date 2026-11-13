import { FormEvent, useEffect, useState } from 'react';
import { Eye, EyeOff, LoaderCircle, LockKeyhole } from 'lucide-react';
import { ApiError, authApi, AuthUser, onSessionExpired } from './authApi';
import ProjectWorkspace from './ProjectWorkspace';
import { projectsApi } from './projectsApi';
import { clearInvitationFragment, invitationTokenFromHash } from './invitationLink';

type AuthMode = 'login' | 'register';

export default function App() {
  const [mode, setMode] = useState<AuthMode>('login');
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [inviteToken, setInviteToken] = useState(() => invitationTokenFromHash(window.location.hash));

  useEffect(() => {
    if (inviteToken) clearInvitationFragment(window.history, window.location.pathname, window.location.search);
  }, [inviteToken]);

  useEffect(() => {
    const update = () => setInviteToken(invitationTokenFromHash(window.location.hash));
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);

  useEffect(() => {
    if (!user) return;
    return onSessionExpired(() => {
      setUser(null);
      setMode('login');
      setError('Your session expired. Sign in again to continue.');
    });
  }, [user]);

  useEffect(() => {
    let active = true;
    authApi.me()
      .then((currentUser) => { if (active) setUser(currentUser); })
      .catch((requestError) => {
        if (!active) return;
        setUser(null);
        if (!(requestError instanceof ApiError && [401, 403].includes(requestError.status))) {
          setError(requestError instanceof Error ? requestError.message : 'Could not check your session. Please try again.');
        }
      })
      .finally(() => { if (active) setLoadingSession(false); });
    return () => { active = false; };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setBusy(true);
    const form = new FormData(event.currentTarget);
    const username = String(form.get('username') ?? '').trim();
    const password = String(form.get('password') ?? '');
    try {
      const authenticated = mode === 'register'
        ? await authApi.register({ username, email: String(form.get('email') ?? '').trim(), password })
        : await authApi.login({ username, password });
      setUser(authenticated);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to sign in. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  const isRegister = mode === 'register';

  if (!loadingSession && user) {
    if (inviteToken) return <InvitationAcceptance token={inviteToken} onDone={() => setInviteToken('')} />;
    return <ProjectWorkspace user={user} onLogout={() => { setUser(null); setMode('login'); }} />;
  }

  return (
    <main className={`auth-shell auth-reference-shell ${isRegister ? 'register-mode' : 'login-mode'}`}>
      <section className="auth-layout" id="home">
        <div className="auth-illustration-pane"><img src={`/images/auth-${isRegister ? 'register' : 'login'}-illustration.png`} alt="A teammate working at a laptop" /></div>
        <section className="auth-card" aria-labelledby="auth-title">
          {loadingSession ? (
            <div className="auth-loading" role="status"><LoaderCircle className="spin" size={21} /> Checking your session…</div>
          ) : (
            <>
              {inviteToken && <p className="workspace-notice">Sign in or create an account with the email address invited to the project. The invitation will be checked after sign-in.</p>}
              <img className="auth-form-logo" src="/images/envshare-exact-logo.svg" alt="EnvShare" />
              <h1 id="auth-title">{isRegister ? 'Create Account' : 'Sign In'}</h1>
              <p className="auth-subtitle">{isRegister ? 'Get started with EnvShare' : 'Access your EnvShare account'}</p>

              <form className="auth-form" onSubmit={handleSubmit}>
                {isRegister && <>
                  <label htmlFor="username">Username</label>
                  <input id="username" name="username" type="text" autoComplete="username" required minLength={1} maxLength={150} placeholder="Choose a username" />
                  <label htmlFor="email">Email address</label>
                  <input id="email" name="email" type="email" autoComplete="email" required placeholder="you@example.com" />
                </>}

                {!isRegister && <><label htmlFor="username">Username</label><input id="username" name="username" type="text" autoComplete="username" required minLength={1} maxLength={150} placeholder="Enter your username" /></>}

                <div className="password-label"><label htmlFor="password">Password</label>{isRegister && <span>At least 8 characters</span>}</div>
                <div className="password-field">
                  <input id="password" name="password" type={showPassword ? 'text' : 'password'} autoComplete={isRegister ? 'new-password' : 'current-password'} required minLength={isRegister ? 8 : undefined} placeholder={isRegister ? 'Create a strong password' : 'Enter your password'} />
                  <button className="password-toggle" type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button>
                </div>

                {error && <p className="form-error" role="alert">{error}</p>}
                <button className="auth-submit" type="submit" disabled={busy}>
                  {busy ? <><LoaderCircle className="spin" size={17} /> Please wait…</> : isRegister ? 'Sign Up' : 'Sign In'}
                </button>
              </form>
              <p className="auth-switch-prompt">{isRegister ? 'Already have an account?' : 'New to EnvShare?'} <button type="button" onClick={() => { setMode(isRegister ? 'login' : 'register'); setError(''); }}>{isRegister ? 'Sign in' : 'Create account'}</button></p>
              <p className="auth-privacy-note"><LockKeyhole size={13} /> Your account is protected with secure sign-in.</p>
            </>
          )}
        </section>
      </section>
    </main>
  );
}

function InvitationAcceptance({ token, onDone }: { token: string; onDone: () => void }) {
  const [details, setDetails] = useState<{ project_name: string; role: string; expires_at: string; uses_remaining: number } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    projectsApi.inspectInvitation(token).then(setDetails).catch((cause) => setError(cause instanceof Error ? cause.message : 'Invitation is unavailable.'));
  }, [token]);
  async function accept() {
    setBusy(true); setError('');
    try { await projectsApi.acceptInvitation(token); onDone(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not accept this invitation.'); }
    finally { setBusy(false); }
  }
  return <main className="auth-shell min-h-screen invitation-shell"><a className="invitation-brand" href="#home" aria-label="EnvShare home"><img src="/images/envshare-exact-logo.svg" alt="EnvShare" /></a><section className="auth-card" aria-labelledby="invite-title"><span className="form-eyebrow">PROJECT INVITATION</span><h2 id="invite-title">Join a project</h2>{details ? <><p className="auth-subtitle">You were invited to <strong>{details.project_name}</strong> as <strong>{details.role}</strong>.</p><p className="auth-subtitle">Expires {new Date(details.expires_at).toLocaleString()} · {details.uses_remaining} use(s) remaining</p><button className="auth-submit" onClick={() => void accept()} disabled={busy}>{busy ? 'Accepting…' : 'Accept invitation'}</button></> : <p className="auth-subtitle">{error || 'Checking invitation…'}</p>}{error && <p className="form-error" role="alert">{error}</p>}<button className="workspace-secondary" onClick={onDone}>Back to workspace</button></section></main>;
}
