import { FormEvent, useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, Boxes, CirclePlus, FolderKanban, LoaderCircle, LogOut, ShieldCheck, UserPlus, Users, X } from 'lucide-react';
import { AuthUser, authApi } from './authApi';
import EnvironmentVariables from './EnvironmentVariables';
import AuditTimeline from './AuditTimeline';
import { Environment, Project, ProjectMember, projectsApi } from './projectsApi';

type Props = { user: AuthUser; onLogout: () => void };

export default function ProjectWorkspace({ user, onLogout }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [activeEnvironmentId, setActiveEnvironmentId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [memberUsername, setMemberUsername] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [auditRefresh, setAuditRefresh] = useState(0);

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

  async function openProject(project: Project) {
    setError('');
    setNotice('');
    setMembers([]);
    try {
      const detail = await projectsApi.get(project.id);
      setActiveProject(detail);
      const projectEnvironments = await projectsApi.environments(detail.id);
      setEnvironments(projectEnvironments);
      setActiveEnvironmentId(projectEnvironments[0]?.id ?? null);
      if (detail.creator_id === user.id) setMembers(await projectsApi.members(detail.id));
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
      const member = await projectsApi.addMember(activeProject.id, memberUsername.trim());
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

  const ownsActiveProject = activeProject?.creator_id === user.id;

  return (
    <main className="workspace-shell">
      <header className="workspace-topbar">
        <a className="auth-brand" href="#projects" aria-label="EnvShare projects"><span className="auth-brand-mark"><Boxes size={17} /></span><span>env<span>share</span></span></a>
        <div className="workspace-account"><span className="account-avatar">{user.username.slice(0, 1).toUpperCase()}</span><span className="account-name">{user.username}</span><button onClick={() => void signOut()} className="signout-button" aria-label="Sign out" disabled={signingOut}><LogOut size={16} /><span>{signingOut ? 'Signing out…' : 'Sign out'}</span></button></div>
      </header>

      <div className="workspace-content" id="projects">
        <div className="workspace-heading"><div><div className="auth-eyebrow"><span /> YOUR WORKSPACE</div><h1>{activeProject ? activeProject.name : 'Projects'}</h1><p>{activeProject ? activeProject.description || 'Project workspace and team access.' : 'Organize project access and keep your team working together.'}</p></div>
          {activeProject ? <button className="workspace-secondary" onClick={() => { setActiveProject(null); setEnvironments([]); setActiveEnvironmentId(null); setError(''); setNotice(''); }}><ArrowLeft size={16} /> All projects</button> : <button className="workspace-primary" onClick={() => { setShowCreate(true); setError(''); }}><CirclePlus size={17} /> New project</button>}
        </div>

        {error && <p className="workspace-alert" role="alert">{error}</p>}
        {notice && <p className="workspace-notice" role="status">{notice}</p>}

        {!activeProject && <section className="project-section" aria-label="Your projects">
          <div className="section-heading"><div><h2>Your projects</h2><p>Only projects you created or joined appear here.</p></div><span className="project-total">{projects.length} {projects.length === 1 ? 'project' : 'projects'}</span></div>
          {loading ? <div className="workspace-loading" role="status"><LoaderCircle className="spin" size={19} /> Loading projects…</div> : projects.length === 0 ? <div className="projects-empty"><span className="empty-folder"><FolderKanban size={23} /></span><h3>Start with a project</h3><p>Create a project, then add registered teammates who need access.</p><button className="workspace-primary" onClick={() => setShowCreate(true)}><CirclePlus size={16} /> Create a project</button></div> : <div className="project-grid">{projects.map((project) => <article className="project-card" key={project.id}>
            <div className="project-card-top"><span className="project-card-icon"><FolderKanban size={18} /></span><span className={project.creator_id === user.id ? 'role-pill owner' : 'role-pill'}>{project.creator_id === user.id ? 'Creator' : 'Member'}</span></div>
            <h3>{project.name}</h3><p>{project.description || 'No description added.'}</p>
            <div className="project-card-meta"><span><Users size={14} /> {project.member_count} {project.member_count === 1 ? 'member' : 'members'}</span><span>Updated {new Date(project.updated_at).toLocaleDateString()}</span></div>
            <button className="project-open" onClick={() => void openProject(project)}>Open project <ArrowRight size={15} /></button>
          </article>)}</div>}
        </section>}

        {activeProject && <section className="project-detail-grid">
          <article className="detail-card project-overview"><div className="detail-card-heading"><span className="detail-icon"><FolderKanban size={18} /></span><span className={ownsActiveProject ? 'role-pill owner' : 'role-pill'}>{ownsActiveProject ? 'Creator' : 'Member'}</span></div><span className="detail-label">PROJECT DETAILS</span><h2>{activeProject.name}</h2><p>{activeProject.description || 'This project does not have a description yet.'}</p><div className="detail-meta"><span>Created by <strong>{activeProject.creator_username}</strong></span><span>Created {new Date(activeProject.created_at).toLocaleDateString()}</span></div>
            <div className="phase-callout"><ShieldCheck size={16} /><span><strong>Project access is ready</strong><small>Environment variables are scoped to this project's members.</small></span></div>
          </article>
          {ownsActiveProject ? <article className="detail-card team-card"><div className="team-heading"><div><span className="detail-label">ACCESS CONTROL</span><h2>Team members</h2></div><span className="member-count">{members.length}</span></div><p className="team-description">Members can view and edit this project’s data. Only you can manage access.</p>
            <form className="member-add-form" onSubmit={addMember}><label htmlFor="member-username">Add a registered user</label><div className="member-input-row"><input id="member-username" value={memberUsername} onChange={(event) => setMemberUsername(event.target.value)} placeholder="Enter their username" required maxLength={150} /><button type="submit" disabled={busy || !memberUsername.trim()} aria-label="Add project member"><UserPlus size={16} /> Add</button></div></form>
            <div className="member-list" aria-label="Project members">{members.length === 0 ? <div className="member-empty">No teammates added yet.</div> : members.map((member) => <div className="member-row" key={member.user_id}><span className="member-avatar">{member.username.slice(0, 1).toUpperCase()}</span><span className="member-info"><strong>{member.username}</strong><small>{member.email}</small></span><span className="member-role">Member</span><button className="remove-member" onClick={() => void removeMember(member)} disabled={busy} aria-label={`Remove ${member.username}`} title={`Remove ${member.username}`}><X size={16} /></button></div>)}</div>
          </article> : <article className="detail-card team-card member-access-card"><div className="detail-icon"><Users size={18} /></div><span className="detail-label">TEAM ACCESS</span><h2>You’re a project member</h2><p>You can view and edit this project’s variables. Ask the project creator to update team access.</p><span className="member-role large">Member</span></article>}
          <EnvironmentVariables
            projectId={activeProject.id}
            onAuditChange={() => setAuditRefresh((version) => version + 1)}
            environments={environments}
            selectedEnvironmentId={activeEnvironmentId}
            onSelectEnvironment={setActiveEnvironmentId}
          />
          <AuditTimeline projectId={activeProject.id} refreshToken={auditRefresh} />
        </section>}
      </div>

      <footer className="workspace-footer"><span>ENVSHARE <i>/</i> PROJECT WORKSPACE</span><span><ShieldCheck size={14} /> Project membership controls access</span></footer>

      {showCreate && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowCreate(false); }}><section className="project-modal" role="dialog" aria-modal="true" aria-labelledby="create-project-title"><button className="modal-close" onClick={() => setShowCreate(false)} aria-label="Close project form"><X size={18} /></button><span className="form-eyebrow">NEW WORKSPACE</span><h2 id="create-project-title">Create a project</h2><p className="modal-copy">Start a shared space for one of your team's projects.</p><form className="project-form" onSubmit={createProject}><label htmlFor="project-name">Project name</label><input id="project-name" name="name" placeholder="e.g. Payments API" maxLength={120} required autoFocus /><label htmlFor="project-description">Description <span>Optional</span></label><textarea id="project-description" name="description" placeholder="What is this project for?" rows={3} /><div className="modal-actions"><button className="workspace-secondary" type="button" onClick={() => setShowCreate(false)}>Cancel</button><button className="workspace-primary" type="submit" disabled={busy}>{busy ? <><LoaderCircle className="spin" size={16} /> Creating…</> : <>Create project <ArrowRight size={16} /></>}</button></div></form></section></div>}
    </main>
  );
}
