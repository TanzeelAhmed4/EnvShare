import { FormEvent, useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, ChartNoAxesColumnIncreasing, CirclePlus, FileClock, FileUp, FolderKanban, History, LayoutDashboard, LoaderCircle, LogOut, Search, Settings, ShieldCheck, UserPlus, Users, UserRound, X } from 'lucide-react';
import { AuthUser, authApi } from './authApi';
import EnvironmentVariables from './EnvironmentVariables';
import AuditTimeline from './AuditTimeline';
import { Environment, Project, ProjectInvitation, ProjectMember, projectsApi } from './projectsApi';
import VersionHistoryPage from './VersionHistoryPage';
import { useModalAccessibility } from './useModalAccessibility';

type Props = { user: AuthUser; onLogout: () => void };
type WorkspacePage = 'dashboard' | 'users' | 'projects' | 'teams' | 'audit' | 'settings' | 'profile' | 'environments' | 'variables' | 'history' | 'import-export' | 'project';
type ProjectPage = 'overview' | 'environments' | 'variables' | 'history' | 'import-export' | 'audit' | 'teams';

export default function ProjectWorkspace({ user, onLogout }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [invitations, setInvitations] = useState<ProjectInvitation[]>([]);
  const [memberRole, setMemberRole] = useState<ProjectMember['role']>('member');
  const [inviteLink, setInviteLink] = useState('');
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [activeEnvironmentId, setActiveEnvironmentId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const createDialogRef = useModalAccessibility<HTMLElement>(showCreate, () => setShowCreate(false));
  const [memberUsername, setMemberUsername] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [auditRefresh, setAuditRefresh] = useState(0);
  const [workspacePage, setWorkspacePage] = useState<WorkspacePage>('dashboard');
  const [projectPage, setProjectPage] = useState<ProjectPage>('overview');
  const [search, setSearch] = useState('');
  const [environmentCounts, setEnvironmentCounts] = useState<Record<string, number> | null>(null);
  const [metricsRefresh, setMetricsRefresh] = useState(0);

  async function loadProjects() {
    setError('');
    try {
      setProjects(await projectsApi.list());
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not load your projects.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadProjects(); }, []);

  useEffect(() => {
    let active = true;
    if (loading || projects.length === 0) { setEnvironmentCounts(projects.length === 0 ? {} : null); return () => { active = false; }; }
    Promise.all(projects.map(async (project) => {
      const projectEnvironments = await projectsApi.environments(project.id);
      return Promise.all(projectEnvironments.map(async (environment) => ({
        name: environment.name,
        count: (await projectsApi.variables(project.id, environment.id)).length,
      })));
    })).then((result) => {
      if (active) setEnvironmentCounts(result.flat().reduce<Record<string, number>>((counts, item) => {
        counts[item.name] = (counts[item.name] ?? 0) + item.count;
        return counts;
      }, {}));
    }).catch(() => { if (active) setEnvironmentCounts(null); });
    return () => { active = false; };
  }, [projects, loading, metricsRefresh]);

  async function signOut() {
    setSigningOut(true);
    setError('');
    try {
      await authApi.logout();
      onLogout();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not sign out.');
    } finally {
      setSigningOut(false);
    }
  }

  async function openProject(project: Project, target: ProjectPage = 'overview') {
    setError('');
    setNotice('');
    setMembers([]);
    try {
      const detail = await projectsApi.get(project.id);
      setActiveProject(detail);
      setWorkspacePage('project');
      setProjectPage(target);
      const projectEnvironments = await projectsApi.environments(detail.id);
      setEnvironments(projectEnvironments);
      setActiveEnvironmentId(projectEnvironments[0]?.id ?? null);
      if (detail.my_role === 'owner' || detail.my_role === 'admin') {
        const [projectMembers, projectInvitations] = await Promise.all([projectsApi.members(detail.id), projectsApi.invitations(detail.id)]);
        setMembers(projectMembers); setInvitations(projectInvitations);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not open this project.');
      setActiveProject(null);
    }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setNotice('');
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const project = await projectsApi.create({
        name: String(form.get('name') ?? '').trim(),
        description: String(form.get('description') ?? '').trim(),
      });
      setProjects((current) => [project, ...current]);
      setShowCreate(false);
      formElement.reset();
      await openProject(project);
      setNotice('Project created. You can add registered teammates below.');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not create the project.');
    } finally {
      setBusy(false);
    }
  }

  async function addMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeProject) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const member = await projectsApi.addMember(activeProject.id, memberUsername.trim(), memberRole);
      setMembers((current) => [...current, member]);
      setMemberUsername('');
      setNotice(`${member.username} was added to the project.`);
      await loadProjects();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not add that member.');
    } finally {
      setBusy(false);
    }
  }

  async function removeMember(member: ProjectMember) {
    if (!activeProject) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await projectsApi.removeMember(activeProject.id, member.user_id);
      setMembers((current) => current.filter((item) => item.user_id !== member.user_id));
      setNotice(`${member.username} was removed from the project.`);
      await loadProjects();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not remove that member.');
    } finally {
      setBusy(false);
    }
  }

  const canManageTeam = activeProject?.my_role === 'owner' || activeProject?.my_role === 'admin';
  const assignableRoles: ProjectMember['role'][] = activeProject?.my_role === 'owner' ? ['admin', 'manager', 'member'] : ['manager', 'member'];

  async function createInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!activeProject) return;
    const formElement = event.currentTarget; const form = new FormData(formElement);
    try {
      const invitation = await projectsApi.createInvitation(activeProject.id, {
        email: String(form.get('email') ?? ''), role: String(form.get('role')) as ProjectMember['role'],
        expires_in_hours: Number(form.get('expires')), max_uses: 1,
      });
      const link = `${window.location.origin}${window.location.pathname}#invite=${encodeURIComponent(invitation.token ?? '')}`;
      setInviteLink(link); await navigator.clipboard?.writeText(link).catch(() => undefined);
      setInvitations((current) => [{ ...invitation, use_count: 0, revoked: false, expired: false }, ...current]);
      formElement.reset(); setNotice('Invitation created. The link is shown below and copied when clipboard access is available.');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create invitation.'); }
  }

  async function revokeInvitation(invitation: ProjectInvitation) {
    if (!activeProject) return;
    try { await projectsApi.revokeInvitation(activeProject.id, invitation.id); setInvitations((items) => items.map((item) => item.id === invitation.id ? { ...item, revoked: true } : item)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not revoke invitation.'); }
  }

  async function changeRole(member: ProjectMember, role: ProjectMember['role']) {
    if (!activeProject) return;
    try { const updated = await projectsApi.updateMemberRole(activeProject.id, member.user_id, role); setMembers((items) => items.map((item) => item.user_id === updated.user_id ? updated : item)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update role.'); }
  }

  function navigate(page: WorkspacePage) {
    if (page !== 'project') setActiveProject(null);
    setWorkspacePage(page);
    const projectTab: Partial<Record<WorkspacePage, ProjectPage>> = {
      teams: 'teams', audit: 'audit', environments: 'environments', variables: 'variables', history: 'history', 'import-export': 'import-export',
    };
    if (projectTab[page]) setProjectPage(projectTab[page]!);
    setError(''); setNotice('');
  }

  function refreshProjectData() {
    setAuditRefresh((version) => version + 1);
    setMetricsRefresh((version) => version + 1);
  }

  const visibleProjects = projects.filter((project) => `${project.name} ${project.description}`.toLowerCase().includes(search.toLowerCase()));
  const pageTitle: Record<WorkspacePage, string> = {
    dashboard: 'Dashboard', users: 'Users', projects: 'Projects', teams: 'Teams', audit: 'Audit Logs', settings: 'System Settings', profile: 'My Profile', environments: 'Environments', variables: 'Environment Variables', history: 'Version History', 'import-export': 'Import / Export', project: activeProject?.name ?? 'Project Details',
  };

  return (
    <div className="workspace-app">
      <aside className="workspace-sidebar">
        <a className="workspace-sidebar-brand" href="#dashboard" onClick={(event) => { event.preventDefault(); navigate('dashboard'); }} aria-label="EnvShare dashboard"><img src="/images/envshare-exact-logo.svg" alt="EnvShare" /><span>Team workspace</span></a>
        <span className="workspace-sidebar-caption">WORKSPACE</span>
        <nav className="workspace-navigation" aria-label="Main navigation">
          <NavButton active={workspacePage === 'dashboard'} icon={<LayoutDashboard size={17} />} label="Dashboard" onClick={() => navigate('dashboard')} />
          <NavButton active={workspacePage === 'users'} icon={<UserRound size={17} />} label="Users" onClick={() => navigate('users')} />
          <NavButton active={workspacePage === 'projects' || workspacePage === 'project'} icon={<FolderKanban size={17} />} label="Projects" onClick={() => navigate('projects')} />
          <NavButton active={workspacePage === 'teams'} icon={<Users size={17} />} label="Teams" onClick={() => navigate('teams')} />
          <NavButton active={workspacePage === 'audit'} icon={<FileClock size={17} />} label="Audit Logs" onClick={() => navigate('audit')} />
          <NavButton active={workspacePage === 'settings'} icon={<Settings size={17} />} label="System Settings" onClick={() => navigate('settings')} />
        </nav>
        <span className="workspace-sidebar-caption project-tools-caption">PROJECT TOOLS</span>
        <nav className="workspace-navigation" aria-label="Project tools">
          <NavButton active={workspacePage === 'environments'} icon={<ChartNoAxesColumnIncreasing size={17} />} label="Environments" onClick={() => navigate('environments')} />
          <NavButton active={workspacePage === 'variables'} icon={<ShieldCheck size={17} />} label="Variables" onClick={() => navigate('variables')} />
          <NavButton active={workspacePage === 'history'} icon={<History size={17} />} label="Version History" onClick={() => navigate('history')} />
          <NavButton active={workspacePage === 'import-export'} icon={<FileUp size={17} />} label="Import / Export" onClick={() => navigate('import-export')} />
        </nav>
        <button className="workspace-sidebar-profile" onClick={() => navigate('profile')}><span className="account-avatar">{user.username.slice(0, 1).toUpperCase()}</span><span><strong>{user.username}</strong><small>{user.email}</small></span><UserRound size={16} /></button>
      </aside>

      <main className="workspace-shell">
        <header className="workspace-topbar">
          <div className="workspace-topbar-title"><span>ENVSHARE <i>/</i> WORKSPACE</span><h1>{pageTitle[workspacePage]}</h1></div>
          <div className="workspace-topbar-actions"><label className="workspace-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={workspacePage === 'users' ? 'Search users or projects…' : 'Search projects…'} aria-label={workspacePage === 'users' ? 'Search users and projects' : 'Search projects'} /></label><span className="workspace-header-avatar" aria-hidden="true">{user.username.slice(0, 1).toUpperCase()}</span><button onClick={() => void signOut()} className="signout-button" aria-label="Sign out" disabled={signingOut}><LogOut size={16} /><span>{signingOut ? 'Signing out…' : 'Sign out'}</span></button></div>
        </header>

        <div className="workspace-content" id="projects">
          {error && <p className="workspace-alert" role="alert">{error}</p>}
          {notice && <p className="workspace-notice" role="status">{notice}</p>}
          {(workspacePage === 'dashboard' || workspacePage === 'projects') && <>
            {workspacePage === 'dashboard' && <DashboardCards projects={projects} environmentCounts={environmentCounts} loading={loading} />}
            <div className="workspace-heading"><div><div className="auth-eyebrow"><span /> YOUR WORKSPACE</div><h2>{workspacePage === 'dashboard' ? 'Recent projects' : 'Projects'}</h2><p>Only projects you created or joined appear here.</p></div><button className="workspace-primary" onClick={() => { setShowCreate(true); setError(''); }}><CirclePlus size={17} /> New project</button></div>
            <section className="project-section" aria-label="Your projects">
              {loading ? <div className="workspace-loading" role="status"><LoaderCircle className="spin" size={19} /> Loading projects…</div> : visibleProjects.length === 0 ? <div className="projects-empty"><span className="empty-folder"><FolderKanban size={23} /></span><h3>{projects.length ? 'No matching projects' : 'Start with a project'}</h3><p>{projects.length ? 'Try another project name.' : 'Create a project, then add registered teammates who need access.'}</p>{!projects.length && <button className="workspace-primary" onClick={() => setShowCreate(true)}><CirclePlus size={16} /> Create a project</button>}</div> : <div className="project-grid">{visibleProjects.map((project) => <article className="project-card" key={project.id}>
                <div className="project-card-top"><span className="project-card-icon"><FolderKanban size={18} /></span><span className={`role-pill ${project.my_role}`}>{project.my_role}</span></div><h3>{project.name}</h3><p>{project.description || 'No description added.'}</p>
                <div className="project-card-meta"><span><Users size={14} /> {project.member_count} {project.member_count === 1 ? 'member' : 'members'}</span><span>Updated {new Date(project.updated_at).toLocaleDateString()}</span></div><button className="project-open" onClick={() => void openProject(project)}>Open project <ArrowRight size={15} /></button>
              </article>)}</div>}
            </section>
          </>}

          {workspacePage === 'project' && activeProject && <>
            <div className="workspace-heading project-page-heading"><div><div className="auth-eyebrow"><span /> PROJECT WORKSPACE</div><h2>{activeProject.name}</h2><p>{activeProject.description || 'Project overview and management.'}</p></div><button className="workspace-secondary" onClick={() => { setActiveProject(null); setWorkspacePage('projects'); setEnvironments([]); setActiveEnvironmentId(null); setError(''); setNotice(''); }}><ArrowLeft size={16} /> All projects</button></div>
            <nav className="project-page-tabs" aria-label="Project pages">{([['overview', 'Overview'], ['environments', 'Environments'], ['variables', 'Variables'], ['teams', 'Team Members'], ['audit', 'Audit Logs'], ['history', 'Version History'], ['import-export', 'Import / Export']] as [ProjectPage, string][]).map(([key, label]) => <button key={key} aria-current={projectPage === key ? 'page' : undefined} className={projectPage === key ? 'active' : ''} onClick={() => setProjectPage(key)}>{label}</button>)}</nav>
            {projectPage === 'overview' && <section className="project-detail-grid"><article className="detail-card project-overview"><div className="detail-card-heading"><span className="detail-icon"><FolderKanban size={18} /></span><span className={`role-pill ${activeProject.my_role}`}>{activeProject.my_role}</span></div><span className="detail-label">PROJECT DETAILS</span><h2>{activeProject.name}</h2><p>{activeProject.description || 'This project does not have a description yet.'}</p><div className="detail-meta"><span>Created by <strong>{activeProject.creator_username}</strong></span><span>Created {new Date(activeProject.created_at).toLocaleDateString()}</span></div><div className="phase-callout"><ShieldCheck size={16} /><span><strong>Project access is ready</strong><small>Environment variables are scoped to this project's members.</small></span></div></article><article className="detail-card project-overview"><span className="detail-label">PROJECT SNAPSHOT</span><h2>Environment setup</h2><p>This project has {environments.length} environments. Variable totals are shown after selecting an environment.</p><div className="detail-meta"><span>{activeProject.member_count} project members</span><span>Updated {new Date(activeProject.updated_at).toLocaleDateString()}</span></div><button className="workspace-primary" onClick={() => setProjectPage('environments')}>View environments <ArrowRight size={15} /></button></article></section>}

            {projectPage === 'teams' && <section className="project-detail-grid"><article className="detail-card team-card"><div className="team-heading"><div><span className="detail-label">ACCESS CONTROL</span><h2>Team members</h2></div><span className="member-count">{members.length}</span></div><p className="team-description">Admins and owners manage access. Managers can edit project data; members have read-only access.</p>{canManageTeam && <form className="member-add-form" onSubmit={addMember}><label htmlFor="member-username">Add a registered user</label><div className="member-input-row"><input id="member-username" value={memberUsername} onChange={(event) => setMemberUsername(event.target.value)} placeholder="Enter their username" required maxLength={150} /><select aria-label="New member role" value={memberRole} onChange={(event) => setMemberRole(event.target.value as ProjectMember['role'])}>{assignableRoles.map((role) => <option key={role} value={role}>{role}</option>)}</select><button type="submit" disabled={busy || !memberUsername.trim()} aria-label="Add project member"><UserPlus size={16} /> Add</button></div></form>}{!canManageTeam && <p className="workspace-notice">Your project role is {activeProject.my_role}. Only project owners and admins can manage membership.</p>}<div className="member-list" aria-label="Project members">{members.length === 0 ? <div className="member-empty">Member details are available to project owners and admins.</div> : members.map((member) => <div className="member-row" key={member.user_id}><span className="member-avatar">{member.username.slice(0, 1).toUpperCase()}</span><span className="member-info"><strong>{member.username}</strong><small>{member.email}</small></span>{canManageTeam ? <><select aria-label={`${member.username} role`} value={member.role} onChange={(event) => void changeRole(member, event.target.value as ProjectMember['role'])}>{[...new Set([...assignableRoles, member.role])].map((role) => <option key={role} value={role}>{role}</option>)}</select><button className="remove-member" onClick={() => void removeMember(member)} disabled={busy} aria-label={`Remove ${member.username}`} title={`Remove ${member.username}`}><X size={16} /></button></> : <span className="member-role">{member.role}</span>}</div>)}</div></article>
              {canManageTeam && <article className="detail-card team-card"><div className="team-heading"><div><span className="detail-label">INVITATIONS</span><h2>Invite by email</h2></div></div><form className="member-add-form" onSubmit={createInvitation}><div className="member-input-row"><input name="email" type="email" placeholder="teammate@example.com" required /><select name="role" defaultValue="member">{assignableRoles.map((role) => <option key={role} value={role}>{role}</option>)}</select><input name="expires" type="number" min="1" max="720" defaultValue="168" aria-label="Expires in hours" /><button type="submit">Create invitation</button></div></form>{inviteLink && <p className="workspace-notice">Invitation link (copied when clipboard access is available): <code>{inviteLink}</code></p>}<div className="member-list" aria-label="Project invitations">{invitations.map((invite) => <div className="member-row" key={invite.id}><span className="member-info"><strong>{invite.email}</strong><small>{invite.role} · expires {new Date(invite.expires_at).toLocaleString()} · {invite.use_count ?? 0}/{invite.max_uses} uses</small></span><span className="member-role">{invite.revoked ? 'Revoked' : invite.expired ? 'Expired' : invite.exhausted ? 'Used' : 'Pending'}</span>{!invite.revoked && !invite.expired && !invite.exhausted && <button className="remove-member" onClick={() => void revokeInvitation(invite)}>Revoke</button>}</div>)}</div></article>}</section>}

            {projectPage === 'environments' && <section className="environment-page-grid" aria-label="Project environments">{environments.map((environment) => <button key={environment.id} className={`environment-page-card ${environment.name}`} onClick={() => { setActiveEnvironmentId(environment.id); setProjectPage('variables'); }}><span className="environment-tab-dot" /><strong>{environment.label}</strong><small>Open environment variables</small><ArrowRight size={16} /></button>)}</section>}
            {(projectPage === 'variables' || projectPage === 'import-export') && <EnvironmentVariables projectId={activeProject.id} canManageHistory={activeProject.my_role !== 'member'} canWriteVariables={activeProject.my_role !== 'member'} onAuditChange={refreshProjectData} environments={environments} selectedEnvironmentId={activeEnvironmentId} onSelectEnvironment={setActiveEnvironmentId} />}
            {projectPage === 'history' && <VersionHistoryPage projectId={activeProject.id} environmentId={activeEnvironmentId} canManageHistory={activeProject.my_role !== 'member'} onAuditChange={refreshProjectData} />}
            {projectPage === 'audit' && <AuditTimeline projectId={activeProject.id} refreshToken={auditRefresh} />}
          </>}

          {workspacePage === 'users' && <ManagedUsersPage projects={projects} search={search} onManage={(project) => void openProject(project, 'teams')} />}
          {workspacePage === 'teams' && !activeProject && <UnavailablePage title="Choose a project team" icon={<Users size={20} />} copy="Team members and invitations are managed within each project. Choose a project to view its access list." projects={visibleProjects} loading={loading} onOpen={(project) => void openProject(project, 'teams')} />}
          {workspacePage === 'audit' && !activeProject && <UnavailablePage title="Choose a project audit log" icon={<FileClock size={20} />} copy="Audit history is scoped to a project and follows your existing project permissions." projects={visibleProjects} loading={loading} onOpen={(project) => void openProject(project, 'audit')} />}
          {workspacePage === 'environments' && !activeProject && <UnavailablePage title="Choose a project" icon={<ChartNoAxesColumnIncreasing size={20} />} copy="Each project's Development, Staging and Production environments are available to its members." projects={visibleProjects} loading={loading} onOpen={(project) => void openProject(project, 'environments')} />}
          {workspacePage === 'variables' && !activeProject && <UnavailablePage title="Choose a project" icon={<ShieldCheck size={20} />} copy="Select a project to manage its environment variables with your current role permissions." projects={visibleProjects} loading={loading} onOpen={(project) => void openProject(project, 'variables')} />}
          {workspacePage === 'history' && !activeProject && <UnavailablePage title="Choose a project" icon={<History size={20} />} copy="Variable history is available within each project environment." projects={visibleProjects} loading={loading} onOpen={(project) => void openProject(project, 'history')} />}
          {workspacePage === 'import-export' && !activeProject && <UnavailablePage title="Choose a project" icon={<FileUp size={20} />} copy="Import and export are available for an individual project environment." projects={visibleProjects} loading={loading} onOpen={(project) => void openProject(project, 'import-export')} />}
          {workspacePage === 'settings' && <SystemSettingsPage />}
          {workspacePage === 'profile' && <section className="profile-page-card"><div className="profile-identity"><div className="profile-avatar-large">{user.username.slice(0, 1).toUpperCase()}</div><strong>{user.username}</strong><span>{user.email || 'No email address on file'}</span></div><form className="profile-form" onSubmit={(event) => event.preventDefault()}><label>Username<input value={user.username} readOnly /></label><label>Email<input value={user.email} readOnly /></label><label>Project role<input value="Assigned separately in each project" readOnly /></label><div className="profile-readonly-note">Profile editing is not available through the current account API.</div><button className="workspace-primary" type="button" disabled>Update Profile</button></form></section>}
        </div>

        <footer className="workspace-footer"><span>ENVSHARE <i>/</i> TEAM WORKSPACE</span><span><ShieldCheck size={14} /> Project membership controls access</span></footer>

      {showCreate && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowCreate(false); }}><section ref={createDialogRef} tabIndex={-1} className="project-modal" role="dialog" aria-modal="true" aria-labelledby="create-project-title"><button className="modal-close" onClick={() => setShowCreate(false)} aria-label="Close project form"><X size={18} /></button><span className="form-eyebrow">NEW WORKSPACE</span><h2 id="create-project-title">Create a project</h2><p className="modal-copy">Start a shared space for one of your team's projects.</p><form className="project-form" onSubmit={createProject}><label htmlFor="project-name">Project name</label><input id="project-name" name="name" placeholder="e.g. Payments API" maxLength={120} required autoFocus /><label htmlFor="project-description">Description <span>Optional</span></label><textarea id="project-description" name="description" placeholder="What is this project for?" rows={3} /><div className="modal-actions"><button className="workspace-secondary" type="button" onClick={() => setShowCreate(false)}>Cancel</button><button className="workspace-primary" type="submit" disabled={busy}>{busy ? <><LoaderCircle className="spin" size={16} /> Creating…</> : <>Create project <ArrowRight size={16} /></>}</button></div></form></section></div>}
      </main>
    </div>
  );
}

function NavButton({ active, icon, label, onClick }: { active: boolean; icon: React.ReactNode; label: string; onClick: () => void }) {
  return <button aria-current={active ? 'page' : undefined} className={`workspace-nav-button${active ? ' active' : ''}`} onClick={onClick}>{icon}<span>{label}</span></button>;
}

function DashboardCards({ projects, environmentCounts, loading }: { projects: Project[]; environmentCounts: Record<string, number> | null; loading: boolean }) {
  const variableTotal = environmentCounts ? Object.values(environmentCounts).reduce((sum, count) => sum + count, 0) : null;
  const environmentTotal = projects.length * 3;
  const envs = ['development', 'staging', 'production'];
  const counts = envs.map((environment) => environmentCounts?.[environment] ?? 0);
  const max = Math.max(1, ...counts);
  const total = counts.reduce((sum, count) => sum + count, 0);
  let position = 0;
  const stops = counts.map((count, index) => {
    const start = position; position += total ? count / total * 100 : 100 / 3;
    return `${['#241445', '#7550a9', '#c6b5e3'][index]} ${start}% ${position}%`;
  }).join(', ');
  return <>
    <section className="dashboard-stat-grid" aria-label="Workspace summary">
      <StatCard label="Projects" value={loading ? '—' : projects.length.toLocaleString()} icon={<FolderKanban size={19} />} tone="violet" />
      <StatCard label="Variables" value={loading || variableTotal === null ? '—' : variableTotal.toLocaleString()} icon={<ShieldCheck size={19} />} tone="blue" />
      <StatCard label="Project memberships" value={loading ? '—' : projects.reduce((sum, project) => sum + project.member_count, 0).toLocaleString()} icon={<Users size={19} />} tone="green" />
      <StatCard label="Environments" value={loading ? '—' : environmentTotal.toLocaleString()} icon={<ChartNoAxesColumnIncreasing size={19} />} tone="peach" />
    </section>
    <section className="dashboard-chart-grid" aria-label="Workspace data">
      <article className="dashboard-chart-card"><div className="section-heading"><div><h2>Variables by environment</h2><p>Counts across projects you can access</p></div><span className="chart-period-label">Current</span></div>{loading ? <p className="chart-unavailable">Loading environment data…</p> : environmentCounts === null ? <p className="chart-unavailable">Environment totals are unavailable for some projects.</p> : <div className="environment-bars">{envs.map((environment, index) => <div className="environment-bar-row" key={environment}><span>{environment[0].toUpperCase() + environment.slice(1)}</span><div><i style={{ width: `${(counts[index] / max) * 100}%` }} /></div><strong>{counts[index]}</strong></div>)}</div>}</article>
      <article className="dashboard-chart-card"><div className="section-heading"><div><h2>Environment share</h2><p>Variables in visible projects</p></div></div>{loading ? <p className="chart-unavailable">Loading environment data…</p> : environmentCounts === null ? <p className="chart-unavailable">Environment totals are unavailable.</p> : <div className="environment-share"><div className="environment-donut" style={{ background: `conic-gradient(${stops})` }}><span>{total}<small>variables</small></span></div><ul>{envs.map((environment, index) => <li key={environment}><i className={`donut-dot dot-${index}`} />{environment[0].toUpperCase() + environment.slice(1)}<strong>{total ? Math.round(counts[index] / total * 100) : 0}%</strong></li>)}</ul></div>}</article>
    </section>
  </>;
}

function StatCard({ label, value, icon, tone }: { label: string; value: string; icon: React.ReactNode; tone: string }) {
  return <article className={`dashboard-stat-card ${tone}`}><span className="dashboard-stat-icon">{icon}</span><div><span>{label}</span><strong>{value}</strong></div></article>;
}

function ManagedUsersPage({ projects, search, onManage }: { projects: Project[]; search: string; onManage: (project: Project) => void }) {
  const [memberships, setMemberships] = useState<{ member: ProjectMember; project: Project }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 10;
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    const managedProjects = projects.filter((project) => project.my_role === 'owner' || project.my_role === 'admin');
    Promise.all(managedProjects.map(async (project) => (await projectsApi.members(project.id)).map((member) => ({ member, project }))))
      .then((result) => { if (active) setMemberships(result.flat()); })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load project members.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projects]);
  useEffect(() => { setPage(1); }, [search]);
  const filtered = memberships.filter(({ member, project }) => `${member.username} ${member.email} ${project.name} ${member.role}`.toLowerCase().includes(search.toLowerCase()) && (!roleFilter || member.role === roleFilter));
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize);
  const managedProjects = projects.filter((project) => project.my_role === 'owner' || project.my_role === 'admin');
  return <section className="managed-users-page">
    <div className="section-heading"><div><span className="detail-label">PROJECT ACCESS</span><h2>Users</h2><p>Memberships in projects where you can manage access.</p></div><span className="project-total">{filtered.length} access records</span></div>
    {managedProjects.length === 0 ? <div className="availability-card detail-card"><span className="detail-icon"><UserRound size={20} /></span><h2>Project access management is limited</h2><p>Your account can only view the members of a project when its permission allows it. There is no global user directory or system user administration API in this application.</p></div> : error ? <p className="workspace-alert" role="alert">{error}</p> : loading ? <div className="workspace-loading" role="status"><LoaderCircle className="spin" size={18} /> Loading users…</div> : <><div className="managed-users-filters"><label>Role<select value={roleFilter} onChange={(event) => { setRoleFilter(event.target.value); setPage(1); }}><option value="">All roles</option><option value="admin">Admin</option><option value="manager">Manager</option><option value="member">Member</option></select></label></div><div className="management-table-wrap"><table className="management-table"><thead><tr><th>User</th><th>Email</th><th>Project</th><th>Role</th><th>Access</th></tr></thead><tbody>{pageItems.map(({ member, project }) => <tr key={`${project.id}-${member.user_id}`}><td><span className="table-user"><span className="member-avatar">{member.username.slice(0, 1).toUpperCase()}</span><strong>{member.username}</strong></span></td><td>{member.email || '—'}</td><td>{project.name}</td><td><span className={`role-pill ${member.role}`}>{member.role}</span></td><td><button className="workspace-secondary" onClick={() => onManage(project)}>Manage access</button></td></tr>)}</tbody></table>{filtered.length === 0 && <p className="management-empty">No project access records match these filters.</p>}</div>{filtered.length > pageSize && <nav className="management-pagination" aria-label="User list pagination"><span>Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filtered.length)} of {filtered.length}</span><button className="workspace-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page} of {pages}</span><button className="workspace-secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button></nav>}</>}
  </section>;
}

