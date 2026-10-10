import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api, type Field, type Issue, type Project } from './api'

function Toggle({checked, label, onChange}: {checked: boolean; label: string; onChange: (value: boolean) => void}) {
  return <label className="toggle"><input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} /><span aria-hidden="true" /> <span className="sr-only">{label}</span></label>
}

export default function App() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [notice, setNotice] = useState('')
  const health = useQuery({queryKey: ['health'], queryFn: api.health})
  const projects = useQuery({queryKey: ['projects'], queryFn: api.projects})
  const activeProjects = projects.data?.items.filter(project => project.active) ?? []
  const fields = useQuery({queryKey: ['fields', search], queryFn: () => api.fields(search)})
  const syncStatus = useQuery({queryKey: ['sync-status'], queryFn: api.syncStatus, refetchInterval: 15_000})
  const roots = useQuery({queryKey: ['roots', activeProjects[0]?.jira_project_id], queryFn: () => api.roots(activeProjects.length === 1 ? activeProjects[0].jira_project_id : undefined)})
  const anomalies = useQuery({queryKey: ['anomalies'], queryFn: api.anomalies})
  const summary = useQuery({queryKey: ['summary', activeProjects.map(project => project.jira_project_id)], queryFn: () => api.summary(activeProjects.map(project => project.jira_project_id)), enabled: activeProjects.length > 0})
  const statusGroups = useQuery({queryKey: ['status-groups', activeProjects.map(project => project.jira_project_id)], queryFn: () => api.groupBy('status_id', activeProjects.map(project => project.jira_project_id)), enabled: activeProjects.length > 0})
  const test = useMutation({mutationFn: api.testConnection, onSuccess: data => setNotice(`Connected as ${data.account.display_name ?? data.account.account_id ?? 'Jira user'}.`), onError: e => setNotice(e.message)})
  const refresh = useMutation({mutationFn: api.refresh, onSuccess: data => {setNotice(`Metadata refreshed: ${data.counts.projects ?? 0} projects and ${data.counts.fields ?? 0} fields.`); queryClient.invalidateQueries()}, onError: e => setNotice(e.message)})
  const projectSelect = useMutation({mutationFn: ({id, selected}: {id: string; selected: boolean}) => api.selectProject(id, selected), onSuccess: () => queryClient.invalidateQueries({queryKey: ['projects']})})
  const fieldSelect = useMutation({mutationFn: ({id, selected}: {id: string; selected: boolean}) => api.selectField(id, selected), onSuccess: () => queryClient.invalidateQueries({queryKey: ['fields']})})
  const sync = useMutation({mutationFn: api.sync, onSuccess: data => {setNotice(`Sync completed: ${data.fetched_count} issues, ${data.anomaly_count} hierarchy anomalies.`); queryClient.invalidateQueries()}, onError: e => setNotice(e.message)})
  const busy = test.isPending || refresh.isPending || sync.isPending

  const projectIds = activeProjects.map(project => project.jira_project_id)
  const projectLabel = activeProjects.length === 1 ? `${activeProjects[0].key} · Jira ID ${activeProjects[0].jira_project_id}` : `${activeProjects.length} active projects`

  return <div className="shell">
    <aside><div className="brand"><span className="mark">PI</span><div>Portfolio<br/><strong>Intelligence</strong></div></div><nav>
      <NavLink to="/overview">Overview</NavLink><NavLink to="/hierarchy">Hierarchy</NavLink><NavLink to="/sync">Sync monitor</NavLink><NavLink to="/configuration">Configuration</NavLink>
    </nav><div className="security">Credentials stay on the server. Jira access is read-only.</div></aside>
    <main>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss">×</button></div>}
      <Routes>
        <Route path="/" element={<Navigate to="/overview" replace/>}/>
        <Route path="/overview" element={<><PageHeader eyebrow="EXECUTIVE PORTFOLIO" title="Portfolio overview" subtitle={projectLabel} configured={health.data?.jira_configured}/><Overview summary={summary.data} groups={statusGroups.data?.groups}/></>}/>
        <Route path="/hierarchy" element={<><PageHeader eyebrow="WORK BREAKDOWN" title="Issue hierarchy" subtitle={`${projectLabel} · Parent links from Jira`} configured={health.data?.jira_configured}/><HierarchyView roots={roots.data?.items ?? []} loading={roots.isLoading} fields={fields.data?.items ?? []} projectIds={projectIds}/></>}/>
        <Route path="/sync" element={<><PageHeader eyebrow="DATA OPERATIONS" title="Sync monitor" subtitle={projectLabel} configured={health.data?.jira_configured}/><section className="sync-panel"><div className="sync-heading"><div><p className="eyebrow">{projectLabel}</p><h2>Issue synchronization</h2><p>Enhanced-JQL sync with a five-minute incremental overlap and full reconciliation.</p></div><div className="actions"><button className="secondary" disabled={busy || !projectIds.length} onClick={() => sync.mutate({mode: 'incremental', projectIds})}>Incremental sync</button><button disabled={busy || !projectIds.length} onClick={() => sync.mutate({mode: 'full', projectIds})}>{sync.isPending ? 'Synchronizing…' : 'Full sync'}</button></div></div><div className="metrics"><Metric label="Last status" value={syncStatus.data?.latest?.status ?? 'Not run'}/><Metric label="Issues fetched" value={syncStatus.data?.latest?.fetched_count ?? 0}/><Metric label="Missing/tombstoned" value={syncStatus.data?.latest?.missing_count ?? 0}/><Metric label="Hierarchy anomalies" value={anomalies.data?.total_count ?? 0}/></div></section></>}/>
        <Route path="/configuration" element={<><PageHeader eyebrow="ADMINISTRATION" title="Connect your portfolio" subtitle="Discover Jira projects and fields without site-specific assumptions." configured={health.data?.jira_configured}/><section className="connection"><div><span className="step">01</span><h2>Jira Cloud connection</h2><p>Credentials are configured in the backend environment.</p></div><div className="actions"><button className="secondary" disabled={busy || !health.data?.jira_configured} onClick={() => test.mutate()}>Test connection</button><button disabled={busy || !health.data?.jira_configured} onClick={() => refresh.mutate()}>{refresh.isPending ? 'Discovering…' : 'Refresh metadata'}</button></div></section><div className="grid"><Catalog<Project> title="Projects" count={projects.data?.total_count} loading={projects.isLoading} error={projects.error} items={projects.data?.items ?? []} empty="Refresh metadata to discover projects." render={item => <><div className="identity"><b>{item.key}</b><div><strong>{item.name}</strong><small>Jira ID {item.jira_project_id}</small></div></div><Toggle checked={item.active} label={`Select ${item.name}`} onChange={selected => projectSelect.mutate({id: item.jira_project_id, selected})}/></>} /><section className="card fields"><div className="cardhead"><div><span className="step">03</span><h2>Field catalog</h2></div><span>{fields.data?.total_count ?? '—'} fields</span></div><label className="search"><span className="sr-only">Search fields</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name or Jira field ID…"/></label>{fields.isLoading ? <State text="Loading fields…"/> : fields.error ? <State text={fields.error.message}/> : fields.data?.items.length ? <div className="list">{fields.data.items.map(field => <div className="row" key={field.jira_field_id}><div><strong>{field.name}</strong><small><code>{field.jira_field_id}</code> · {fieldType(field)} {field.is_custom && '· Custom'}</small></div><Toggle checked={field.selected} label={`Select ${field.name}`} onChange={selected => fieldSelect.mutate({id: field.jira_field_id, selected})}/></div>)}</div> : <State text="No matching fields."/>}</section></div></>}/>
        <Route path="*" element={<Navigate to="/overview" replace/>}/>
      </Routes>
    </main>
  </div>
}

