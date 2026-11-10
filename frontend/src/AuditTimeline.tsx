import { useEffect, useState } from 'react';
import { Clock3, History, LoaderCircle } from 'lucide-react';
import { AccessAuditEvent, AuditChange, AuditEvent, projectsApi } from './projectsApi';

type Props = { projectId: number; refreshToken: number };
const REDACTED = '[REDACTED]';

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

export default function AuditTimeline({ projectId, refreshToken }: Props) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    projectsApi.auditHistory(projectId)
      .then((items) => { if (active) setEvents(items); })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : 'Could not load audit history.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectId, refreshToken]);

  return (
    <section className="audit-card" aria-labelledby="audit-title">
      <div className="audit-heading"><span className="audit-icon"><History size={17} /></span><div><span className="detail-label">PROJECT ACTIVITY</span><h2 id="audit-title">Variable history</h2></div><span className="audit-count">{events.length} {events.length === 1 ? 'event' : 'events'}</span></div>
      {error && <p className="workspace-alert" role="alert">{error}</p>}
      {loading ? <div className="audit-state" role="status"><LoaderCircle className="spin" size={17} /> Loading history…</div> : events.length === 0 ? <p className="audit-empty">Variable changes will appear here.</p> : <ol className="audit-timeline" aria-label="Environment variable change history">{events.map((event) => {
        const details = Object.entries(event.changes) as [keyof AuditEvent['changes'], AuditChange][];
        return <li className={`audit-event ${event.action}`} key={event.id}><span className="audit-marker" aria-hidden="true" /><article><div className="audit-event-top"><p><strong>{event.actor}</strong> {event.action} <code>{event.variable_key}</code></p><span className={`audit-action ${event.action}`}>{event.action_label}</span></div><p className="audit-context">{event.environment_label} environment</p>{details.length > 0 && <ul className="audit-changes" aria-label="Change details">{details.map(([field, change]) => <li key={field}>{changeText(field === 'value' ? 'Value' : field === 'sensitivity' ? 'Classification' : 'Key', change, event.action)}</li>)}</ul>}<time dateTime={event.created_at}><Clock3 size={12} />{new Date(event.created_at).toLocaleString()}</time></article></li>;
      })}</ol>}
      <AccessHistory projectId={projectId} refreshToken={refreshToken} />
    </section>
  );
}

function AccessHistory({ projectId, refreshToken }: Props) {
  const [events, setEvents] = useState<AccessAuditEvent[]>([]);
  useEffect(() => {
    let active = true;
    projectsApi.accessAuditHistory(projectId).then((items) => { if (active) setEvents(items); }).catch(() => undefined);
    return () => { active = false; };
  }, [projectId, refreshToken]);
  if (events.length === 0) return null;
  return <><h3>Team access history</h3><ol className="audit-timeline" aria-label="Project access history">{events.map((event) => <li className="audit-event" key={event.id}>
    <span className="audit-marker" aria-hidden="true" /><article>
      <div className="audit-event-top"><p><strong>{event.actor_username}</strong> {event.action.replace(/_/g, ' ')} {event.target_username || event.target_email}</p>
        <span className="audit-action">{[event.role_before, event.role_after].filter(Boolean).join(' → ')}</span></div>
      <time dateTime={event.created_at}><Clock3 size={12} />{new Date(event.created_at).toLocaleString()}</time>
    </article>
  </li>)}</ol></>;
}
