import { FormEvent, useEffect, useState } from 'react';
import { Eye, EyeOff, KeyRound, LoaderCircle, LockKeyhole, Pencil, Plus, ShieldCheck, Trash2 } from 'lucide-react';
import { Environment, ImportPreview, ProjectVariable, projectsApi } from './projectsApi';

type Props = {
  projectId: number;
  onAuditChange: () => void;
  environments: Environment[];
  selectedEnvironmentId: number | null;
  onSelectEnvironment: (id: number) => void;
};

export default function EnvironmentVariables({ projectId, onAuditChange, environments, selectedEnvironmentId, onSelectEnvironment }: Props) {
  const [variables, setVariables] = useState<ProjectVariable[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [revealed, setRevealed] = useState<Record<number, string>>({});
  const [editor, setEditor] = useState<ProjectVariable | 'new' | null>(null);
  const [replaceSensitiveValue, setReplaceSensitiveValue] = useState(false);
  const [selectedSensitivity, setSelectedSensitivity] = useState<'standard' | 'sensitive'>('standard');
  const [reload, setReload] = useState(0);
  const [importOpen, setImportOpen] = useState(false);
  const [importContent, setImportContent] = useState('');
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null);
  const [importClassifications, setImportClassifications] = useState<Record<string, 'standard' | 'sensitive'>>({});
  const [importNotice, setImportNotice] = useState('');

  useEffect(() => {
    if (!selectedEnvironmentId) return;
    let current = true;
    setLoading(true);
    setError('');
    setRevealed({});
    projectsApi.variables(projectId, selectedEnvironmentId)
      .then((items) => { if (current) setVariables(items); })
      .catch((requestError) => {
        if (current) setError(requestError instanceof Error ? requestError.message : 'Could not load variables.');
      })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [projectId, selectedEnvironmentId, reload]);

  function startCreate() {
    setSelectedSensitivity('standard');
    setReplaceSensitiveValue(false);
    setEditor('new');
    setError('');
  }

  function startEdit(variable: ProjectVariable) {
    setSelectedSensitivity(variable.sensitivity);
    setReplaceSensitiveValue(false);
    setEditor(variable);
    setError('');
  }

  async function saveVariable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedEnvironmentId || editor === null) return;
    const form = new FormData(event.currentTarget);
    const payload: { key: string; sensitivity: 'standard' | 'sensitive'; value?: string } = {
      key: String(form.get('key') ?? '').trim(),
      sensitivity: selectedSensitivity,
    };
    const editingSensitive = editor !== 'new' && editor.sensitivity === 'sensitive';
    if (editor === 'new' || !editingSensitive || replaceSensitiveValue) {
      payload.value = String(form.get('value') ?? '');
    }

    setBusy(true);
    setError('');
    try {
      if (editor === 'new') {
        await projectsApi.createVariable(projectId, selectedEnvironmentId, payload);
      } else {
        await projectsApi.updateVariable(projectId, selectedEnvironmentId, editor.id, payload);
      }
      setEditor(null);
      setReload((version) => version + 1);
      onAuditChange();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not save this variable.');
    } finally {
      setBusy(false);
    }
  }

  async function deleteVariable(variable: ProjectVariable) {
    if (!selectedEnvironmentId || !window.confirm(`Delete ${variable.key} from this environment?`)) return;
    setBusy(true);
    setError('');
    try {
      await projectsApi.deleteVariable(projectId, selectedEnvironmentId, variable.id);
      setRevealed((current) => { const next = { ...current }; delete next[variable.id]; return next; });
      setReload((version) => version + 1);
      onAuditChange();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not delete this variable.');
    } finally {
      setBusy(false);
    }
  }

  async function toggleReveal(variable: ProjectVariable) {
    if (!selectedEnvironmentId) return;
    if (Object.prototype.hasOwnProperty.call(revealed, variable.id)) {
      setRevealed((current) => { const next = { ...current }; delete next[variable.id]; return next; });
      return;
    }
    setError('');
    try {
      const result = await projectsApi.revealVariable(projectId, selectedEnvironmentId, variable.id);
      setRevealed((current) => ({ ...current, [variable.id]: result.value }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not reveal this value.');
    }
  }

  function openImport() {
    setImportContent('');
    setImportPreview(null);
    setImportClassifications({});
    setError('');
    setImportNotice('');
    setImportOpen(true);
  }

  async function previewImport(classifications = importClassifications) {
    if (!selectedEnvironmentId) return;
    setBusy(true);
    setError('');
    try {
      const result = await projectsApi.previewImport(projectId, selectedEnvironmentId, importContent, classifications);
      setImportPreview(result);
    } catch (requestError) {
      setImportPreview(null);
      setError(requestError instanceof Error ? requestError.message : 'Could not preview this import.');
    } finally {
      setBusy(false);
    }
  }

  async function confirmImport() {
    if (!selectedEnvironmentId || !importPreview || importPreview.invalid_lines.length > 0) return;
    setBusy(true);
    setError('');
    try {
      const result = await projectsApi.confirmImport(projectId, selectedEnvironmentId, importContent, importClassifications, importPreview.preview_token);
      setImportOpen(false);
      setImportPreview(null);
      setReload((version) => version + 1);
      onAuditChange();
      setImportNotice(`Import saved: ${result.created} new, ${result.updated} updated, ${result.unchanged} unchanged.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not save this import.');
    } finally {
      setBusy(false);
    }
  }

  const activeEnvironment = environments.find((environment) => environment.id === selectedEnvironmentId);
  const editing = editor !== null && editor !== 'new' ? editor : null;

  return (
    <section className="variable-manager" aria-labelledby="variables-title">
      <div className="variables-heading"><div><span className="detail-label">PROJECT CONFIGURATION</span><h2 id="variables-title">Environment variables</h2><p>Switch environments to manage each project's configuration.</p></div><span className="variable-count"><KeyRound size={14} /> {variables.length} {variables.length === 1 ? 'variable' : 'variables'}</span></div>
      <div className="environment-tabs" role="tablist" aria-label="Project environments">
        {environments.map((environment) => <button
          key={environment.id}
          role="tab"
          aria-selected={environment.id === selectedEnvironmentId}
          className={`environment-tab ${environment.name} ${environment.id === selectedEnvironmentId ? 'active' : ''}`}
          onClick={() => onSelectEnvironment(environment.id)}
        ><span className="environment-tab-dot" />{environment.label}</button>)}
      </div>
      <div className="variable-toolbar"><div><strong>{activeEnvironment?.label ?? 'Environment'}</strong><span>Changes are saved to this environment only.</span></div><div className="variable-toolbar-actions"><button className="workspace-secondary" onClick={openImport} disabled={!selectedEnvironmentId}>Import .env</button><button className="workspace-primary" onClick={startCreate} disabled={!selectedEnvironmentId}><Plus size={16} /> Add variable</button></div></div>
      {error && <p className="workspace-alert variable-alert" role="alert">{error}</p>}
      {importNotice && <p className="import-success" role="status">{importNotice}</p>}

      {loading ? <div className="variables-loading" role="status"><LoaderCircle className="spin" size={18} /> Loading variables…</div> : variables.length === 0 ? <div className="variables-empty"><span><KeyRound size={21} /></span><h3>No variables in {activeEnvironment?.label ?? 'this environment'} yet</h3><p>Add a key and value to start building this environment's configuration.</p><button className="workspace-secondary" onClick={startCreate}><Plus size={15} /> Add the first variable</button></div> : <div className="variable-table-wrap"><table className="variable-table"><thead><tr><th>KEY</th><th>VALUE</th><th>CLASSIFICATION</th><th aria-label="Actions" /></tr></thead><tbody>{variables.map((variable) => {
        const isRevealed = Object.prototype.hasOwnProperty.call(revealed, variable.id);
        return <tr key={variable.id}>
          <td><code>{variable.key}</code></td>
          <td><div className="variable-value-cell"><span className={variable.sensitivity === 'sensitive' && !isRevealed ? 'masked-value' : 'variable-value'}>{isRevealed ? revealed[variable.id] : variable.value}</span>{variable.sensitivity === 'sensitive' && <button className="reveal-button" onClick={() => void toggleReveal(variable)} aria-label={isRevealed ? `Hide ${variable.key}` : `Reveal ${variable.key}`} title={isRevealed ? 'Hide value' : 'Reveal value'}>{isRevealed ? <EyeOff size={15} /> : <Eye size={15} />}</button>}</div></td>
          <td><span className={`classification-pill ${variable.sensitivity}`}>{variable.sensitivity === 'sensitive' ? <LockKeyhole size={12} /> : <ShieldCheck size={12} />}{variable.sensitivity === 'sensitive' ? 'Sensitive' : 'Standard'}</span></td>
          <td><div className="variable-actions"><button onClick={() => startEdit(variable)} aria-label={`Edit ${variable.key}`} title="Edit"><Pencil size={14} /></button><button onClick={() => void deleteVariable(variable)} disabled={busy} aria-label={`Delete ${variable.key}`} title="Delete"><Trash2 size={14} /></button></div></td>
        </tr>;
      })}</tbody></table></div>}

      {importOpen && <div className="modal-backdrop" role="presentation"><section className="project-modal import-modal" role="dialog" aria-modal="true" aria-labelledby="env-import-title"><button className="modal-close" onClick={() => setImportOpen(false)} aria-label="Close import">×</button><span className="form-eyebrow">BULK CONFIGURATION</span><h2 id="env-import-title">Import .env values</h2><p className="modal-copy">Preview changes for {activeEnvironment?.label ?? 'this environment'}. Nothing is saved until you confirm.</p><label className="import-label" htmlFor="env-import-content">Paste .env content</label><textarea id="env-import-content" className="import-source" rows={7} spellCheck={false} placeholder={'API_URL=https://example.com\nFEATURE_FLAG="enabled"'} value={importContent} onChange={(event) => { setImportContent(event.target.value); setImportPreview(null); setImportClassifications({}); }} />
        {importPreview && <div className="import-preview" aria-live="polite"><h3>Import preview <span>{importPreview.preview.length} entries</span></h3>{importPreview.invalid_lines.length > 0 && <div className="import-invalid" role="alert"><strong>Fix these lines before saving</strong>{importPreview.invalid_lines.map((item) => <p key={`${item.line}-${item.message}`}>Line {item.line}: {item.message}</p>)}</div>}{importPreview.preview.length === 0 ? <p className="import-empty">No valid variable entries found.</p> : <div className="import-preview-list">{importPreview.preview.map((item) => { const classification = importClassifications[item.key]; const newValue = item.classification === 'New' && classification !== 'standard' ? '••••••••' : item.new_value; return <article className="import-preview-row" key={item.key}><div className="import-preview-top"><code>{item.key}</code><span className={`import-classification ${item.classification.toLowerCase()}`}>{item.classification}</span></div>{item.classification === 'Update' ? <div className="import-values"><div><small>Old value</small><code>{item.old_value}</code></div><div><small>New value</small><code>{item.new_value}</code></div></div> : item.classification === 'New' ? <div className="import-new-value"><code>{newValue}</code><label>Classification<select value={classification ?? ''} onChange={(event) => { const value = event.target.value as 'standard' | 'sensitive'; const next = { ...importClassifications, [item.key]: value }; setImportClassifications(next); void previewImport(next); }}><option value="" disabled>Choose…</option><option value="standard">Standard</option><option value="sensitive">Sensitive</option></select></label></div> : <div className="import-unchanged-value"><small>Unchanged</small><code>{item.new_value}</code></div>}</article>; })}</div>}</div>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="modal-actions"><button className="workspace-secondary" type="button" onClick={() => setImportOpen(false)}>Cancel</button>{!importPreview ? <button className="workspace-primary" type="button" onClick={() => void previewImport()} disabled={busy || !importContent.trim()}>{busy ? 'Preparing…' : 'Preview import'}</button> : <button className="workspace-primary" type="button" onClick={() => void confirmImport()} disabled={busy || importPreview.invalid_lines.length > 0 || importPreview.preview.length === 0 || importPreview.preview.some((item) => item.classification === 'New' && !importClassifications[item.key])}>{busy ? 'Saving…' : 'Confirm and save'}</button>}</div>
      </section></div>}

      {editor !== null && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setEditor(null); }}><section className="project-modal variable-modal" role="dialog" aria-modal="true" aria-labelledby="variable-editor-title"><button className="modal-close" onClick={() => setEditor(null)} aria-label="Close variable form">×</button><span className="form-eyebrow">{editing ? 'EDIT CONFIGURATION' : 'NEW CONFIGURATION'}</span><h2 id="variable-editor-title">{editing ? `Edit ${editing.key}` : 'Add a variable'}</h2><p className="modal-copy">This value belongs to {activeEnvironment?.label ?? 'the selected environment'}.</p><form className="project-form" onSubmit={saveVariable}>
        <label htmlFor="variable-key">Key</label><input id="variable-key" name="key" defaultValue={editing?.key ?? ''} maxLength={255} pattern="[A-Za-z_][A-Za-z0-9_]*" title="Use letters, numbers, and underscores; start with a letter or underscore." required autoFocus />
        {editing?.sensitivity === 'sensitive' && <label className="replace-sensitive-option"><input type="checkbox" checked={replaceSensitiveValue} onChange={(event) => setReplaceSensitiveValue(event.target.checked)} /> Replace the protected value</label>}
        <label htmlFor="variable-value">Value</label><textarea id="variable-value" name="value" rows={3} required={editor === 'new' || !editing || editing.sensitivity === 'standard' || replaceSensitiveValue} disabled={Boolean(editing?.sensitivity === 'sensitive' && !replaceSensitiveValue)} placeholder={editing?.sensitivity === 'sensitive' && !replaceSensitiveValue ? 'Protected value (unchanged)' : 'Enter the environment value'} defaultValue={editing?.sensitivity === 'standard' ? editing.value : ''} />
        <label htmlFor="variable-sensitivity">Classification</label><select id="variable-sensitivity" value={selectedSensitivity} onChange={(event) => setSelectedSensitivity(event.target.value as 'standard' | 'sensitive')}><option value="standard">Standard</option><option value="sensitive">Sensitive</option></select>
        {editing?.sensitivity === 'sensitive' && selectedSensitivity === 'standard' && <p className="sensitivity-warning">Changing this to Standard makes the current value visible in normal responses.</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="modal-actions"><button className="workspace-secondary" type="button" onClick={() => setEditor(null)}>Cancel</button><button className="workspace-primary" type="submit" disabled={busy}>{busy ? <><LoaderCircle className="spin" size={15} /> Saving…</> : 'Save variable'}</button></div>
      </form></section></div>}
    </section>
  );
}
