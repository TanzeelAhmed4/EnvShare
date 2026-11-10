import { FormEvent, useEffect, useState } from 'react';
import { ArrowRight, Command, Eye, EyeOff, KeyRound, LoaderCircle, ShieldCheck } from 'lucide-react';
import { authApi, AuthUser, onSessionExpired } from './authApi';
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
      .catch(() => { if (active) setUser(null); })
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
    <main className="auth-shell min-h-screen">
      <header className="auth-topbar">
        <a className="auth-brand" href="#home" aria-label="EnvShare home">
          <span className="auth-brand-mark"><Command size={18} strokeWidth={2.5} /></span>
          <span>env<span>share</span></span>
        </a>
        <span className="secure-byline"><ShieldCheck size={15} /> Private by design</span>
      </header>

      <section className="auth-layout" id="home">
        <div className="auth-story">
          <div className="auth-eyebrow"><span /> TEAM ENVIRONMENTS, IN ONE PLACE</div>
          <h1>Make configuration feel <span>less complicated.</span></h1>
          <p>Bring your project settings together and keep your team working from the same source of truth.</p>
          <div className="story-rule" />
          <div className="story-points">
            <div><span className="story-icon"><Command size={17} /></span><span><strong>Projects with clear ownership</strong><small>Create a project and choose which registered teammates can access it.</small></span></div>
            <div><span className="story-icon"><KeyRound size={17} /></span><span><strong>Careful account security</strong><small>Argon2id password hashing and CSRF-protected account actions.</small></span></div>
          </div>
          <div className="story-footer"><span className="tiny-shield"><ShieldCheck size={14} /></span> Your workspace is only for you and your team.</div>
        </div>

        <section className="auth-card" aria-labelledby="auth-title">
          {loadingSession ? (
            <div className="auth-loading" role="status"><LoaderCircle className="spin" size={21} /> Checking your session…</div>
          ) : (
            <>
              {inviteToken && <p className="workspace-notice">Sign in or create an account with the email address invited to the project. The invitation will be checked after sign-in.</p>}
              <span className="form-eyebrow">{isRegister ? 'GET STARTED' : 'WELCOME BACK'}</span>
              <h2 id="auth-title">{isRegister ? 'Create your account' : 'Sign in to EnvShare'}</h2>
              <p className="auth-subtitle">{isRegister ? 'Set up your account to get your team in sync.' : 'Pick up where your team left off.'}</p>

              <div className="auth-tabs" role="tablist" aria-label="Authentication options">
                <button className={!isRegister ? 'active' : ''} role="tab" aria-selected={!isRegister} onClick={() => { setMode('login'); setError(''); }}>Sign in</button>
                <button className={isRegister ? 'active' : ''} role="tab" aria-selected={isRegister} onClick={() => { setMode('register'); setError(''); }}>Create account</button>
              </div>

              <form className="auth-form" onSubmit={handleSubmit} noValidate>
                <label htmlFor="username">Username</label>
                <input id="username" name="username" type="text" autoComplete="username" required minLength={1} maxLength={150} placeholder="Choose a username" />

                {isRegister && <>
                  <label htmlFor="email">Email address</label>
                  <input id="email" name="email" type="email" autoComplete="email" required placeholder="you@example.com" />
                </>}

                <div className="password-label"><label htmlFor="password">Password</label>{isRegister && <span>At least 8 characters</span>}</div>
                <div className="password-field">
                  <input id="password" name="password" type={showPassword ? 'text' : 'password'} autoComplete={isRegister ? 'new-password' : 'current-password'} required minLength={isRegister ? 8 : undefined} placeholder={isRegister ? 'Create a strong password' : 'Enter your password'} />
                  <button className="password-toggle" type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button>
                </div>

                {error && <p className="form-error" role="alert">{error}</p>}
                <button className="auth-submit" type="submit" disabled={busy}>
                  {busy ? <><LoaderCircle className="spin" size={17} /> Please wait…</> : <>{isRegister ? 'Create account' : 'Sign in'} <ArrowRight size={17} /></>}
                </button>
              </form>
              <p className="form-legal">By continuing, you agree to use EnvShare responsibly and keep your credentials private.</p>
            </>
          )}
        </section>
      </section>

      <footer className="auth-footer"><span>ENVSHARE <i>/</i> TEAM ENVIRONMENT MANAGER</span><span>Local workspace <b /></span></footer>
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
  return <main className="auth-shell min-h-screen"><section className="auth-card" aria-labelledby="invite-title"><span className="form-eyebrow">PROJECT INVITATION</span><h2 id="invite-title">Join a project</h2>{details ? <><p className="auth-subtitle">You were invited to <strong>{details.project_name}</strong> as <strong>{details.role}</strong>.</p><p className="auth-subtitle">Expires {new Date(details.expires_at).toLocaleString()} · {details.uses_remaining} use(s) remaining</p><button className="auth-submit" onClick={() => void accept()} disabled={busy}>{busy ? 'Accepting…' : 'Accept invitation'}</button></> : <p className="auth-subtitle">{error || 'Checking invitation…'}</p>}{error && <p className="form-error" role="alert">{error}</p>}<button className="workspace-secondary" onClick={onDone}>Back to workspace</button></section></main>;
}
