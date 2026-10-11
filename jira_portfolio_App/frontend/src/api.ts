const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Envelope<T> = { items: T[]; next_cursor: string | null; total_count: number; sync_version: number }
export type Project = { jira_project_id: string; key: string; name: string; active: boolean; updated_at: string }
export type Field = { jira_field_id: string; name: string; schema_json: Record<string, unknown>; is_custom: boolean; searchable: boolean; selected: boolean; last_seen_at: string }
export type Connection = { connected: boolean; base_url: string; account: { account_id?: string; display_name?: string } }
export type SyncRun = { id: number; status: string; mode: string; projects: string[]; started_at: string; finished_at?: string; fetched_count: number; upserted_count: number; missing_count: number; anomaly_count: number; watermark_after?: string; error?: Record<string, unknown> }
export type Issue = { jira_issue_id: string; issue_key: string; project_id: string; summary: string; parent_jira_issue_id?: string; issue_type: {id?: string; name?: string; hierarchy_level?: number}; status: {id?: string; name?: string; category_key?: string}; updated_at?: string; baseline_due_at?: string | null; due_at?: string | null; configured_fields?: Record<string, unknown> }
export type PortfolioMetric = {metric_id: string; value: number | null; numerator: number; denominator: number; unit: string; as_of?: string; warnings: string[]}
export type PortfolioSummary = {metrics: PortfolioMetric[]; scope_count: number; null_counts: Record<string, number>; sync_version: number}
export type TraceabilityConfig = {project_id: string; grouping_fields: string[]; level_captions: string[]; updated_at: string | null; persisted: boolean}
export type WbsFlow = {project_id: string; levels: {field_id: string; caption: string}[]; nodes: {id: string; label: string; level: number; value: number}[]; links: {source: string; target: string; value: number}[]; issue_count: number; sync_version: number}
export type LiveIssueMetadata = {id?: string; key: string; self?: string; fields: Record<string, unknown>; names: Record<string, string>; schema: Record<string, Record<string, unknown>>}
export type GridConfig = {project_id: string; mandatory_columns: string[]; optional_fields: {field_id: string; name: string}[]; updated_at: string | null; persisted: boolean}
export type SprintViewConfig = {project_id: string; grouping_fields: string[]; level_captions: string[]; updated_at: string | null; persisted: boolean}
export type AppUser = {id: number; username: string; display_name: string; role: 'admin' | 'user'; screen_permissions: string[]; active: boolean}
export type UserPayload = {username: string; display_name: string; password?: string; role: 'admin' | 'user'; screen_permissions: string[]; active: boolean}

