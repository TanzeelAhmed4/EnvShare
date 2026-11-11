import { FormEvent, useEffect, useState } from 'react';
import { Clock3, History, LoaderCircle } from 'lucide-react';
import { AccessAuditEvent, AuditChange, AuditEvent, AuditFilters, AuditPage, Environment, projectsApi } from './projectsApi';
import { auditDisplayState } from './auditFilters';

type Props = { projectId: number; refreshToken: number };
const REDACTED = '[REDACTED]';
const PAGE_SIZE = 20;

function changeText(label: string, change: AuditChange, action: AuditEvent['action']) {
  if (label === 'Value' && (change.before === REDACTED || change.after === REDACTED)) {
    if (action === 'created') return 'Protected value added';
    if (action === 'deleted') return 'Protected value removed';
    return 'Protected value changed';
  }
  if (change.before === null) return `${label} set to ${change.after ?? ''}`;
  if (change.after === null) return `${label} removed (was ${change.before})`;
  return `${label}: ${change.before} → ${change.after}`;
}

function initialPage<T>(): AuditPage<T> {
  return { count: 0, next: null, previous: null, page: 1, page_size: PAGE_SIZE, results: [] };
}

export default function AuditTimeline({ projectId, refreshToken }: Props) {
  const [events, setEvents] = useState<AuditPage<AuditEvent>>(initialPage());
  const [accessEvents, setAccessEvents] = useState<AuditPage<AccessAuditEvent>>(initialPage());
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [draft, setDraft] = useState<AuditFilters>({});
  const [filters, setFilters] = useState<AuditFilters>({});
  const [page, setPage] = useState(1);
  const [accessPage, setAccessPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    projectsApi.environments(projectId).then((items) => { if (active) setEnvironments(items); }).catch(() => undefined);
    return () => { active = false; };
  }, [projectId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([
      projectsApi.auditHistory(projectId, { ...filters, page, page_size: PAGE_SIZE }),
      projectsApi.accessAuditHistory(projectId, { ...filters, page: accessPage, page_size: PAGE_SIZE }),
    ]).then(([variableResult, accessResult]) => {
      if (active) { setEvents(variableResult); setAccessEvents(accessResult); }
    }).catch((requestError) => {
      if (active) setError(requestError instanceof Error ? requestError.message : 'Could not load audit history.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectId, refreshToken, filters, page, accessPage]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters(draft);
    setPage(1);
    setAccessPage(1);
  }

  function clearFilters() {
    setDraft({}); setFilters({}); setPage(1); setAccessPage(1);
  }
  const displayState = auditDisplayState({
    loading, error, variableCount: events.results.length, accessCount: accessEvents.results.length,
  });

  return (
    <section className="audit-card" aria-labelledby="audit-title">
      <div className="audit-heading"><span className="audit-icon"><History size={17} /></span><div><span className="detail-label">PROJECT ACTIVITY</span><h2 id="audit-title">Audit history</h2></div><span className="audit-count">{events.count + accessEvents.count} events</span></div>
      <form className="audit-filters" onSubmit={applyFilters} aria-label="Audit filters">
        <label>Search<input value={draft.search ?? ''} onChange={(event) => setDraft({ ...draft, search: event.target.value })} maxLength={200} /></label>
        <label>Action<select value={draft.action ?? ''} onChange={(event) => setDraft({ ...draft, action: event.target.value })}>
          <option value="">All actions</option>
          <optgroup label="Variable activity">
            {['created', 'updated', 'deleted', 'revealed', 'bulk_imported', 'restored', 'version_accessed', 'version_compared'].map((action) => <option key={action} value={action}>{action.replace(/_/g, ' ')}</option>)}
          </optgroup>
          <optgroup label="Project access">
            {['project_created', 'membership_added', 'member_removed', 'role_changed', 'invitation_created', 'invitation_accepted', 'invitation_revoked'].map((action) => <option key={action} value={action}>{action.replace(/_/g, ' ')}</option>)}
          </optgroup>
        </select></label>
        <label>User<input value={draft.actor ?? ''} onChange={(event) => setDraft({ ...draft, actor: event.target.value })} maxLength={150} /></label>
        <label>Environment<select value={draft.environment ?? ''} onChange={(event) => setDraft({ ...draft, environment: event.target.value ? Number(event.target.value) : '' })}>
          <option value="">All environments</option>{environments.map((environment) => <option key={environment.id} value={environment.id}>{environment.label}</option>)}
        </select></label>
        <label>From<input type="date" value={draft.date_from ?? ''} onChange={(event) => setDraft({ ...draft, date_from: event.target.value })} /></label>
        <label>To<input type="date" value={draft.date_to ?? ''} onChange={(event) => setDraft({ ...draft, date_to: event.target.value })} /></label>
        <div className="audit-filter-actions"><button type="submit" className="workspace-primary">Apply filters</button><button type="button" className="workspace-secondary" onClick={clearFilters}>Clear filters</button></div>
      </form>
      {displayState === 'error' && <p className="workspace-alert" role="alert">{error}</p>}
      {displayState === 'loading' ? <div className="audit-state" role="status"><LoaderCircle className="spin" size={17} /> Loading history…</div> : displayState === 'error' ? null : displayState === 'empty' ? <p className="audit-empty">No audit events match these filters.</p> : <>
        {events.results.length > 0 && <><ol className="audit-timeline" aria-label="Environment variable audit events">{events.results.map((event) => {
          const details = Object.entries(event.changes) as [string, AuditChange][];
          const importEvent = event.changes.source?.after === 'bulk_import';
          return <li className={`audit-event ${event.action}`} key={event.id}><span className="audit-marker" aria-hidden="true" /><article><div className="audit-event-top"><p><strong>{event.actor}</strong> {importEvent ? 'imported' : event.action.replace(/_/g, ' ')} <code>{event.variable_key}</code></p><span className={`audit-action ${event.action}`}>{event.action_label}</span></div><p className="audit-context">{event.environment_label} environment</p>{details.length > 0 && <ul className="audit-changes" aria-label="Change details">{details.map(([field, change]) => <li key={field}>{changeText(field === 'value' ? 'Value' : field === 'sensitivity' ? 'Classification' : field, change, event.action)}</li>)}</ul>}<time dateTime={event.created_at}><Clock3 size={12} />{new Date(event.created_at).toLocaleString()}</time></article></li>;
        })}</ol><Pagination page={page} count={events.count} pageSize={events.page_size} onChange={setPage} label="Variable audit" /></>}
        {accessEvents.results.length > 0 && <><h3>Team access history</h3><ol className="audit-timeline" aria-label="Project access audit events">{accessEvents.results.map((event) => <li className="audit-event" key={event.id}><span className="audit-marker" aria-hidden="true" /><article><div className="audit-event-top"><p><strong>{event.actor_username}</strong> {event.action.replace(/_/g, ' ')} {event.target_username || event.target_email}</p><span className="audit-action">{[event.role_before, event.role_after].filter(Boolean).join(' → ')}</span></div><time dateTime={event.created_at}><Clock3 size={12} />{new Date(event.created_at).toLocaleString()}</time></article></li>)}</ol><Pagination page={accessPage} count={accessEvents.count} pageSize={accessEvents.page_size} onChange={setAccessPage} label="Access audit" /></>}
      </>}
    </section>
  );
}

function Pagination({ page, count, pageSize, onChange, label }: { page: number; count: number; pageSize: number; onChange: (value: number) => void; label: string }) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  return <nav className="audit-pagination" aria-label={`${label} pagination`}><button className="workspace-secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button><span>Page {page} of {pages}</span><button className="workspace-secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</button></nav>;
}
