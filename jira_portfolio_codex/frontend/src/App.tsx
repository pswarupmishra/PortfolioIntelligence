import { useEffect, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
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
    <aside><div className="brand"><img className="brand-logo" src="https://www.jswsteel.in/wp-content/themes/JSWSteel/images/JSW_Steel_Logo.svg" alt="JSW Steel"/><div>Portfolio<br/><strong>Intelligence</strong></div></div><nav>
      <NavLink to="/overview">Overview</NavLink><NavLink to="/hierarchy">Hierarchy</NavLink><NavLink to="/cards">Card view</NavLink><NavLink to="/traceability">Traceability configuration</NavLink><NavLink to="/sync">Sync monitor</NavLink><NavLink to="/configuration">Connection</NavLink>
    </nav><div className="security">Credentials stay on the server. Jira access is read-only.</div></aside>
    <main>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss">×</button></div>}
      <Routes>
        <Route path="/" element={<Navigate to="/overview" replace/>}/>
        <Route path="/overview" element={<><PageHeader eyebrow="EXECUTIVE PORTFOLIO" title="Portfolio overview" subtitle={projectLabel} configured={health.data?.jira_configured}/><Overview summary={summary.data} groups={statusGroups.data?.groups}/></>}/>
        <Route path="/hierarchy" element={<HierarchyPage projects={projects.data?.items ?? []} fields={fields.data?.items ?? []} configured={health.data?.jira_configured}/>}/>
        <Route path="/cards" element={<CardViewPage projects={projects.data?.items ?? []} fields={fields.data?.items ?? []} configured={health.data?.jira_configured}/>}/>
        <Route path="/traceability" element={<><PageHeader eyebrow="TRACEABILITY" title="Traceability configuration" subtitle="Choose a project and define its grouping hierarchy." configured={health.data?.jira_configured}/><TraceabilityConfiguration projects={projects.data?.items ?? []} fields={fields.data?.items ?? []} onNotice={setNotice}/></>}/>
        <Route path="/sync" element={<><PageHeader eyebrow="DATA OPERATIONS" title="Sync monitor" subtitle={projectLabel} configured={health.data?.jira_configured}/><section className="sync-panel"><div className="sync-heading"><div><p className="eyebrow">{projectLabel}</p><h2>Issue synchronization</h2><p>Enhanced-JQL sync with a five-minute incremental overlap and full reconciliation.</p></div><div className="actions"><button className="secondary" disabled={busy || !projectIds.length} onClick={() => sync.mutate({mode: 'incremental', projectIds})}>Incremental sync</button><button disabled={busy || !projectIds.length} onClick={() => sync.mutate({mode: 'full', projectIds})}>{sync.isPending ? 'Synchronizing…' : 'Full sync'}</button></div></div><div className="metrics"><Metric label="Last status" value={syncStatus.data?.latest?.status ?? 'Not run'}/><Metric label="Issues fetched" value={syncStatus.data?.latest?.fetched_count ?? 0}/><Metric label="Missing/tombstoned" value={syncStatus.data?.latest?.missing_count ?? 0}/><Metric label="Hierarchy anomalies" value={anomalies.data?.total_count ?? 0}/></div></section></>}/>
        <Route path="/configuration" element={<><PageHeader eyebrow="ADMINISTRATION" title="Connect your portfolio" subtitle="Discover Jira projects and fields without site-specific assumptions." configured={health.data?.jira_configured}/><section className="connection"><div><span className="step">01</span><h2>Jira Cloud connection</h2><p>Credentials are configured in the backend environment.</p></div><div className="actions"><button className="secondary" disabled={busy || !health.data?.jira_configured} onClick={() => test.mutate()}>Test connection</button><button disabled={busy || !health.data?.jira_configured} onClick={() => refresh.mutate()}>{refresh.isPending ? 'Discovering…' : 'Refresh metadata'}</button></div></section><div className="grid"><Catalog<Project> title="Projects" count={projects.data?.total_count} loading={projects.isLoading} error={projects.error} items={projects.data?.items ?? []} empty="Refresh metadata to discover projects." render={item => <><div className="identity"><b>{item.key}</b><div><strong>{item.name}</strong><small>Jira ID {item.jira_project_id}</small></div></div><Toggle checked={item.active} label={`Select ${item.name}`} onChange={selected => projectSelect.mutate({id: item.jira_project_id, selected})}/></>} /><section className="card fields"><div className="cardhead"><div><span className="step">03</span><h2>Field catalog</h2></div><span>{fields.data?.total_count ?? '—'} fields</span></div><label className="search"><span className="sr-only">Search fields</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name or Jira field ID…"/></label>{fields.isLoading ? <State text="Loading fields…"/> : fields.error ? <State text={fields.error.message}/> : fields.data?.items.length ? <div className="list">{fields.data.items.map(field => <div className="row" key={field.jira_field_id}><div><strong>{field.name}</strong><small><code>{field.jira_field_id}</code> · {fieldType(field)} {field.is_custom && '· Custom'}</small></div><Toggle checked={field.selected} label={`Select ${field.name}`} onChange={selected => fieldSelect.mutate({id: field.jira_field_id, selected})}/></div>)}</div> : <State text="No matching fields."/>}</section></div></>}/>
        <Route path="*" element={<Navigate to="/overview" replace/>}/>
      </Routes>
    </main>
  </div>
}

function PageHeader({eyebrow, title, subtitle, configured}: {eyebrow: string; title: string; subtitle: string; configured?: boolean}) { return <header><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="subtitle">{subtitle}</p></div><span className={`pill ${configured ? 'ok' : ''}`}>{configured ? 'Jira configured' : 'Setup required'}</span></header> }

function Overview({summary, groups}: {summary?: Awaited<ReturnType<typeof api.summary>>; groups?: {value: unknown; label: string; issue_count: number}[]}) { return <section className="analytics-panel"><div className="cardhead"><div><span className="step">LIVE PORTFOLIO</span><h2>Portfolio snapshot</h2></div><span>Sync version {summary?.sync_version ?? '—'}</span></div><div className="kpis">{summary?.metrics.map(metric => <div className="kpi" key={metric.metric_id}><small>{metric.metric_id.replaceAll('_', ' ')}</small><strong>{metric.unit === 'ratio' ? metric.value == null ? '—' : `${Math.round(metric.value * 100)}%` : metric.value ?? '—'}</strong><span>{metric.numerator} / {metric.denominator}</span></div>) ?? <State text="Run a sync to calculate portfolio metrics."/>}</div>{groups?.length ? <div className="distribution"><b>Status distribution</b><div>{groups.slice(0, 8).map(group => <span key={String(group.value)}>{group.label} <strong>{group.issue_count}</strong></span>)}</div></div> : null}</section> }

function groupingChoices(fields: Field[]) { return [
    {id: 'status_id', name: 'Status'}, {id: 'issue_type_id', name: 'Issue type'}, {id: 'assignee', name: 'Assignee'},
    ...fields.filter(field => field.jira_field_id === 'labels' || field.is_custom).map(field => ({id: field.jira_field_id, name: field.name})),
  ].filter((choice, index, all) => all.findIndex(item => item.id === choice.id) === index) }

function CardViewPage({projects, fields, configured}: {projects: Project[]; fields: Field[]; configured?: boolean}) {
  const fallbackProject = projects.find(project => project.active) ?? projects[0]
  const [projectId, setProjectId] = useState('')
  useEffect(() => { if (!projectId && fallbackProject) setProjectId(fallbackProject.jira_project_id) }, [projectId, fallbackProject])
  const project = projects.find(item => item.jira_project_id === projectId)
  const config = useQuery({queryKey: ['traceability-config', projectId], queryFn: () => api.traceabilityConfig(projectId), enabled: !!projectId})
  const groupingFields = config.data?.grouping_fields ?? ['labels', 'status_id', 'issue_type_id']
  return <><PageHeader eyebrow="TRACEABILITY CARDS" title="Card view" subtitle={project ? `${project.key} · ${groupingFields.length} grouping levels` : 'Select a project'} configured={configured}/><section className="project-picker"><label>Project <select aria-label="Card view project" value={projectId} onChange={event => setProjectId(event.target.value)}><option value="" disabled>Select a project</option>{projects.map(item => <option key={item.jira_project_id} value={item.jira_project_id}>{item.key} · {item.name}</option>)}</select></label><span>{config.data?.persisted ? 'Saved traceability configuration' : 'Using default grouping'}</span></section>{projectId && !config.isLoading ? <section className="card-browser" key={`${projectId}-${groupingFields.join('|')}`}><div className="cardhead"><div><span className="step">NESTED CARD PATH</span><h2>{groupingFields.map(field => groupingChoices(fields).find(choice => choice.id === field)?.name ?? field).join(' → ')}</h2></div><span>Select a card to open the next level</span></div><CardGroupingBranch projectId={projectId} fields={groupingFields} choices={groupingChoices(fields)} level={0} filters={[]}/></section> : <State text="Loading card configuration…"/>}</>
}

type CardMetricsData = {task_count: number; in_progress_count: number; baseline_delayed_count: number; on_track_count: number; delayed_count: number; no_due_date_count: number; next_group_count: number}

function CardMetrics({group, showNext}: {group: CardMetricsData; showNext: boolean}) {
  const rows = [
    {icon: '▦', label: 'Tasks', value: group.task_count, tone: 'tasks', hint: 'Bottom-level work items'},
    {icon: '◔', label: 'In progress', value: group.in_progress_count, tone: 'progress', hint: 'Tasks in Jira status category In Progress'},
    {icon: '◆', label: 'Baseline delayed', value: group.baseline_delayed_count, tone: 'baseline', hint: 'Open tasks past their first Jira due date'},
    {icon: '✓', label: 'Revised on track', value: group.on_track_count, tone: 'track', hint: 'Open tasks whose current Jira due date has not passed'},
    {icon: '!', label: 'Revised delayed', value: group.delayed_count, tone: 'delay', hint: 'Open tasks past their current Jira due date'},
    {icon: '∅', label: 'No due date', value: group.no_due_date_count, tone: 'missing', hint: 'Open tasks without a Jira due date'},
    ...(showNext ? [{icon: '⇲', label: 'Next-level groups', value: group.next_group_count, tone: 'groups', hint: 'Distinct groups at the next configured level'}] : []),
  ]
  return <table className="card-metrics" aria-label="Card metrics"><tbody>{rows.map(row => <tr className={`metric-${row.tone}`} title={row.hint} key={row.label}><td><span className="metric-icon" aria-hidden="true">{row.icon}</span>{row.label}</td><td>{row.value}</td></tr>)}</tbody></table>
}

function CardGroupingBranch({projectId, fields, choices, level, filters}: {projectId: string; fields: string[]; choices: {id: string; name: string}[]; level: number; filters: Record<string, unknown>[]}) {
  const [selected, setSelected] = useState<Group | null>(null)
  const field = fields[level]
  const filter = combineFilters(filters)
  const nextField = fields[level + 1]
  const groups = useQuery({queryKey: ['card-groups', projectId, level, field, nextField, filter], queryFn: () => api.cardGroups(field, nextField, [projectId], filter ?? undefined)})
  const fieldName = choices.find(choice => choice.id === field)?.name ?? field
  if (groups.isLoading) return <State text={`Loading ${fieldName} cards…`}/>
  if (groups.error) return <State text={groups.error.message}/>
  return <div className="card-level"><div className="card-level-title"><span>Level {level + 1}</span><strong>{fieldName}</strong></div><div className="trace-card-grid">{groups.data?.groups.map(group => { const open = selected?.value === group.value; const muted = selected !== null && !open; const empty = group.task_count === 0; const nextFilters = [...filters, groupFilter(field, group)]; return <article className={`trace-card ${open ? 'open' : ''} ${muted ? 'muted' : ''} ${empty ? 'empty-card' : ''}`} key={`${field}-${String(group.value)}`}><button className="trace-card-button" onClick={() => setSelected(open ? null : group)} aria-expanded={open}><span>{group.label}</span><strong>{group.issue_count}</strong><CardMetrics group={group} showNext={Boolean(nextField)}/><small>{level === fields.length - 1 ? 'View work items' : `Open level ${level + 2}`}</small></button>{open && <div className="trace-card-children">{level === fields.length - 1 ? <CardResults projectId={projectId} filter={combineFilters(nextFilters)!} direct={fields.includes('issue_type_id')} groupLabel={group.label}/> : <CardGroupingBranch projectId={projectId} fields={fields} choices={choices} level={level + 1} filters={nextFilters}/>}</div>}</article>})}</div>{groups.data?.non_additive && <p className="group-warning">Multi-value groups can overlap.</p>}</div>
}

function CardResults({projectId, filter, direct, groupLabel}: {projectId: string; filter: Record<string, unknown>; direct: boolean; groupLabel: string}) {
  type SortField = 'key' | 'summary' | 'type' | 'baseline' | 'revised' | 'status'
  const [sortField, setSortField] = useState<SortField>('key')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const epics = useQuery({queryKey: ['card-result-epics', projectId, filter], queryFn: () => api.epicsByFilter([projectId], filter), enabled: !direct})
  const issues = useQuery({queryKey: ['card-result-issues', projectId, filter], queryFn: () => api.issuesByFilter([projectId], filter), enabled: direct})
  const result = direct ? issues : epics
  const changeSort = (field: SortField) => { if (sortField === field) setSortDirection(value => value === 'asc' ? 'desc' : 'asc'); else { setSortField(field); setSortDirection('asc') } }
  const valueFor = (issue: Issue) => ({key: issue.issue_key, summary: issue.summary, type: issue.issue_type.name ?? '', baseline: issue.baseline_due_at ?? '', revised: issue.due_at ?? '', status: issue.status.name ?? ''})[sortField]
  const sortedItems = [...(result.data?.items ?? [])].sort((left, right) => valueFor(left).localeCompare(valueFor(right), undefined, {numeric: true}) * (sortDirection === 'asc' ? 1 : -1))
  if (result.isLoading) return <State text="Loading work items…"/>
  if (result.error) return <State text={result.error.message}/>
  const sortButton = (field: SortField, label: string) => <button className={sortField === field ? 'sorted' : ''} onClick={() => changeSort(field)}>{label}<span aria-hidden="true">{sortField === field ? sortDirection === 'asc' ? '▲' : '▼' : '↕'}</span></button>
  return <div className="card-result-grid"><div className="result-head"><strong>{groupLabel}</strong><span>{result.data?.total_count ?? 0} results</span></div>{sortedItems.length ? <div className="issue-list"><div className="issue-grid-head">{sortButton('key', 'Key')}{sortButton('summary', 'Summary')}{sortButton('type', 'Issue type')}{sortButton('baseline', 'Baseline due')}{sortButton('revised', 'Revised due')}{sortButton('status', 'Status')}</div>{sortedItems.map(issue => <div className="issue-row card-issue-row" key={issue.jira_issue_id}><b>{issue.issue_key}</b><span>{issue.summary}</span><small>{issue.issue_type.name ?? 'Unknown type'}</small><DueDate value={issue.baseline_due_at}/><DueDate value={issue.due_at} revised/><StatusBadge name={issue.status.name} category={issue.status.category_key}/></div>)}</div> : <State text="No matching work items."/>}</div>
}

function DueDate({value, revised = false}: {value?: string | null; revised?: boolean}) {
  if (!value) return <span className="due-date missing"><i aria-hidden="true">—</i>Not set</span>
  const display = new Intl.DateTimeFormat(undefined, {day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC'}).format(new Date(value))
  return <span className={`due-date ${revised ? 'revised' : 'baseline'}`}><i aria-hidden="true">{revised ? '↻' : '◆'}</i>{display}</span>
}

function StatusBadge({name, category}: {name?: string; category?: string}) {
  const tone = category === 'done' ? 'done' : category === 'indeterminate' ? 'progress' : 'todo'
  const icon = tone === 'done' ? '✓' : tone === 'progress' ? '◔' : '○'
  return <span className={`status-badge status-${tone}`}><i aria-hidden="true">{icon}</i>{name ?? 'Unknown status'}</span>
}

function HierarchyPage({projects, fields, configured}: {projects: Project[]; fields: Field[]; configured?: boolean}) {
  const fallbackProject = projects.find(project => project.active) ?? projects[0]
  const [projectId, setProjectId] = useState('')
  useEffect(() => { if (!projectId && fallbackProject) setProjectId(fallbackProject.jira_project_id) }, [projectId, fallbackProject])
  const project = projects.find(item => item.jira_project_id === projectId)
  const config = useQuery({queryKey: ['traceability-config', projectId], queryFn: () => api.traceabilityConfig(projectId), enabled: !!projectId})
  const roots = useQuery({queryKey: ['roots', projectId], queryFn: () => api.roots(projectId), enabled: !!projectId})
  const configuredFields = config.data?.grouping_fields ?? ['labels', 'status_id', 'issue_type_id']
  return <><PageHeader eyebrow="WORK BREAKDOWN" title="Issue hierarchy" subtitle={project ? `${project.key} · Jira ID ${project.jira_project_id} · Parent links from Jira` : 'Select a project'} configured={configured}/><section className="project-picker"><label>Project <select aria-label="Hierarchy project" value={projectId} onChange={event => setProjectId(event.target.value)}><option value="" disabled>Select a project</option>{projects.map(item => <option key={item.jira_project_id} value={item.jira_project_id}>{item.key} · {item.name}</option>)}</select></label><span>{config.data?.persisted ? `${configuredFields.length} saved grouping levels` : 'Using default grouping'}</span></section>{projectId && !config.isLoading ? <HierarchyView key={`${projectId}-${configuredFields.join('|')}`} roots={roots.data?.items ?? []} loading={roots.isLoading} fields={fields} projectIds={[projectId]} initialFields={configuredFields}/> : <State text="Loading traceability configuration…"/>}</>
}

function TraceabilityConfiguration({projects, fields, onNotice}: {projects: Project[]; fields: Field[]; onNotice: (message: string) => void}) {
  const queryClient = useQueryClient()
  const fallbackProject = projects.find(project => project.active) ?? projects[0]
  const [projectId, setProjectId] = useState('')
  const [levels, setLevels] = useState<string[]>(['labels', 'status_id', 'issue_type_id'])
  useEffect(() => { if (!projectId && fallbackProject) setProjectId(fallbackProject.jira_project_id) }, [projectId, fallbackProject])
  const config = useQuery({queryKey: ['traceability-config', projectId], queryFn: () => api.traceabilityConfig(projectId), enabled: !!projectId})
  useEffect(() => { if (config.data) setLevels(config.data.grouping_fields) }, [config.data])
  const save = useMutation({mutationFn: () => api.saveTraceabilityConfig(projectId, levels), onSuccess: data => {queryClient.setQueryData(['traceability-config', projectId], data); onNotice(`Saved ${levels.length} traceability levels for ${projects.find(project => project.jira_project_id === projectId)?.key ?? projectId}.`)}, onError: error => onNotice(error.message)})
  const choices = groupingChoices(fields)
  const addLevel = () => { const next = choices.find(choice => !levels.includes(choice.id)); if (next) setLevels(current => [...current, next.id]) }
  return <section className="trace-config"><div className="trace-project"><label>Project<select aria-label="Traceability project" value={projectId} onChange={event => setProjectId(event.target.value)}><option value="" disabled>Select a project</option>{projects.map(project => <option key={project.jira_project_id} value={project.jira_project_id}>{project.key} · {project.name}</option>)}</select></label><p>The saved order becomes the hierarchy grouping shown on initial load.</p></div><div className="level-editor">{levels.map((field, index) => <div className="level-edit" key={index}><span>{index + 1}</span><label><span className="sr-only">Grouping field for level {index + 1}</span><select value={field} onChange={event => setLevels(current => current.map((item, position) => position === index ? event.target.value : item))}>{choices.map(choice => <option key={choice.id} value={choice.id}>{choice.name}</option>)}</select></label>{levels.length > 1 && <button className="secondary" aria-label={`Remove level ${index + 1}`} onClick={() => setLevels(current => current.filter((_, position) => position !== index))}>Remove</button>}</div>)}</div><div className="trace-actions"><button className="secondary" disabled={levels.length >= choices.length} onClick={addLevel}>Add grouping level</button><button disabled={!projectId || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save configuration'}</button></div></section>
}

function HierarchyView({roots, loading, fields, projectIds, initialFields}: {roots: Issue[]; loading: boolean; fields: Field[]; projectIds: string[]; initialFields: string[]}) {
  const choices = groupingChoices(fields)
  const [groupFields, setGroupFields] = useState(initialFields)
  const [selectedGroups, setSelectedGroups] = useState<Array<{value: unknown; label: string} | null>>(() => initialFields.map(() => null))
  const levelFilters = selectedGroups.map((group, index) => group ? groupFilter(groupFields[index], group) : null)
  const filtersBeforeLevel = groupFields.map((_, index) => combineFilters(levelFilters.slice(0, index)))
  const finalFilter = combineFilters(selectedGroups.map((group, index) => group ? groupFilter(groupFields[index], group) : null))
  const groupQueries = useQueries({queries: groupFields.map((field, index) => ({queryKey: ['hierarchy-groups', index, field, filtersBeforeLevel[index], projectIds], queryFn: () => api.groupBy(field, projectIds, filtersBeforeLevel[index] ?? undefined), enabled: projectIds.length > 0 && (index === 0 || !!selectedGroups[index - 1])}))})
  const deepestLevel = selectedGroups.reduce((last, group, index) => group ? index : last, -1)
  const showDirectIssueType = deepestLevel >= 0 && groupFields[deepestLevel] === 'issue_type_id'
  const epicMatches = useQuery({queryKey: ['group-epics', finalFilter, projectIds], queryFn: () => api.epicsByFilter(projectIds, finalFilter!), enabled: !!finalFilter && !showDirectIssueType && projectIds.length > 0})
  const directMatches = useQuery({queryKey: ['group-direct-items', finalFilter, projectIds], queryFn: () => api.issuesByFilter(projectIds, finalFilter!), enabled: !!finalFilter && showDirectIssueType && projectIds.length > 0})
  const matches = showDirectIssueType ? directMatches : epicMatches
  const changeField = (level: number, value: string) => { setGroupFields(current => current.map((field, index) => index === level ? value : field)); setSelectedGroups(current => current.map((group, index) => index >= level ? null : group)) }
  const selectGroup = (level: number, group: {value: unknown; label: string}) => setSelectedGroups(current => current.map((selected, index) => index === level ? group : index > level ? null : selected))
  return <>
    <section className="grouping-card"><div className="cardhead"><div><span className="step">{groupFields.length}-LEVEL GROUPING</span><h2>Drill down through Jira fields</h2></div><span>{groupFields.map(field => choices.find(choice => choice.id === field)?.name ?? field).join(' → ')}</span></div>
      {groupFields.map((field, index) => <GroupingLevel key={`${index}-${field}`} level={index} field={field} choices={choices} selected={selectedGroups[index]} query={groupQueries[index]} enabled={index === 0 || !!selectedGroups[index - 1]} onFieldChange={changeField} onSelect={selectGroup}/>)}
      {finalFilter && <div className="group-results"><div className="result-head"><strong>{selectedGroups.filter(Boolean).map(group => group?.label).join(' / ')}</strong><span>{matches.data ? showDirectIssueType ? `${matches.data.total_count} matching ${selectedGroups[deepestLevel]?.label ?? 'work items'}` : `${matches.data.total_count} epics · ${'matching_work_item_count' in matches.data ? matches.data.matching_work_item_count : matches.data.total_count} matching work items` : 'Loading results…'}</span></div>{matches.isLoading ? <State text={showDirectIssueType ? 'Loading matching work items…' : 'Finding epic ancestors…'}/> : matches.data?.items.length ? <div className="group-epics">{matches.data.items.map(issue => <TreeNode key={issue.jira_issue_id} issue={issue} depth={0}/>)}</div> : <State text="No matching work items were found for this grouping."/>}</div>}
    </section>
    <section className="hierarchy-card"><div className="cardhead"><div><span className="step">EXPANDABLE TREE</span><h2>Roots and descendants</h2></div><span>{roots.length} loaded roots</span></div>{loading ? <State text="Loading hierarchy…"/> : roots.length ? <div className="tree">{roots.map(issue => <TreeNode key={issue.jira_issue_id} issue={issue} depth={0}/>)}</div> : <State text="Run a full sync to populate the hierarchy."/>}</section>
  </>
}

type Group = {value: unknown; label: string; issue_count: number; task_count?: number; in_progress_count?: number; delayed_count?: number; next_group_count?: number}
type GroupQuery = {data?: {groups: Group[]; non_additive: boolean}; isLoading: boolean; error: Error | null}

function groupFilter(fieldId: string, group: {value: unknown}) { return {field_id: fieldId, operator: group.value == null ? 'is_null' : 'eq', value: group.value == null ? true : group.value} }
function combineFilters(filters: Array<Record<string, unknown> | null>) { const active = filters.filter((filter): filter is Record<string, unknown> => !!filter); return active.length === 0 ? null : active.length === 1 ? active[0] : {and: active} }

function GroupingLevel({level, field, choices, selected, query, enabled, onFieldChange, onSelect}: {level: number; field: string; choices: {id: string; name: string}[]; selected: {value: unknown; label: string} | null; query: GroupQuery; enabled: boolean; onFieldChange: (level: number, value: string) => void; onSelect: (level: number, group: Group) => void}) {
  return <div className={`group-level ${enabled ? '' : 'disabled'}`}><div className="group-level-head"><strong>Level {level + 1}</strong><label className="group-select">Group by <select aria-label={`Grouping level ${level + 1}`} value={field} disabled={!enabled} onChange={event => onFieldChange(level, event.target.value)}>{choices.map(choice => <option key={choice.id} value={choice.id}>{choice.name}</option>)}</select></label></div>{!enabled ? <p>Select a value in Level {level} to continue.</p> : query.isLoading ? <State text="Building groups…"/> : query.error ? <State text={query.error.message}/> : <div className="group-chips">{query.data?.groups.map(group => <button key={`${field}-${String(group.value)}`} className={selected?.value === group.value ? 'group-chip selected' : 'group-chip'} onClick={() => onSelect(level, group)}><span>{group.label}</span><strong>{group.issue_count}</strong></button>)}</div>}{query.data?.non_additive && enabled && <p className="group-warning">Multi-value groups can overlap.</p>}</div>
}

function TreeNode({issue, depth}: {issue: Issue; depth: number}) { const [expanded, setExpanded] = useState(false); const children = useQuery({queryKey: ['children', issue.jira_issue_id], queryFn: () => api.children(issue.jira_issue_id), enabled: expanded}); return <div className="tree-branch"><button className="tree-row" style={{paddingLeft: 18 + depth * 24}} onClick={() => setExpanded(value => !value)} aria-expanded={expanded}><span className="chevron">{expanded ? '−' : '+'}</span><b>{issue.issue_key}</b><span>{issue.summary}</span><small>{issue.issue_type.name ?? 'Unknown type'} · {issue.status.name ?? 'Unknown status'}</small></button>{expanded && (children.isLoading ? <div className="tree-loading">Loading children…</div> : children.data?.items.length ? children.data.items.map(child => <TreeNode key={child.jira_issue_id} issue={child} depth={depth + 1}/>) : <div className="tree-empty" style={{paddingLeft: 54 + depth * 24}}>No direct children</div>)}</div> }

function Metric({label, value}: {label: string; value: string | number}) { return <div className="metric"><small>{label}</small><strong>{value}</strong></div> }

function fieldType(field: Field) { return String(field.schema_json.type ?? field.schema_json.custom ?? 'unknown type') }
function State({text}: {text: string}) { return <div className="state">{text}</div> }
function Catalog<T>({title, count, items, loading, error, empty, render}: {title: string; count?: number; items: T[]; loading: boolean; error: Error | null; empty: string; render: (item: T) => React.ReactNode}) {
  return <section className="card"><div className="cardhead"><div><span className="step">02</span><h2>{title}</h2></div><span>{count ?? '—'} available</span></div>{loading ? <State text={`Loading ${title.toLowerCase()}…`}/> : error ? <State text={error.message}/> : items.length ? <div className="list">{items.map((item, i) => <div className="row" key={i}>{render(item)}</div>)}</div> : <State text={empty}/>}</section>
}