const tokenKey = 'portfolio_intelligence_session'
export const authToken = {
  get: () => typeof localStorage === 'undefined' ? null : localStorage.getItem(tokenKey),
  set: (token: string) => { if (typeof localStorage !== 'undefined') localStorage.setItem(tokenKey, token) },
  clear: () => { if (typeof localStorage !== 'undefined') localStorage.removeItem(tokenKey) },
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = authToken.get()
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers: {'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {}), ...init?.headers} })
  const body = response.status === 204 ? null : await response.json()
  if (!response.ok) {
    const errorBody = body as {message?: string; detail?: string} | null
    throw new Error(errorBody?.message ?? errorBody?.detail ?? 'Request failed')
  }
  return body as T
}

export const api = {
  login: (username: string, password: string) => request<{token: string; expires_at: string; user: AppUser}>('/api/v1/auth/login', {method: 'POST', body: JSON.stringify({username, password})}),
  me: () => request<AppUser>('/api/v1/auth/me'),
  logout: () => request<void>('/api/v1/auth/logout', {method: 'POST'}),
  users: () => request<{items: AppUser[]; screens: string[]}>('/api/v1/admin/users'),
  createUser: (payload: UserPayload) => request<AppUser>('/api/v1/admin/users', {method: 'POST', body: JSON.stringify(payload)}),
  updateUser: (id: number, payload: UserPayload) => request<AppUser>(`/api/v1/admin/users/${id}`, {method: 'PUT', body: JSON.stringify(payload)}),
  deleteUser: (id: number) => request<void>(`/api/v1/admin/users/${id}`, {method: 'DELETE'}),
  health: () => request<{status: string; jira_configured: boolean}>('/api/v1/health/ready'),
  testConnection: () => request<Connection>('/api/v1/jira/test-connection', {method: 'POST'}),
  issueMetadata: (issueIdOrKey: string) => request<LiveIssueMetadata>(`/api/v1/jira/issues/${encodeURIComponent(issueIdOrKey)}/metadata`),
  refresh: () => request<{status: string; counts: Record<string, number>; warnings: unknown[]}>('/api/v1/admin/metadata/refresh', {method: 'POST'}),
  projects: () => request<Envelope<Project>>('/api/v1/jira/projects'),
  traceabilityConfig: (projectId: string) => request<TraceabilityConfig>(`/api/v1/traceability-config/${encodeURIComponent(projectId)}`),
  wbsFlow: (projectId: string) => request<WbsFlow>(`/api/v1/portfolio/wbs-flow/${encodeURIComponent(projectId)}`),
  saveTraceabilityConfig: (projectId: string, groupingFields: string[], levelCaptions: string[]) => request<TraceabilityConfig>(`/api/v1/admin/traceability-config/${encodeURIComponent(projectId)}`, {method: 'PUT', body: JSON.stringify({grouping_fields: groupingFields, level_captions: levelCaptions})}),
  fields: (search = '', projectId = '') => request<Envelope<Field>>(`/api/v1/metadata/fields?limit=500&search=${encodeURIComponent(search)}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ''}`),
  gridConfig: (projectId: string) => request<GridConfig>(`/api/v1/grid-config/${encodeURIComponent(projectId)}`),
  gridFields: (projectId: string) => request<Envelope<Field>>(`/api/v1/grid-config/${encodeURIComponent(projectId)}/fields`),
  saveGridConfig: (projectId: string, optionalFields: string[]) => request<GridConfig>(`/api/v1/admin/grid-config/${encodeURIComponent(projectId)}`, {method: 'PUT', body: JSON.stringify({optional_fields: optionalFields})}),
  sprintGridConfig: (projectId: string) => request<GridConfig>(`/api/v1/sprint-grid-config/${encodeURIComponent(projectId)}`),
  saveSprintGridConfig: (projectId: string, optionalFields: string[]) => request<GridConfig>(`/api/v1/admin/sprint-grid-config/${encodeURIComponent(projectId)}`, {method: 'PUT', body: JSON.stringify({optional_fields: optionalFields})}),
  sprintViewConfig: (projectId: string) => request<SprintViewConfig>(`/api/v1/sprint-view-config/${encodeURIComponent(projectId)}`),
  saveSprintViewConfig: (projectId: string, groupingFields: string[], levelCaptions: string[]) => request<SprintViewConfig>(`/api/v1/admin/sprint-view-config/${encodeURIComponent(projectId)}`, {method: 'PUT', body: JSON.stringify({grouping_fields: groupingFields, level_captions: levelCaptions})}),
  selectProject: (id: string, selected: boolean) => request<Project>(`/api/v1/admin/projects/${encodeURIComponent(id)}`, {method: 'PUT', body: JSON.stringify({selected})}),
  deleteProjectData: (id: string) => request<{status: string; project_id: string; project_key: string; deleted: Record<string, number>}>(`/api/v1/admin/projects/${encodeURIComponent(id)}/data?confirm=${encodeURIComponent(id)}`, {method: 'DELETE'}),
  selectField: (id: string, selected: boolean) => request<Field>(`/api/v1/admin/fields/${encodeURIComponent(id)}`, {method: 'PUT', body: JSON.stringify({selected})}),
  selectFields: (fieldIds: string[], selected: boolean) => request<{updated_count: number; selected: boolean}>('/api/v1/admin/fields', {method: 'PUT', body: JSON.stringify({field_ids: fieldIds, selected})}),
  sync: ({mode, projectIds}: {mode: 'full' | 'incremental'; projectIds: string[]}) => request<SyncRun>('/api/v1/admin/sync', {method: 'POST', body: JSON.stringify({mode, project_ids: projectIds})}),
  syncStatus: () => request<{running: boolean; latest: SyncRun | null; sync_version: number}>('/api/v1/admin/sync/status'),
  roots: (projectId?: string) => request<Envelope<Issue>>(`/api/v1/hierarchy/roots?limit=25${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ''}`),
  children: (jiraIssueId: string) => request<Envelope<Issue>>(`/api/v1/issues/${encodeURIComponent(jiraIssueId)}/children?limit=200`),
  epicsByFilter: (projectIds: string[], filter: Record<string, unknown>) => request<Envelope<Issue> & {matching_work_item_count: number}>(
    `/api/v1/hierarchy/epics?limit=200&${projectIds.map(id => `project_ids=${encodeURIComponent(id)}`).join('&')}&filters=${encodeURIComponent(JSON.stringify(filter))}`),
  issuesByFilter: (projectIds: string[], filter: Record<string, unknown>) => request<Envelope<Issue>>(
    `/api/v1/issues?limit=200&${projectIds.map(id => `project_ids=${encodeURIComponent(id)}`).join('&')}&filters=${encodeURIComponent(JSON.stringify(filter))}`),
  anomalies: () => request<Envelope<{issue_id: number; type: string; details: Record<string, unknown>}>>('/api/v1/hierarchy/anomalies'),
  summary: (projectIds: string[]) => request<PortfolioSummary>(`/api/v1/portfolio/summary?${projectIds.map(id => `project_ids=${encodeURIComponent(id)}`).join('&')}`),
  groupBy: (fieldId: string, projectIds: string[], filters?: Record<string, unknown>) => request<{field_id: string; groups: {value: unknown; label: string; issue_count: number}[]; non_additive: boolean; warnings: string[]}>(
    '/api/v1/analytics/group-by', {method: 'POST', body: JSON.stringify({field_id: fieldId, project_ids: projectIds, filters, aggregation: 'count'})}),
  cardGroups: (fieldId: string, nextFieldId: string | undefined, projectIds: string[], filters?: Record<string, unknown>) => request<{field_id: string; groups: {value: unknown; label: string; issue_count: number; task_count: number; in_progress_count: number; baseline_delayed_count: number; on_track_count: number; delayed_count: number; no_due_date_count: number; baseline_due_date: string | null; latest_due_date: string | null; next_group_count: number}[]; non_additive: boolean; warnings: string[]}>(
    '/api/v1/analytics/card-groups', {method: 'POST', body: JSON.stringify({field_id: fieldId, next_field_id: nextFieldId, project_ids: projectIds, filters})}),
}
