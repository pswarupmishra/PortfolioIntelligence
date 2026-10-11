import { useEffect, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api, type Field, type Issue, type LiveIssueMetadata, type Project, type WbsFlow } from './api'

function Toggle({checked, label, onChange}: {checked: boolean; label: string; onChange: (value: boolean) => void}) {
  return <label className="toggle"><input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} /><span aria-hidden="true" /> <span className="sr-only">{label}</span></label>
}

export default function App() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [notice, setNotice] = useState('')
  const [configurationOpen, setConfigurationOpen] = useState(true)
  const [portfolioSyncOpen, setPortfolioSyncOpen] = useState(true)
  const [portfolioViewOpen, setPortfolioViewOpen] = useState(true)
  const [appSettingOpen, setAppSettingOpen] = useState(true)
  const [executionViewOpen, setExecutionViewOpen] = useState(true)
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
      <NavLink to="/overview">Overview</NavLink><div className="nav-group"><button className="nav-parent" onClick={() => setPortfolioViewOpen(value => !value)} aria-expanded={portfolioViewOpen}><span>Portfolio View</span><i aria-hidden="true">{portfolioViewOpen ? '−' : '+'}</i></button>{portfolioViewOpen && <div className="nav-children"><NavLink to="/hierarchy">Hierarchy</NavLink><NavLink to="/cards">Traceability</NavLink><NavLink to="/wbs">WBS view</NavLink></div>}</div><div className="nav-group"><button className="nav-parent" onClick={() => setExecutionViewOpen(value => !value)} aria-expanded={executionViewOpen}><span>Execution View</span><i aria-hidden="true">{executionViewOpen ? '−' : '+'}</i></button>{executionViewOpen && <div className="nav-children"><NavLink to="/sprints">Sprint View</NavLink></div>}</div><div className="nav-group"><button className="nav-parent" onClick={() => setAppSettingOpen(value => !value)} aria-expanded={appSettingOpen}><span>App Setting</span><i aria-hidden="true">{appSettingOpen ? '−' : '+'}</i></button>{appSettingOpen && <div className="nav-subgroups"><div className="nav-group"><button className="nav-subparent" onClick={() => setPortfolioSyncOpen(value => !value)} aria-expanded={portfolioSyncOpen}><span>Portfolio Sync</span><i aria-hidden="true">{portfolioSyncOpen ? '−' : '+'}</i></button>{portfolioSyncOpen && <div className="nav-children"><NavLink to="/sync">Sync Monitoring</NavLink></div>}</div><div className="nav-group"><button className="nav-subparent" onClick={() => setConfigurationOpen(value => !value)} aria-expanded={configurationOpen}><span>Configuration</span><i aria-hidden="true">{configurationOpen ? '−' : '+'}</i></button>{configurationOpen && <div className="nav-children"><NavLink to="/traceability">Traceability configuration</NavLink><NavLink to="/sprint-view-configuration">Sprint View configuration</NavLink><div className="nav-nested"><span>Grid configuration</span><NavLink to="/traceability-grid-configuration">Traceability Grid</NavLink><NavLink to="/sprint-grid-configuration">Sprint Grid</NavLink></div><NavLink to="/configuration">Jira connection</NavLink></div>}</div></div>}</div>
    </nav><div className="security">Designed and Developed by VJNR MES Team</div></aside>
    <main>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss">×</button></div>}
      <Routes>
        <Route path="/" element={<Navigate to="/overview" replace/>}/>
        <Route path="/overview" element={<><PageHeader eyebrow="EXECUTIVE PORTFOLIO" title="Portfolio overview" subtitle={projectLabel} configured={health.data?.jira_configured}/><Overview summary={summary.data} groups={statusGroups.data?.groups}/></>}/>
        <Route path="/hierarchy" element={<HierarchyPage projects={projects.data?.items ?? []} fields={fields.data?.items ?? []} configured={health.data?.jira_configured}/>}/>
        <Route path="/cards" element={<CardViewPage projects={projects.data?.items ?? []} fields={fields.data?.items ?? []} configured={health.data?.jira_configured}/>}/>
        <Route path="/wbs" element={<WbsViewPage projects={projects.data?.items ?? []} configured={health.data?.jira_configured}/>}/>
        <Route path="/sprints" element={<SprintViewPage projects={projects.data?.items ?? []} configured={health.data?.jira_configured}/>}/>
        <Route path="/traceability" element={<><PageHeader eyebrow="TRACEABILITY" title="Traceability configuration" subtitle="Choose a project and define its grouping hierarchy." configured={health.data?.jira_configured}/><TraceabilityConfiguration projects={projects.data?.items ?? []} fields={fields.data?.items ?? []} onNotice={setNotice}/></>}/>
        <Route path="/grid-configuration" element={<Navigate to="/traceability-grid-configuration" replace/>}/>
        <Route path="/traceability-grid-configuration" element={<GridConfiguration scope="traceability" projects={projects.data?.items ?? []} configured={health.data?.jira_configured} onNotice={setNotice}/>}/>
        <Route path="/sprint-grid-configuration" element={<GridConfiguration scope="sprint" projects={projects.data?.items ?? []} configured={health.data?.jira_configured} onNotice={setNotice}/>}/>
        <Route path="/sprint-view-configuration" element={<SprintViewConfiguration projects={projects.data?.items ?? []} configured={health.data?.jira_configured} onNotice={setNotice}/>}/>
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

