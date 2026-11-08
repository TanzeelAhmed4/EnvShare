import { apiRequest } from './authApi';

export type Project = {
  id: number;
  name: string;
  description: string;
  creator_id: number;
  creator_username: string;
  member_count: number;
  created_at: string;
  updated_at: string;
};

export type ProjectMember = {
  user_id: number;
  username: string;
  email: string;
  role: 'member';
  created_at: string;
};

export type Environment = {
  id: number;
  name: 'development' | 'staging' | 'production';
  label: 'Development' | 'Staging' | 'Production';
};

export type ProjectVariable = {
  id: number;
  environment_id: number;
  key: string;
  value: string;
  sensitivity: 'standard' | 'sensitive';
  created_at: string;
  updated_at: string;
};

export type ImportPreviewItem = {
  classification: 'New' | 'Update' | 'Unchanged';
  key: string;
  old_value: string | null;
  new_value: string;
  sensitivity: 'standard' | 'sensitive' | null;
};

export type ImportPreview = {
  preview: ImportPreviewItem[];
  invalid_lines: { line: number; message: string }[];
  preview_token: string;
};

export type AuditChange = { before: string | null; after: string | null };
export type AuditEvent = {
  id: number;
  project_name: string;
  environment_name: string;
  environment_label: string;
  variable_id: number;
  variable_key: string;
  action: 'created' | 'updated' | 'deleted' | 'revealed';
  action_label: string;
  actor: string;
  changes: { key?: AuditChange; sensitivity?: AuditChange; value?: AuditChange };
  created_at: string;
};

export const projectsApi = {
  list: () => apiRequest<Project[]>('/projects/'),
  get: (id: number) => apiRequest<Project>(`/projects/${id}/`),
  create: (data: Pick<Project, 'name' | 'description'>) => apiRequest<Project>('/projects/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  members: (id: number) => apiRequest<ProjectMember[]>(`/projects/${id}/members/`),
  addMember: (id: number, username: string) => apiRequest<ProjectMember>(`/projects/${id}/members/`, {
    method: 'POST',
    body: JSON.stringify({ username }),
  }),
  removeMember: (projectId: number, userId: number) => apiRequest<null>(
    `/projects/${projectId}/members/${userId}/`,
    { method: 'DELETE' },
  ),
  environments: (projectId: number) => apiRequest<Environment[]>(`/projects/${projectId}/environments/`),
  variables: (projectId: number, environmentId: number) => apiRequest<ProjectVariable[]>(
    `/projects/${projectId}/environments/${environmentId}/variables/`,
  ),
  createVariable: (projectId: number, environmentId: number, data: Partial<ProjectVariable>) =>
    apiRequest<ProjectVariable>(`/projects/${projectId}/environments/${environmentId}/variables/`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateVariable: (projectId: number, environmentId: number, variableId: number, data: Partial<ProjectVariable>) =>
    apiRequest<ProjectVariable>(
      `/projects/${projectId}/environments/${environmentId}/variables/${variableId}/`,
      { method: 'PATCH', body: JSON.stringify(data) },
    ),
  deleteVariable: (projectId: number, environmentId: number, variableId: number) =>
    apiRequest<null>(
      `/projects/${projectId}/environments/${environmentId}/variables/${variableId}/`,
      { method: 'DELETE' },
    ),
  revealVariable: (projectId: number, environmentId: number, variableId: number) =>
    apiRequest<{ key: string; value: string }>(
      `/projects/${projectId}/environments/${environmentId}/variables/${variableId}/reveal/`,
      { method: 'POST', body: JSON.stringify({}) },
    ),
  previewImport: (projectId: number, environmentId: number, content: string, classifications: Record<string, 'standard' | 'sensitive'>) =>
    apiRequest<ImportPreview>(`/projects/${projectId}/environments/${environmentId}/import/preview/`, {
      method: 'POST', body: JSON.stringify({ content, classifications }),
    }),
  confirmImport: (projectId: number, environmentId: number, content: string, classifications: Record<string, 'standard' | 'sensitive'>, previewToken: string) =>
    apiRequest<{ created: number; updated: number; unchanged: number }>(
      `/projects/${projectId}/environments/${environmentId}/import/confirm/`,
      { method: 'POST', body: JSON.stringify({ content, classifications, confirm: true, preview_token: previewToken }) },
    ),
  auditHistory: (projectId: number) => apiRequest<AuditEvent[]>(`/projects/${projectId}/audit/`),
};