function UnavailablePage({ title, icon, copy, projects, loading, onOpen }: { title: string; icon: React.ReactNode; copy: string; projects?: Project[]; loading?: boolean; onOpen?: (project: Project) => void }) {
  return <section className="detail-card availability-card"><span className="detail-icon">{icon}</span><h2>{title}</h2><p>{copy}</p>{projects && <div className="availability-projects">{loading ? <p role="status">Loading projects…</p> : projects.length ? projects.map((project) => <button key={project.id} onClick={() => onOpen?.(project)}><span><strong>{project.name}</strong><small>{project.my_role} · {project.member_count} members</small></span><ArrowRight size={16} /></button>) : <p>No accessible projects found.</p>}</div>}</section>;
}

function SystemSettingsPage() {
  const [tab, setTab] = useState('General');
  const tabs = ['General', 'Security', 'Email', 'Audit & Logs', 'Backup'];
  return <section className="settings-page"><div className="settings-page-intro"><span className="detail-label">ADMINISTRATION</span><h2>System Settings</h2><p>Configure and manage platform settings.</p></div><div className="settings-page-layout"><nav className="settings-page-nav" aria-label="Settings sections">{tabs.map((item) => <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{item}</button>)}</nav><article className="settings-page-content"><h3>{tab === 'General' ? 'General Settings' : tab}</h3><p>Settings controls are unavailable because the current backend does not provide a system configuration API.</p>{tab === 'General' && <div className="settings-readonly-fields"><label>Platform Name<input value="EnvShare" readOnly /></label><label>Platform URL<input value={window.location.origin} readOnly /></label><label>Registration<span className="settings-status">Status not provided by the server</span></label></div>}<button className="workspace-primary" disabled>Save Changes</button></article></div></section>;
}
