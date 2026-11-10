import { apiRequest } from './authApi';

export type Project = {
  id: number;
  name: string;
  description: string;
  creator_id: number;
  creator_username: string;
  member_count: number;
  my_role: 'owner' | 'admin' | 'manager' | 'member';
  created_at: string;
  updated_at: string;
};

export type ProjectMember = {
  user_id: number;
  username: string;
  email: string;
  role: 'admin' | 'manager' | 'member';
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

export type ProjectInvitation = {
  id: number; email: string; role: 'admin' | 'manager' | 'member'; created_at?: string;
  expires_at: string; max_uses: number; use_count?: number; revoked?: boolean; expired?: boolean; exhausted?: boolean;
  token?: string;
};
export type AccessAuditEvent = {
  id: number; actor_username: string; action: string; target_email: string; target_username: string;
  role_before: string; role_after: string; created_at: string;
};

export const projectsApi = {
  list: () => apiRequest<Project[]>('/projects/'),
  get: (id: number) => apiRequest<Project>(`/projects/${id}/`),
  create: (data: Pick<Project, 'name' | 'description'>) => apiRequest<Project>('/projects/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  members: (id: number) => apiRequest<ProjectMember[]>(`/projects/${id}/members/`),
  addMember: (id: number, username: string, role: ProjectMember['role'] = 'member') => apiRequest<ProjectMember>(`/projects/${id}/members/`, {
    method: 'POST',
    body: JSON.stringify({ username, role }),
  }),
  removeMember: (projectId: number, userId: number) => apiRequest<null>(
    `/projects/${projectId}/members/${userId}/`,
    { method: 'DELETE' },
  ),
  updateMemberRole: (projectId: number, userId: number, role: ProjectMember['role']) => apiRequest<ProjectMember>(
    `/projects/${projectId}/members/${userId}/`, { method: 'PATCH', body: JSON.stringify({ role }) },
  ),
  invitations: (projectId: number) => apiRequest<ProjectInvitation[]>(`/projects/${projectId}/invitations/`),
  createInvitation: (projectId: number, data: { email: string; role: ProjectInvitation['role']; expires_in_hours: number; max_uses: number }) =>
    apiRequest<ProjectInvitation>(`/projects/${projectId}/invitations/`, { method: 'POST', body: JSON.stringify(data) }),
  revokeInvitation: (projectId: number, invitationId: number) => apiRequest<null>(
    `/projects/${projectId}/invitations/${invitationId}/`, { method: 'POST', body: JSON.stringify({}) },
  ),
  inspectInvitation: (token: string) => apiRequest<{ project_name: string; role: string; expires_at: string; uses_remaining: number }>(
    '/projects/invitations/inspect/', { method: 'POST', body: JSON.stringify({ token }) },
  ),
  acceptInvitation: (token: string) => apiRequest<{ project_id: number; project_name: string; role: string }>(
    '/projects/invitations/accept/', { method: 'POST', body: JSON.stringify({ token }) },
  ),
  delete: (projectId: number) => apiRequest<null>(`/projects/${projectId}/delete/`, { method: 'DELETE' }),
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
  accessAuditHistory: (projectId: number) => apiRequest<AccessAuditEvent[]>(`/projects/${projectId}/access-audit/`),
};
