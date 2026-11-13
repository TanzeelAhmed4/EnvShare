import { useEffect, useState } from 'react';
import { GitCompare, History, LoaderCircle, RotateCcw, Eye, EyeOff } from 'lucide-react';
import { ProjectVariable, VariableVersion, VariableVersionComparison, projectsApi } from './projectsApi';

type Props = { projectId: number; environmentId: number | null; canManageHistory: boolean; onAuditChange: () => void };
type HistoryRow = { variable: ProjectVariable; versions: VariableVersion[] };

export default function VersionHistoryPage({ projectId, environmentId, canManageHistory, onAuditChange }: Props) {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [compare, setCompare] = useState<{ variable: ProjectVariable; versions: VariableVersion[] } | null>(null);
  const [comparison, setComparison] = useState<VariableVersionComparison | null>(null);
  const [revealed, setRevealed] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let current = true;
    if (environmentId === null) { setRows([]); return () => { current = false; }; }
    setLoading(true); setError(''); setComparison(null); setRevealed({});
    projectsApi.variables(projectId, environmentId)
      .then((variables) => Promise.all(variables.map(async (variable) => ({
        variable,
        versions: await projectsApi.variableVersions(projectId, environmentId, variable.id),
      }))))
      .then((items) => { if (current) setRows(items); })
      .catch((cause) => { if (current) setError(cause instanceof Error ? cause.message : 'Could not load version history.'); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [projectId, environmentId]);

  async function compareVersions(variable: ProjectVariable, left: VariableVersion, right: VariableVersion) {
    if (environmentId === null) return;
    setBusy(true); setError(''); setComparison(null);
    try {
      setComparison(await projectsApi.compareVariableVersions(projectId, environmentId, variable.id, left.id, right.id));
      onAuditChange();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not compare these versions.'); }
    finally { setBusy(false); }
  }

  async function toggleReveal(variable: ProjectVariable, version: VariableVersion) {
    if (environmentId === null) return;
    if (Object.prototype.hasOwnProperty.call(revealed, version.id)) {
      setRevealed((current) => { const next = { ...current }; delete next[version.id]; return next; });
      return;
    }
    setBusy(true); setError('');
    try {
      const result = await projectsApi.variableVersionValue(projectId, environmentId, variable.id, version.id);
      setRevealed((current) => ({ ...current, [version.id]: result.value }));
      if (version.sensitivity === 'sensitive') onAuditChange();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not retrieve this version value.'); }
    finally { setBusy(false); }
  }

  async function restore(variable: ProjectVariable, version: VariableVersion) {
    if (environmentId === null || !canManageHistory || !window.confirm(`Restore ${variable.key} from version ${version.version_number}?`)) return;
    setBusy(true); setError('');
    try {
      await projectsApi.restoreVariableVersion(projectId, environmentId, variable.id, version.id);
      onAuditChange();
      const variables = await projectsApi.variables(projectId, environmentId);
      const updated = await Promise.all(variables.map(async (item) => ({ variable: item, versions: await projectsApi.variableVersions(projectId, environmentId, item.id) })));
      setRows(updated);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not restore this version.'); }
    finally { setBusy(false); }
  }

  return <section className="version-history-page" aria-labelledby="version-history-title">
    <div className="section-heading"><div><span className="detail-label">PROJECT CONFIGURATION</span><h2 id="version-history-title">Version history</h2><p>Inspect, compare, and restore saved variable versions.</p></div><span className="version-history-mark"><History size={17} /> {rows.reduce((sum, row) => sum + row.versions.length, 0)} versions</span></div>
    {environmentId === null && <div className="variables-empty"><h3>Select an environment first</h3><p>Choose Development, Staging, or Production from the Environments page.</p></div>}
    {error && <p className="workspace-alert" role="alert">{error}</p>}
    {loading ? <div className="variables-loading" role="status"><LoaderCircle className="spin" size={18} /> Loading version history…</div> : environmentId !== null && rows.length === 0 ? <div className="variables-empty"><h3>No variable versions yet</h3><p>Versions appear after variables are created or changed.</p></div> : <div className="version-history-list">{rows.map(({ variable, versions }) => <article className="version-history-variable" key={variable.id}>
      <div className="version-history-variable-heading"><div><code>{variable.key}</code><span>{variable.sensitivity === 'sensitive' ? 'Sensitive value' : 'Standard value'}</span></div><span className="version-count">{versions.length} versions</span></div>
      {versions.length === 0 ? <p className="member-empty">No saved versions.</p> : <ol>{versions.map((version, index) => <li key={version.id} className={index === 0 ? 'latest' : ''}><span className="version-marker" /><div className="version-history-details"><strong>v{version.version_number}.0 <small>{version.action}</small></strong><span>{new Date(version.created_at).toLocaleString()} · {version.actor_username}</span>{Object.prototype.hasOwnProperty.call(revealed, version.id) && <code className="version-value">{revealed[version.id]}</code>}</div><div className="version-history-actions">{version.sensitivity === 'sensitive' && <button className="workspace-secondary" onClick={() => void toggleReveal(variable, version)} disabled={busy} aria-label={revealed[version.id] ? 'Hide sensitive version' : 'Reveal sensitive version'}>{revealed[version.id] ? <EyeOff size={15} /> : <Eye size={15} />}{revealed[version.id] ? 'Hide' : 'Reveal'}</button>}<button className="workspace-secondary" onClick={() => setCompare((current) => current?.variable.id === variable.id && current.versions.some((item) => item.id === version.id) ? null : { variable, versions: [version] })}>Select to compare</button>{canManageHistory && <button className="workspace-secondary" onClick={() => void restore(variable, version)} disabled={busy}><RotateCcw size={14} /> Restore</button>}</div></li>)}</ol>}
      {compare?.variable.id === variable.id && <div className="version-compare-controls"><span><GitCompare size={15} /> Select two versions to compare</span>{versions.map((version) => <button key={version.id} className={compare.versions.some((item) => item.id === version.id) ? 'selected' : ''} onClick={() => { setComparison(null); setCompare((current) => { const selected = current?.variable.id === variable.id ? current.versions : []; return { variable, versions: selected.some((item) => item.id === version.id) ? selected.filter((item) => item.id !== version.id) : [...selected, version].slice(-2) }; }); }}>v{version.version_number}.0</button>)}<button className="workspace-primary" disabled={busy || compare.versions.length !== 2} onClick={() => compare.versions.length === 2 && void compareVersions(variable, compare.versions[0], compare.versions[1])}>Compare</button></div>}
      {comparison && compare?.variable.id === variable.id && <div className="version-comparison-result"><strong>{comparison.sensitive ? comparison.different ? 'Protected values differ' : 'Protected values are identical' : comparison.different ? 'Versions differ' : 'Versions are identical'}</strong>{!comparison.sensitive && comparison.diff?.map((line, lineIndex) => <code key={`${lineIndex}-${line}`}>{line}</code>)}</div>}
    </article>)}</div>}
  </section>;
}
