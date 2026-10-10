const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Envelope<T> = { items: T[]; next_cursor: string | null; total_count: number; sync_version: number }
export type Project = { jira_project_id: string; key: string; name: string; active: boolean; updated_at: string }
export type Field = { jira_field_id: string; name: string; schema_json: Record<string, unknown>; is_custom: boolean; searchable: boolean; selected: boolean; last_seen_at: string }
export type Connection = { connected: boolean; base_url: string; account: { account_id?: string; display_name?: string } }
export type SyncRun = { id: number; status: string; mode: string; projects: string[]; started_at: string; finished_at?: string; fetched_count: number; upserted_count: number; missing_count: number; anomaly_count: number; watermark_after?: string; error?: Record<string, unknown> }
export type Issue = { jira_issue_id: string; issue_key: string; project_id: string; summary: string; parent_jira_issue_id?: string; issue_type: {id?: string; name?: string; hierarchy_level?: number}; status: {id?: string; name?: string; category_key?: string}; updated_at?: string }
export type PortfolioMetric = {metric_id: string; value: number | null; numerator: number; denominator: number; unit: string; as_of?: string; warnings: string[]}
export type PortfolioSummary = {metrics: PortfolioMetric[]; scope_count: number; null_counts: Record<string, number>; sync_version: number}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers: {'Content-Type': 'application/json', 'X-App-Role': 'admin', ...init?.headers} })
  const body = await response.json()
  if (!response.ok) throw new Error(body.message ?? body.detail ?? 'Request failed')
  return body as T
}

export const api = {
  health: () => request<{status: string; jira_configured: boolean}>('/api/v1/health/ready'),
  testConnection: () => request<Connection>('/api/v1/jira/test-connection', {method: 'POST'}),
  refresh: () => request<{status: string; counts: Record<string, number>; warnings: unknown[]}>('/api/v1/admin/metadata/refresh', {method: 'POST'}),
  projects: () => request<Envelope<Project>>('/api/v1/jira/projects'),
  fields: (search = '') => request<Envelope<Field>>(`/api/v1/metadata/fields?limit=500&search=${encodeURIComponent(search)}`),
  selectProject: (id: string, selected: boolean) => request<Project>(`/api/v1/admin/projects/${encodeURIComponent(id)}`, {method: 'PUT', body: JSON.stringify({selected})}),
  selectField: (id: string, selected: boolean) => request<Field>(`/api/v1/admin/fields/${encodeURIComponent(id)}`, {method: 'PUT', body: JSON.stringify({selected})}),
  sync: ({mode, projectIds}: {mode: 'full' | 'incremental'; projectIds: string[]}) => request<SyncRun>('/api/v1/admin/sync', {method: 'POST', body: JSON.stringify({mode, project_ids: projectIds})}),
  syncStatus: () => request<{running: boolean; latest: SyncRun | null; sync_version: number}>('/api/v1/admin/sync/status'),
  roots: (projectId?: string) => request<Envelope<Issue>>(`/api/v1/hierarchy/roots?limit=25${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ''}`),
  children: (jiraIssueId: string) => request<Envelope<Issue>>(`/api/v1/issues/${encodeURIComponent(jiraIssueId)}/children?limit=200`),
  issuesByFilter: (projectIds: string[], filter: Record<string, unknown>) => request<Envelope<Issue>>(
    `/api/v1/issues?limit=200&${projectIds.map(id => `project_ids=${encodeURIComponent(id)}`).join('&')}&filters=${encodeURIComponent(JSON.stringify(filter))}`),
  anomalies: () => request<Envelope<{issue_id: number; type: string; details: Record<string, unknown>}>>('/api/v1/hierarchy/anomalies'),
  summary: (projectIds: string[]) => request<PortfolioSummary>(`/api/v1/portfolio/summary?${projectIds.map(id => `project_ids=${encodeURIComponent(id)}`).join('&')}`),
  groupBy: (fieldId: string, projectIds: string[]) => request<{field_id: string; groups: {value: unknown; label: string; issue_count: number}[]; non_additive: boolean; warnings: string[]}>(
    '/api/v1/analytics/group-by', {method: 'POST', body: JSON.stringify({field_id: fieldId, project_ids: projectIds, aggregation: 'count'})}),
}