function sprintGroupingChoices(fields: Field[]) { return [
  {id: 'status_id', name: 'Status'}, {id: 'issue_type_id', name: 'Issue type'}, {id: 'assignee', name: 'Assignee'},
  ...fields.filter(field => !new Set(['summary', 'project', 'issuetype', 'status', 'parent', 'assignee', 'reporter', 'created', 'updated', 'duedate', 'resolutiondate']).has(field.jira_field_id)).map(field => ({id: field.jira_field_id, name: field.name})),
].filter((choice, index, all) => all.findIndex(item => item.id === choice.id) === index) }

function CardViewPage({projects, fields, configured}: {projects: Project[]; fields: Field[]; configured?: boolean}) {
  const fallbackProject = projects.find(project => project.active) ?? projects[0]
  const [projectId, setProjectId] = useState('')
  useEffect(() => { if (!projectId && fallbackProject) setProjectId(fallbackProject.jira_project_id) }, [projectId, fallbackProject])
  const project = projects.find(item => item.jira_project_id === projectId)
  const config = useQuery({queryKey: ['traceability-config', projectId], queryFn: () => api.traceabilityConfig(projectId), enabled: !!projectId})
  const groupingFields = config.data?.grouping_fields ?? ['labels', 'status_id', 'issue_type_id']
  const choices = groupingChoices(fields)
  const levelCaptions = groupingFields.map((field, index) => config.data?.level_captions[index]?.trim() || choices.find(choice => choice.id === field)?.name || field)
  return <><PageHeader eyebrow="PORTFOLIO VIEW" title="Traceability" subtitle={project ? `${project.key} · ${groupingFields.length} grouping levels` : 'Select a project'} configured={configured}/><section className="project-picker"><label>Project <select aria-label="Traceability project" value={projectId} onChange={event => setProjectId(event.target.value)}><option value="" disabled>Select a project</option>{projects.map(item => <option key={item.jira_project_id} value={item.jira_project_id}>{item.key} · {item.name}</option>)}</select></label><span>{config.data?.persisted ? 'Saved traceability configuration' : 'Using default grouping'}</span></section>{projectId && !config.isLoading ? <section className="card-browser" key={`${projectId}-${groupingFields.join('|')}-${levelCaptions.join('|')}`}><div className="cardhead"><div><span className="step">NESTED CARD PATH</span><h2>{levelCaptions.join(' → ')}</h2></div><span>Select a card to open the next level</span></div><CardGroupingBranch projectId={projectId} fields={groupingFields} captions={levelCaptions} choices={choices} level={0} filters={[]}/></section> : <State text="Loading traceability configuration…"/>}</>
}

const mandatoryGridColumns = ['Key', 'Summary', 'Issue type', 'Baseline due', 'Revised due', 'Status']