function PageHeader({eyebrow, title, subtitle, configured}: {eyebrow: string; title: string; subtitle: string; configured?: boolean}) { return <header><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="subtitle">{subtitle}</p></div><span className={`pill ${configured ? 'ok' : ''}`}>{configured ? 'Jira configured' : 'Setup required'}</span></header> }

function Overview({summary, groups}: {summary?: Awaited<ReturnType<typeof api.summary>>; groups?: {value: unknown; label: string; issue_count: number}[]}) { return <section className="analytics-panel"><div className="cardhead"><div><span className="step">LIVE PORTFOLIO</span><h2>Portfolio snapshot</h2></div><span>Sync version {summary?.sync_version ?? '—'}</span></div><div className="kpis">{summary?.metrics.map(metric => <div className="kpi" key={metric.metric_id}><small>{metric.metric_id.replaceAll('_', ' ')}</small><strong>{metric.unit === 'ratio' ? metric.value == null ? '—' : `${Math.round(metric.value * 100)}%` : metric.value ?? '—'}</strong><span>{metric.numerator} / {metric.denominator}</span></div>) ?? <State text="Run a sync to calculate portfolio metrics."/>}</div>{groups?.length ? <div className="distribution"><b>Status distribution</b><div>{groups.slice(0, 8).map(group => <span key={String(group.value)}>{group.label} <strong>{group.issue_count}</strong></span>)}</div></div> : null}</section> }