function SprintViewConfiguration({projects, configured, onNotice}: {projects: Project[]; configured?: boolean; onNotice: (message: string) => void}) {
  const queryClient = useQueryClient()
  const fallbackProject = projects.find(project => project.active) ?? projects[0]
  const [projectId, setProjectId] = useState('')
  const [levels, setLevels] = useState<string[]>([])
  const [captions, setCaptions] = useState<string[]>([])
  useEffect(() => { if (!projectId && fallbackProject) setProjectId(fallbackProject.jira_project_id) }, [projectId, fallbackProject])
  const projectFields = useQuery({queryKey: ['project-grid-fields', projectId], queryFn: () => api.gridFields(projectId), enabled: Boolean(projectId)})
  const config = useQuery({queryKey: ['sprint-view-config', projectId], queryFn: () => api.sprintViewConfig(projectId), enabled: Boolean(projectId)})
  useEffect(() => { if (config.data) { setLevels(config.data.grouping_fields); setCaptions(config.data.grouping_fields.map((_, index) => config.data?.level_captions[index] ?? '')) } }, [config.data])
  const choices = sprintGroupingChoices(projectFields.data?.items ?? [])
  const save = useMutation({mutationFn: () => api.saveSprintViewConfig(projectId, levels, captions), onSuccess: data => { queryClient.setQueryData(['sprint-view-config', projectId], data); onNotice(`Saved ${levels.length} Sprint View levels for ${projects.find(project => project.jira_project_id === projectId)?.key ?? projectId}.`) }, onError: error => onNotice(error.message)})
  const addLevel = () => { const next = choices.find(choice => !levels.includes(choice.id)); if (next) { setLevels(current => [...current, next.id]); setCaptions(current => [...current, '']) } }
  const removeLevel = (index: number) => { setLevels(current => current.filter((_, position) => position !== index)); setCaptions(current => current.filter((_, position) => position !== index)) }
  return <><PageHeader eyebrow="APP SETTING · CONFIGURATION" title="Sprint View configuration" subtitle="Define project-specific execution grouping and captions." configured={configured}/><section className="trace-config"><div className="trace-project"><label>Project<select aria-label="Sprint View configuration project" value={projectId} onChange={event => { setProjectId(event.target.value); setLevels([]); setCaptions([]) }}><option value="" disabled>Select a project</option>{projects.map(project => <option key={project.jira_project_id} value={project.jira_project_id}>{project.key} · {project.name}</option>)}</select></label><p>Fields are derived from Jira metadata present for the selected project. Configure any number of nested grouping levels.</p></div>{projectFields.isLoading || config.isLoading ? <State text="Loading applicable Jira metadata…"/> : <div className="level-editor">{levels.map((field, index) => <div className="level-edit" key={index}><span>{index + 1}</span><label><span className="sr-only">Sprint grouping field for level {index + 1}</span><select value={field} onChange={event => setLevels(current => current.map((item, position) => position === index ? event.target.value : item))}>{choices.map(choice => <option key={choice.id} value={choice.id}>{choice.name}</option>)}</select></label><label className="caption-input"><span>Card caption</span><input maxLength={100} value={captions[index] ?? ''} placeholder={choices.find(choice => choice.id === field)?.name ?? field} onChange={event => setCaptions(current => current.map((item, position) => position === index ? event.target.value : item))}/></label>{levels.length > 1 && <button className="secondary" aria-label={`Remove sprint level ${index + 1}`} onClick={() => removeLevel(index)}>Remove</button>}</div>)}</div>}<div className="trace-actions"><button className="secondary" disabled={!choices.some(choice => !levels.includes(choice.id))} onClick={addLevel}>Add grouping level</button><button disabled={!projectId || !levels.length || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save Sprint View configuration'}</button></div></section></>
}

function GridConfiguration({scope, projects, configured, onNotice}: {scope: 'traceability' | 'sprint'; projects: Project[]; configured?: boolean; onNotice: (message: string) => void}) {
  const queryClient = useQueryClient()
  const fallbackProject = projects.find(project => project.active) ?? projects[0]
  const [projectId, setProjectId] = useState('')
  const [selectedFields, setSelectedFields] = useState<string[]>([])
  const [fieldToAdd, setFieldToAdd] = useState('')
  useEffect(() => { if (!projectId && fallbackProject) setProjectId(fallbackProject.jira_project_id) }, [projectId, fallbackProject])
  const project = projects.find(item => item.jira_project_id === projectId)
  const config = useQuery({queryKey: [`${scope}-grid-config`, projectId], queryFn: () => scope === 'sprint' ? api.sprintGridConfig(projectId) : api.gridConfig(projectId), enabled: Boolean(projectId)})
  const applicableFields = useQuery({queryKey: ['project-grid-fields', projectId], queryFn: () => api.gridFields(projectId), enabled: Boolean(projectId)})
  useEffect(() => { if (config.data) setSelectedFields(config.data.optional_fields.map(field => field.field_id)) }, [config.data])
  const save = useMutation({mutationFn: () => scope === 'sprint' ? api.saveSprintGridConfig(projectId, selectedFields) : api.saveGridConfig(projectId, selectedFields), onSuccess: () => { onNotice(`${scope === 'sprint' ? 'Sprint' : 'Traceability'} Grid configuration saved.`); queryClient.invalidateQueries({queryKey: [`${scope}-grid-config`, projectId]}); queryClient.invalidateQueries({queryKey: ['card-result-issues']}); queryClient.invalidateQueries({queryKey: ['card-result-epics']}) }, onError: error => onNotice(error.message)})
  const excluded = new Set(['key', 'summary', 'issuetype', 'issue_type_id', 'status', 'status_id', 'duedate'])
  const available = (applicableFields.data?.items ?? []).filter(field => !excluded.has(field.jira_field_id) && !selectedFields.includes(field.jira_field_id))
  const fieldById = new Map((applicableFields.data?.items ?? []).map(field => [field.jira_field_id, field]))
  const move = (index: number, offset: number) => setSelectedFields(current => { const next = [...current]; const target = index + offset; if (target < 0 || target >= next.length) return current; [next[index], next[target]] = [next[target], next[index]]; return next })
  const add = () => { if (fieldToAdd) { setSelectedFields(current => [...current, fieldToAdd]); setFieldToAdd('') } }
  const viewName = scope === 'sprint' ? 'Sprint Grid' : 'Traceability Grid'
  return <><PageHeader eyebrow="APP SETTING · CONFIGURATION · GRID" title={`${viewName} configuration`} subtitle={project ? `${project.key} · Configure ${viewName} work-item columns` : 'Select a project'} configured={configured}/><section className="project-picker"><label>Project <select aria-label={`${viewName} configuration project`} value={projectId} onChange={event => { setProjectId(event.target.value); setSelectedFields([]); setFieldToAdd('') }}><option value="" disabled>Select a project</option>{projects.map(item => <option key={item.jira_project_id} value={item.jira_project_id}>{item.key} · {item.name}</option>)}</select></label><span>Configuration applies only to this project and view</span></section><section className="grid-config"><div className="cardhead"><div><span className="step">MANDATORY COLUMNS</span><h2>Always displayed</h2></div><span>{mandatoryGridColumns.length} columns</span></div><div className="mandatory-columns">{mandatoryGridColumns.map((column, index) => <span key={column}><b>{index + 1}</b>{column}</span>)}</div><div className="grid-field-builder"><div><span className="step">OPTIONAL JIRA FIELDS</span><h2>{viewName} project columns</h2><p>Only fields applicable to the selected project are available. Newly selected fields may require a Jira sync before values appear.</p></div><div className="grid-field-add"><select aria-label="Applicable Jira field" value={fieldToAdd} onChange={event => setFieldToAdd(event.target.value)}><option value="">Select a standard or custom field…</option>{available.map(field => <option value={field.jira_field_id} key={field.jira_field_id}>{field.name} · {field.is_custom ? 'Custom' : 'Standard'}</option>)}</select><button disabled={!fieldToAdd} onClick={add}>Add column</button></div></div>{config.isLoading || applicableFields.isLoading ? <State text="Loading project fields…"/> : <div className="selected-grid-fields">{selectedFields.length ? selectedFields.map((fieldId, index) => { const field = fieldById.get(fieldId); return <div className="selected-grid-field" key={fieldId}><span className="field-order">{mandatoryGridColumns.length + index + 1}</span><div><strong>{field?.name ?? fieldId}</strong><small>{fieldId} · {field?.is_custom ? 'Custom field' : 'Standard field'}</small></div><div className="field-actions"><button className="secondary" disabled={index === 0} onClick={() => move(index, -1)} aria-label={`Move ${field?.name ?? fieldId} up`}>↑</button><button className="secondary" disabled={index === selectedFields.length - 1} onClick={() => move(index, 1)} aria-label={`Move ${field?.name ?? fieldId} down`}>↓</button><button className="remove-field" onClick={() => setSelectedFields(current => current.filter(value => value !== fieldId))}>Remove</button></div></div>}) : <State text="No optional columns selected."/>}</div>}<div className="trace-actions"><span>{selectedFields.length} optional columns</span><button disabled={!projectId || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : `Save ${viewName} configuration`}</button></div></section></>
}

function WbsViewPage({projects, configured}: {projects: Project[]; configured?: boolean}) {
  const fallbackProject = projects.find(project => project.active) ?? projects[0]
  const [projectId, setProjectId] = useState('')
  useEffect(() => { if (!projectId && fallbackProject) setProjectId(fallbackProject.jira_project_id) }, [projectId, fallbackProject])
  const project = projects.find(item => item.jira_project_id === projectId)
  const flow = useQuery({queryKey: ['wbs-flow', projectId], queryFn: () => api.wbsFlow(projectId), enabled: Boolean(projectId)})
  return <><PageHeader eyebrow="PORTFOLIO VIEW" title="WBS flow" subtitle={project ? `${project.key} · Traceability flow across configured levels` : 'Select a project'} configured={configured}/><section className="project-picker"><label>Project <select aria-label="WBS project" value={projectId} onChange={event => setProjectId(event.target.value)}><option value="" disabled>Select a project</option>{projects.map(item => <option key={item.jira_project_id} value={item.jira_project_id}>{item.key} · {item.name}</option>)}</select></label><span>{flow.data ? `${flow.data.issue_count} work items · Sync version ${flow.data.sync_version}` : 'Loading flow'}</span></section>{flow.isLoading ? <State text="Building WBS flow…"/> : flow.error ? <State text={flow.error.message}/> : flow.data ? <SankeyPlot flow={flow.data}/> : null}</>
}

function SprintViewPage({projects, configured}: {projects: Project[]; configured?: boolean}) {
  const fallbackProject = projects.find(project => project.active) ?? projects[0]
  const [projectId, setProjectId] = useState('')
  useEffect(() => { if (!projectId && fallbackProject) setProjectId(fallbackProject.jira_project_id) }, [projectId, fallbackProject])
  const project = projects.find(item => item.jira_project_id === projectId)
  const config = useQuery({queryKey: ['sprint-view-config', projectId], queryFn: () => api.sprintViewConfig(projectId), enabled: Boolean(projectId)})
  const projectFields = useQuery({queryKey: ['project-grid-fields', projectId], queryFn: () => api.gridFields(projectId), enabled: Boolean(projectId)})
  const groupingFields = config.data?.grouping_fields ?? []
  const choices = sprintGroupingChoices(projectFields.data?.items ?? [])
  const captions = groupingFields.map((field, index) => config.data?.level_captions[index]?.trim() || choices.find(choice => choice.id === field)?.name || field)
  return <><PageHeader eyebrow="EXECUTION VIEW" title="Sprint View" subtitle={project ? `${project.key} · ${groupingFields.length} configured execution levels` : 'Select a project'} configured={configured}/><section className="project-picker"><label>Project <select aria-label="Sprint project" value={projectId} onChange={event => setProjectId(event.target.value)}><option value="" disabled>Select a project</option>{projects.map(item => <option key={item.jira_project_id} value={item.jira_project_id}>{item.key} · {item.name}</option>)}</select></label><span>{config.data?.persisted ? 'Saved Sprint View configuration' : 'Using metadata-driven default grouping'}</span></section>{config.isLoading || projectFields.isLoading ? <State text="Loading Sprint View configuration…"/> : groupingFields.length ? <section className="card-browser" key={`${projectId}-${groupingFields.join('|')}-${captions.join('|')}`}><div className="cardhead"><div><span className="step">SPRINT EXECUTION PATH</span><h2>{captions.join(' → ')}</h2></div><span>Select a card to open the next execution level</span></div><CardGroupingBranch projectId={projectId} fields={groupingFields} captions={captions} choices={choices} level={0} filters={[]} gridScope="sprint"/></section> : <State text="Configure at least one Sprint View grouping level."/>}</>
}

function SankeyPlot({flow}: {flow: WbsFlow}) {
  const [selected, setSelected] = useState<string | null>(null)
  const [selectedLeaf, setSelectedLeaf] = useState<WbsFlow['nodes'][number] | null>(null)
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setSelectedLeaf(null) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [])
  const width = 1200
  const grouped = flow.levels.map((_, level) => flow.nodes.filter(node => node.level === level).sort((a, b) => b.value - a.value))
  const maxNodes = Math.max(1, ...grouped.map(nodes => nodes.length))
  const height = Math.max(520, maxNodes * 58 + 100)
  const positions = new Map<string, {x: number; y: number; h: number}>()
  grouped.forEach((nodes, level) => nodes.forEach((node, index) => {
    const x = 90 + level * ((width - 180) / Math.max(1, flow.levels.length - 1))
    const y = 75 + index * ((height - 120) / Math.max(1, nodes.length))
    const h = Math.max(14, Math.min(38, 12 + (node.value / Math.max(1, flow.issue_count)) * 90))
    positions.set(node.id, {x, y, h})
  }))
  const connected = new Set<string>()
  if (selected) flow.links.forEach(link => { if (link.source === selected) connected.add(link.target); if (link.target === selected) connected.add(link.source) })
  const maxLink = Math.max(1, ...flow.links.map(link => link.value))
  const lastLevel = flow.levels.length - 1
  const leafField = flow.levels[lastLevel]?.field_id
  const nodeValue = (node: WbsFlow['nodes'][number]) => node.id.slice(node.id.indexOf(':') + 1)
  const leafFilter = selectedLeaf && leafField ? (() => {
    const value = nodeValue(selectedLeaf)
    if (value === '__null__') return {field_id: leafField, operator: 'is_null', value: true}
    if (value !== '__other__') return {field_id: leafField, operator: 'eq', value}
    const leafNodes = flow.nodes.filter(node => node.level === lastLevel)
    const regularValues = leafNodes.map(nodeValue).filter(item => item !== '__null__' && item !== '__other__')
    const remainder = {field_id: leafField, operator: 'not_in', value: regularValues}
    return leafNodes.some(node => nodeValue(node) === '__null__') ? remainder : {or: [remainder, {field_id: leafField, operator: 'is_null', value: true}]}
  })() : null
  const activateNode = (node: WbsFlow['nodes'][number]) => {
    setSelected(current => current === node.id ? null : node.id)
    if (node.level === lastLevel) setSelectedLeaf(node)
  }
  return <section className="wbs-panel"><div className="wbs-heading"><div><span className="step">CONFIGURED TRACEABILITY FLOW</span><h2>{flow.levels.map(level => level.caption).join(' → ')}</h2></div><span>Click a terminal node to open its work-item grid</span></div><div className="sankey-wrap"><svg className="sankey" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`WBS Sankey flow for ${flow.issue_count} Jira work items`}><defs><linearGradient id="flow-gradient" x1="0" x2="1"><stop offset="0" stopColor="#29469a"/><stop offset=".55" stopColor="#7188ce"/><stop offset="1" stopColor="#d71920"/></linearGradient></defs>{flow.levels.map((level, index) => <text className="sankey-level" x={90 + index * ((width - 180) / Math.max(1, flow.levels.length - 1))} y="28" textAnchor="middle" key={level.field_id}>{level.caption}</text>)}<g className="sankey-links">{flow.links.map((link, index) => { const source = positions.get(link.source); const target = positions.get(link.target); if (!source || !target) return null; const active = !selected || link.source === selected || link.target === selected || (connected.has(link.source) && connected.has(link.target)); const bend = (target.x - source.x) * .48; return <path className={active ? 'active' : 'dim'} d={`M ${source.x + 10} ${source.y + source.h / 2} C ${source.x + bend} ${source.y + source.h / 2}, ${target.x - bend} ${target.y + target.h / 2}, ${target.x - 10} ${target.y + target.h / 2}`} strokeWidth={Math.max(1.5, (link.value / maxLink) * 18)} key={`${link.source}-${link.target}-${index}`}><title>{link.value} work items</title></path>})}</g><g className="sankey-nodes">{flow.nodes.map(node => { const position = positions.get(node.id); if (!position) return null; const active = !selected || node.id === selected || connected.has(node.id); const last = node.level === lastLevel; return <g className={active ? 'active' : 'dim'} role="button" tabIndex={0} aria-label={`${node.label}, ${node.value} work items${last ? ', open grid' : ''}`} onClick={() => activateNode(node)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activateNode(node) } }} key={node.id}><rect x={position.x - 10} y={position.y} width="20" height={position.h} rx="7"/><circle cx={position.x} cy={position.y + position.h / 2} r="3"/><text x={last ? position.x - 18 : position.x + 18} y={position.y + position.h / 2 - 2} textAnchor={last ? 'end' : 'start'}>{node.label}</text><text className="sankey-value" x={last ? position.x - 18 : position.x + 18} y={position.y + position.h / 2 + 12} textAnchor={last ? 'end' : 'start'}>{node.value} work items</text></g>})}</g></svg></div>{selected && <button className="secondary wbs-reset" onClick={() => setSelected(null)}>Show all flows</button>}{selectedLeaf && leafFilter && <div className="wbs-modal-backdrop" onMouseDown={() => setSelectedLeaf(null)}><section className="wbs-modal" role="dialog" aria-modal="true" aria-labelledby="wbs-modal-title" onMouseDown={event => event.stopPropagation()}><div className="wbs-modal-head"><div><span className="step">{flow.levels[lastLevel].caption} · WORK ITEMS</span><h2 id="wbs-modal-title">{selectedLeaf.label}</h2></div><button className="wbs-modal-close" onClick={() => setSelectedLeaf(null)} aria-label="Close WBS work-item grid">×</button></div><CardResults projectId={flow.project_id} filter={leafFilter} direct={flow.levels.some(level => level.field_id === 'issue_type_id')} groupLabel={selectedLeaf.label}/></section></div>}</section>
}