function HierarchyView({roots, loading, fields, projectIds}: {roots: Issue[]; loading: boolean; fields: Field[]; projectIds: string[]}) {
  const choices = [
    {id: 'status_id', name: 'Status'}, {id: 'issue_type_id', name: 'Issue type'}, {id: 'assignee', name: 'Assignee'},
    ...fields.filter(field => field.jira_field_id === 'labels' || field.is_custom).map(field => ({id: field.jira_field_id, name: field.name})),
  ].filter((choice, index, all) => all.findIndex(item => item.id === choice.id) === index)
  const [groupField, setGroupField] = useState('labels')
  const [selectedGroup, setSelectedGroup] = useState<{value: unknown; label: string} | null>(null)
  const groups = useQuery({queryKey: ['hierarchy-groups', groupField, projectIds], queryFn: () => api.groupBy(groupField, projectIds), enabled: projectIds.length > 0})
  const filter = selectedGroup ? {field_id: groupField, operator: selectedGroup.value == null ? 'is_null' : 'eq', value: selectedGroup.value == null ? true : selectedGroup.value} : null
  const matches = useQuery({queryKey: ['group-issues', groupField, selectedGroup?.value, projectIds], queryFn: () => api.issuesByFilter(projectIds, filter!), enabled: !!filter && projectIds.length > 0})
  const changeField = (value: string) => { setGroupField(value); setSelectedGroup(null) }
  return <>
    <section className="grouping-card"><div className="cardhead"><div><span className="step">DYNAMIC GROUPING</span><h2>Explore work by Jira field</h2></div><label className="group-select">Group by <select aria-label="Group hierarchy by" value={groupField} onChange={event => changeField(event.target.value)}>{choices.map(choice => <option key={choice.id} value={choice.id}>{choice.name}</option>)}</select></label></div>
      {groups.isLoading ? <State text="Building groups…"/> : groups.error ? <State text={groups.error.message}/> : <div className="group-chips">{groups.data?.groups.map(group => <button key={`${groupField}-${String(group.value)}`} className={selectedGroup?.value === group.value ? 'group-chip selected' : 'group-chip'} onClick={() => setSelectedGroup({value: group.value, label: group.label})}><span>{group.label}</span><strong>{group.issue_count}</strong></button>)}</div>}
      {groups.data?.non_additive && <p className="group-warning">Multi-value fields such as labels can place one task in several groups, so group totals may overlap.</p>}
      {selectedGroup && <div className="group-results"><div className="result-head"><strong>{selectedGroup.label}</strong><span>{matches.data?.total_count ?? '…'} matching work items</span></div>{matches.isLoading ? <State text="Loading matching tasks…"/> : matches.data?.items.length ? <div className="issue-list">{matches.data.items.map(issue => <div className="issue-row" key={issue.jira_issue_id}><b>{issue.issue_key}</b><span>{issue.summary}</span><small>{issue.issue_type.name ?? 'Unknown type'} · {issue.status.name ?? 'Unknown status'}</small></div>)}</div> : <State text="No matching tasks."/>}</div>}
    </section>
    <section className="hierarchy-card"><div className="cardhead"><div><span className="step">EXPANDABLE TREE</span><h2>Roots and descendants</h2></div><span>{roots.length} loaded roots</span></div>{loading ? <State text="Loading hierarchy…"/> : roots.length ? <div className="tree">{roots.map(issue => <TreeNode key={issue.jira_issue_id} issue={issue} depth={0}/>)}</div> : <State text="Run a full sync to populate the hierarchy."/>}</section>
  </>
}

function TreeNode({issue, depth}: {issue: Issue; depth: number}) { const [expanded, setExpanded] = useState(false); const children = useQuery({queryKey: ['children', issue.jira_issue_id], queryFn: () => api.children(issue.jira_issue_id), enabled: expanded}); return <div className="tree-branch"><button className="tree-row" style={{paddingLeft: 18 + depth * 24}} onClick={() => setExpanded(value => !value)} aria-expanded={expanded}><span className="chevron">{expanded ? '−' : '+'}</span><b>{issue.issue_key}</b><span>{issue.summary}</span><small>{issue.issue_type.name ?? 'Unknown type'} · {issue.status.name ?? 'Unknown status'}</small></button>{expanded && (children.isLoading ? <div className="tree-loading">Loading children…</div> : children.data?.items.length ? children.data.items.map(child => <TreeNode key={child.jira_issue_id} issue={child} depth={depth + 1}/>) : <div className="tree-empty" style={{paddingLeft: 54 + depth * 24}}>No direct children</div>)}</div> }

function Metric({label, value}: {label: string; value: string | number}) { return <div className="metric"><small>{label}</small><strong>{value}</strong></div> }

function fieldType(field: Field) { return String(field.schema_json.type ?? field.schema_json.custom ?? 'unknown type') }
function State({text}: {text: string}) { return <div className="state">{text}</div> }
function Catalog<T>({title, count, items, loading, error, empty, render}: {title: string; count?: number; items: T[]; loading: boolean; error: Error | null; empty: string; render: (item: T) => React.ReactNode}) {
  return <section className="card"><div className="cardhead"><div><span className="step">02</span><h2>{title}</h2></div><span>{count ?? '—'} available</span></div>{loading ? <State text={`Loading ${title.toLowerCase()}…`}/> : error ? <State text={error.message}/> : items.length ? <div className="list">{items.map((item, i) => <div className="row" key={i}>{render(item)}</div>)}</div> : <State text={empty}/>}</section>
}