type CardMetricsData = {task_count: number; in_progress_count: number; baseline_delayed_count: number; on_track_count: number; delayed_count: number; no_due_date_count: number; baseline_due_date: string | null; latest_due_date: string | null; next_group_count: number}

function cardDate(value: string | null) {
  return value ? new Intl.DateTimeFormat(undefined, {day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC'}).format(new Date(value)) : 'Not set'
}

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
  return <><div className="card-date-strip" aria-label="Card due dates"><span title="Latest first-assigned due date across bottom-level tasks"><i aria-hidden="true">◆</i><small>Baseline due</small><b>{cardDate(group.baseline_due_date)}</b></span><span title="Latest current Jira due date across bottom-level tasks"><i aria-hidden="true">↻</i><small>Latest Jira due</small><b>{cardDate(group.latest_due_date)}</b></span></div><table className="card-metrics" aria-label="Card metrics"><tbody>{rows.map(row => <tr className={`metric-${row.tone}`} title={row.hint} key={row.label}><td><span className="metric-icon" aria-hidden="true">{row.icon}</span>{row.label}</td><td>{row.value}</td></tr>)}</tbody></table></>
}

type GridScope = 'traceability' | 'sprint'

function CardGroupingBranch({projectId, fields, captions, choices, level, filters, gridScope = 'traceability'}: {projectId: string; fields: string[]; captions: string[]; choices: {id: string; name: string}[]; level: number; filters: Record<string, unknown>[]; gridScope?: GridScope}) {
  const [selected, setSelected] = useState<Group | null>(null)
  const field = fields[level]
  const filter = combineFilters(filters)
  const nextField = fields[level + 1]
  const groups = useQuery({queryKey: ['card-groups', projectId, level, field, nextField, filter], queryFn: () => api.cardGroups(field, nextField, [projectId], filter ?? undefined)})
  const fieldName = captions[level] || choices.find(choice => choice.id === field)?.name || field
  if (groups.isLoading) return <State text={`Loading ${fieldName} cards…`}/>
  if (groups.error) return <State text={groups.error.message}/>
  return <div className="card-level"><div className="card-level-title"><span>Level {level + 1}</span><strong>{fieldName}</strong></div><div className="trace-card-grid">{groups.data?.groups.map(group => { const open = selected?.value === group.value; const muted = selected !== null && !open; const empty = group.task_count === 0; const nextFilters = [...filters, groupFilter(field, group)]; return <article className={`trace-card ${open ? 'open' : ''} ${muted ? 'muted' : ''} ${empty ? 'empty-card' : ''}`} key={`${field}-${String(group.value)}`}><button className="trace-card-button" onClick={() => setSelected(open ? null : group)} aria-expanded={open}><span>{group.label}</span><strong>{group.issue_count}</strong><CardMetrics group={group} showNext={Boolean(nextField)}/><small>{level === fields.length - 1 ? 'View work items' : `Open ${captions[level + 1] || `level ${level + 2}`}`}</small></button>{open && <div className="trace-card-children">{level === fields.length - 1 ? <CardResults projectId={projectId} filter={combineFilters(nextFilters)!} direct={fields.includes('issue_type_id')} groupLabel={group.label} gridScope={gridScope}/> : <CardGroupingBranch projectId={projectId} fields={fields} captions={captions} choices={choices} level={level + 1} filters={nextFilters} gridScope={gridScope}/>}</div>}</article>})}</div>{groups.data?.non_additive && <p className="group-warning">Multi-value groups can overlap.</p>}</div>
}

function CardResults({projectId, filter, direct, groupLabel, gridScope = 'traceability'}: {projectId: string; filter: Record<string, unknown>; direct: boolean; groupLabel: string; gridScope?: GridScope}) {
  type SortField = 'key' | 'summary' | 'type' | 'baseline' | 'revised' | 'status'
  const [sortField, setSortField] = useState<SortField>('key')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const [search, setSearch] = useState('')
  const [issueType, setIssueType] = useState('')
  const [status, setStatus] = useState('')
  const [dueFilter, setDueFilter] = useState('')
  const [metadataIssueKey, setMetadataIssueKey] = useState<string | null>(null)
  const epics = useQuery({queryKey: ['card-result-epics', projectId, filter], queryFn: () => api.epicsByFilter([projectId], filter), enabled: !direct})
  const issues = useQuery({queryKey: ['card-result-issues', projectId, filter], queryFn: () => api.issuesByFilter([projectId], filter), enabled: direct})
  const liveMetadata = useQuery({queryKey: ['live-issue-metadata', metadataIssueKey], queryFn: () => api.issueMetadata(metadataIssueKey!), enabled: Boolean(metadataIssueKey), staleTime: 0, gcTime: 0})
  const gridConfig = useQuery({queryKey: [`${gridScope}-grid-config`, projectId], queryFn: () => gridScope === 'sprint' ? api.sprintGridConfig(projectId) : api.gridConfig(projectId)})
  const result = direct ? issues : epics
  const changeSort = (field: SortField) => { if (sortField === field) setSortDirection(value => value === 'asc' ? 'desc' : 'asc'); else { setSortField(field); setSortDirection('asc') } }
  const valueFor = (issue: Issue) => ({key: issue.issue_key, summary: issue.summary, type: issue.issue_type.name ?? '', baseline: issue.baseline_due_at ?? '', revised: issue.due_at ?? '', status: issue.status.name ?? ''})[sortField]
  const allItems = result.data?.items ?? []
  const issueTypes = [...new Set(allItems.map(issue => issue.issue_type.name).filter((value): value is string => Boolean(value)))].sort()
  const statuses = [...new Set(allItems.map(issue => issue.status.name).filter((value): value is string => Boolean(value)))].sort()
  const today = new Date().toISOString().slice(0, 10)
  const filteredItems = allItems.filter(issue => {
    const term = search.trim().toLocaleLowerCase()
    if (term && !`${issue.issue_key} ${issue.summary}`.toLocaleLowerCase().includes(term)) return false
    if (issueType && issue.issue_type.name !== issueType) return false
    if (status && issue.status.name !== status) return false
    if (dueFilter === 'missing' && issue.due_at) return false
    if (dueFilter === 'defined' && !issue.due_at) return false
    if (dueFilter === 'baseline-delayed' && (!issue.baseline_due_at || issue.baseline_due_at.slice(0, 10) >= today || issue.status.category_key === 'done')) return false
    if (dueFilter === 'revised-delayed' && (!issue.due_at || issue.due_at.slice(0, 10) >= today || issue.status.category_key === 'done')) return false
    return true
  })
  const sortedItems = [...filteredItems].sort((left, right) => valueFor(left).localeCompare(valueFor(right), undefined, {numeric: true}) * (sortDirection === 'asc' ? 1 : -1))
  if (result.isLoading) return <State text="Loading work items…"/>
  if (result.error) return <State text={result.error.message}/>
  const sortButton = (field: SortField, label: string) => <button className={sortField === field ? 'sorted' : ''} onClick={() => changeSort(field)}>{label}<span aria-hidden="true">{sortField === field ? sortDirection === 'asc' ? '▲' : '▼' : '↕'}</span></button>
  const filtersActive = Boolean(search || issueType || status || dueFilter)
  const clearFilters = () => { setSearch(''); setIssueType(''); setStatus(''); setDueFilter('') }
  const optionalFields = gridConfig.data?.optional_fields ?? []
  const gridTemplate = `100px minmax(260px,1fr) 120px 125px 125px 145px ${optionalFields.map(() => '150px').join(' ')}`.trim()
  return <div className="card-result-grid"><div className="result-head"><strong>{groupLabel}</strong><span>{filteredItems.length} of {result.data?.total_count ?? 0} results</span></div><div className="issue-filter-bar"><label><span>Search</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Key or summary…"/></label><label><span>Issue type</span><select value={issueType} onChange={event => setIssueType(event.target.value)}><option value="">All types</option>{issueTypes.map(value => <option key={value}>{value}</option>)}</select></label><label><span>Status</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option>{statuses.map(value => <option key={value}>{value}</option>)}</select></label><label><span>Due date</span><select value={dueFilter} onChange={event => setDueFilter(event.target.value)}><option value="">All dates</option><option value="missing">No due date</option><option value="defined">Due date defined</option><option value="baseline-delayed">Baseline delayed</option><option value="revised-delayed">Revised delayed</option></select></label><button className="secondary" disabled={!filtersActive} onClick={clearFilters}>Clear filters</button></div>{sortedItems.length ? <div className="issue-list"><div className="issue-grid-head" style={{gridTemplateColumns: gridTemplate}}>{sortButton('key', 'Key')}{sortButton('summary', 'Summary')}{sortButton('type', 'Issue type')}{sortButton('baseline', 'Baseline due')}{sortButton('revised', 'Revised due')}{sortButton('status', 'Status')}{optionalFields.map(field => <span className="optional-grid-heading" key={field.field_id}>{field.name}</span>)}</div>{sortedItems.map(issue => <div className="issue-row card-issue-row" style={{gridTemplateColumns: gridTemplate}} key={issue.jira_issue_id}><span className="issue-key-cell"><b>{issue.issue_key}</b><button className="issue-info" onClick={() => setMetadataIssueKey(issue.issue_key)} aria-label={`Show live Jira metadata for ${issue.issue_key}`} title="Show live Jira metadata">i</button></span><span>{issue.summary}</span><small>{issue.issue_type.name ?? 'Unknown type'}</small><DueDate value={issue.baseline_due_at}/><DueDate value={issue.due_at} revised/><StatusBadge name={issue.status.name} category={issue.status.category_key}/>{optionalFields.map(field => <span className="optional-grid-value" title={gridValueText(issue.configured_fields?.[field.field_id])} key={field.field_id}>{gridValueText(issue.configured_fields?.[field.field_id])}</span>)}</div>)}</div> : <State text={filtersActive ? 'No work items match the selected filters.' : 'No matching work items.'}/>} {metadataIssueKey && <IssueMetadataModal issueKey={metadataIssueKey} metadata={liveMetadata.data} loading={liveMetadata.isLoading} error={liveMetadata.error} onClose={() => setMetadataIssueKey(null)}/>}</div>
}

function gridValueText(value: unknown): string {
  if (value == null || value === '') return '—'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(gridValueText).filter(item => item !== '—').join(', ') || '—'
  const object = value as Record<string, unknown>
  if (object.type === 'doc') return adfText(object).trim() || '—'
  for (const key of ['displayName', 'name', 'value', 'label', 'key']) if (object[key] != null) return gridValueText(object[key])
  return Object.entries(object).map(([key, nested]) => `${key}: ${gridValueText(nested)}`).join('; ')
}

function adfText(node: unknown): string {
  if (!node || typeof node !== 'object') return ''
  const item = node as {type?: string; text?: string; content?: unknown[]}
  if (item.type === 'text') return item.text ?? ''
  if (item.type === 'hardBreak') return '\n'
  const content = item.content?.map(adfText).join('') ?? ''
  if (['tableCell', 'tableHeader'].includes(item.type ?? '')) return `${content.trim()} | `
  if (item.type === 'tableRow') return `${content.replace(/\s*\|\s*$/, '')}\n`
  if (item.type === 'bulletList' || item.type === 'orderedList') return `${content}\n`
  if (item.type === 'listItem') return `• ${content.trim()}\n`
  return ['paragraph', 'heading'].includes(item.type ?? '') ? `${content}\n` : content
}

function MetadataValue({value}: {value: unknown}) {
  if (value == null || value === '') return <span className="metadata-empty">Not set</span>
  if (typeof value === 'string') return /^https?:\/\//.test(value) ? <a href={value} target="_blank" rel="noreferrer">{value}</a> : <span>{value}</span>
  if (typeof value === 'number' || typeof value === 'boolean') return <span>{String(value)}</span>
  if (Array.isArray(value)) {
    if (!value.length) return <span className="metadata-empty">None</span>
    if (value.every(item => ['string', 'number', 'boolean'].includes(typeof item))) return <div className="metadata-pills">{value.map((item, index) => <span key={`${String(item)}-${index}`}>{String(item)}</span>)}</div>
    return <div className="metadata-list">{value.map((item, index) => <div key={index}><b>{index + 1}</b><MetadataValue value={item}/></div>)}</div>
  }
  const objectValue = value as Record<string, unknown>
  if (objectValue.type === 'doc' && Array.isArray(objectValue.content)) return <div className="metadata-richtext">{adfText(objectValue).trim() || 'Not set'}</div>
  return <div className="metadata-object">{Object.entries(objectValue).map(([key, nested]) => <div key={key}><strong>{key.replaceAll('_', ' ')}</strong><MetadataValue value={nested}/></div>)}</div>
}

function IssueMetadataModal({issueKey, metadata, loading, error, onClose}: {issueKey: string; metadata?: LiveIssueMetadata; loading: boolean; error: Error | null; onClose: () => void}) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [onClose])
  const rows = metadata ? Object.entries(metadata.fields).map(([fieldId, value]) => ({fieldId, name: metadata.names[fieldId] ?? fieldId, value})).sort((a, b) => a.name.localeCompare(b.name)) : []
  return <div className="metadata-modal-backdrop" onMouseDown={onClose}><section className="metadata-modal" role="dialog" aria-modal="true" aria-labelledby="metadata-title" onMouseDown={event => event.stopPropagation()}><div className="wbs-modal-head"><div><span className="step">LIVE FROM JIRA · NOT STORED</span><h2 id="metadata-title">{issueKey} metadata</h2></div><button className="wbs-modal-close" onClick={onClose} aria-label="Close Jira metadata">×</button></div>{loading ? <State text="Fetching current metadata from Jira…"/> : error ? <State text={error.message}/> : <div className="metadata-table" role="table" aria-label={`Live Jira metadata for ${issueKey}`}>{rows.map(row => <div className="metadata-row" role="row" key={row.fieldId}><div role="cell"><strong>{row.name}</strong><code>{row.fieldId}</code></div><div className="metadata-value" role="cell"><MetadataValue value={row.value}/></div></div>)}</div>}</section></div>
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
  const [captions, setCaptions] = useState<string[]>(['', '', ''])
  useEffect(() => { if (!projectId && fallbackProject) setProjectId(fallbackProject.jira_project_id) }, [projectId, fallbackProject])
  const config = useQuery({queryKey: ['traceability-config', projectId], queryFn: () => api.traceabilityConfig(projectId), enabled: !!projectId})
  useEffect(() => { if (config.data) { setLevels(config.data.grouping_fields); setCaptions(config.data.grouping_fields.map((_, index) => config.data?.level_captions[index] ?? '')) } }, [config.data])
  const save = useMutation({mutationFn: () => api.saveTraceabilityConfig(projectId, levels, captions), onSuccess: data => {queryClient.setQueryData(['traceability-config', projectId], data); onNotice(`Saved ${levels.length} traceability levels for ${projects.find(project => project.jira_project_id === projectId)?.key ?? projectId}.`)}, onError: error => onNotice(error.message)})
  const choices = groupingChoices(fields)
  const addLevel = () => { const next = choices.find(choice => !levels.includes(choice.id)); if (next) { setLevels(current => [...current, next.id]); setCaptions(current => [...current, '']) } }
  const removeLevel = (index: number) => { setLevels(current => current.filter((_, position) => position !== index)); setCaptions(current => current.filter((_, position) => position !== index)) }
  return <section className="trace-config"><div className="trace-project"><label>Project<select aria-label="Traceability project" value={projectId} onChange={event => setProjectId(event.target.value)}><option value="" disabled>Select a project</option>{projects.map(project => <option key={project.jira_project_id} value={project.jira_project_id}>{project.key} · {project.name}</option>)}</select></label><p>Configure the grouping field and the caption shown in Card view for each level.</p></div><div className="level-editor">{levels.map((field, index) => <div className="level-edit" key={index}><span>{index + 1}</span><label><span className="sr-only">Grouping field for level {index + 1}</span><select value={field} onChange={event => setLevels(current => current.map((item, position) => position === index ? event.target.value : item))}>{choices.map(choice => <option key={choice.id} value={choice.id}>{choice.name}</option>)}</select></label><label className="caption-input"><span>Card caption</span><input maxLength={100} value={captions[index] ?? ''} placeholder={choices.find(choice => choice.id === field)?.name ?? field} onChange={event => setCaptions(current => current.map((item, position) => position === index ? event.target.value : item))}/></label>{levels.length > 1 && <button className="secondary" aria-label={`Remove level ${index + 1}`} onClick={() => removeLevel(index)}>Remove</button>}</div>)}</div><div className="trace-actions"><button className="secondary" disabled={levels.length >= choices.length} onClick={addLevel}>Add grouping level</button><button disabled={!projectId || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save configuration'}</button></div></section>
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
