import {useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import {api, type IntelligencePoint, type Project} from './api'
import './intelligence.css'

function TrendChart({title, points, keys}: {title: string; points: IntelligencePoint[]; keys: {key: keyof IntelligencePoint; label: string; color: string}[]}) {
  const width = 780, height = 230, pad = 35
  const values = points.flatMap(p => keys.map(k => Number(p[k.key]) || 0))
  const max = Math.max(1, ...values) * 1.1
  const x = (i: number) => pad + i * (width - pad * 2) / Math.max(1, points.length - 1)
  const y = (n: number) => height - pad - n / max * (height - pad * 2)
  return <section className="intel-chart"><h3>{title}</h3><div className="intel-legend">{keys.map(k => <span key={k.key}><i style={{background: k.color}}/>{k.label}</span>)}</div>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title} preserveAspectRatio="xMidYMid meet">
      {[0, .25, .5, .75, 1].map(t => <g key={t}><line x1={pad} x2={width-pad} y1={y(max*t)} y2={y(max*t)} stroke="#dfe5ed"/><text x={pad-7} y={y(max*t)+4} textAnchor="end" fontSize="12" fill="#69778a">{Math.round(max*t)}</text></g>)}
      {keys.map(k => <polyline key={k.key} fill="none" stroke={k.color} strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" points={points.map((p,i) => `${x(i)},${y(Number(p[k.key]) || 0)}`).join(' ')}/>)}
      {points.length > 0 && <><text x={pad} y={height-6} fontSize="12" fill="#69778a">{points[0].snapshot_date}</text><text x={width-pad} y={height-6} textAnchor="end" fontSize="12" fill="#69778a">{points[points.length-1].snapshot_date}</text></>}
    </svg>
  </section>
}

export default function IntelligencePage({projects}: {projects: Project[]}) {
  const [days, setDays] = useState(90)
  const [projectId, setProjectId] = useState('')
  const query = useQuery({queryKey: ['intelligence', days, projectId], queryFn: () => api.intelligenceTrends(days, projectId)})
  const data = query.data, latest = data?.latest
  return <div className="intelligence-page">
    <header><p className="eyebrow">PORTFOLIO DELIVERY INTELLIGENCE</p><h1>Intelligence</h1><p className="subtitle">Historical delivery performance based on recorded Jira synchronization snapshots.</p></header>
    <div className="intel-controls"><label>Project <select value={projectId} onChange={e=>setProjectId(e.target.value)}><option value="">All active projects</option>{projects.filter(p=>p.active).map(p=><option key={p.jira_project_id} value={p.jira_project_id}>{p.key} — {p.name}</option>)}</select></label><label>Period <select value={days} onChange={e=>setDays(Number(e.target.value))}><option value={30}>30 days</option><option value={60}>60 days</option><option value={90}>90 days</option><option value={180}>180 days</option><option value={365}>365 days</option></select></label></div>
    {query.isLoading && <p>Loading historical intelligence…</p>}
    {query.isError && <p role="alert">Unable to load intelligence: {query.error.message}</p>}
    {data && !latest && <section className="intel-empty">{data.message}</section>}
    {latest && <><div className="intel-kpis">
      {[['Completion', latest.completion_pct+'%'],['Total work items', latest.total],['Completed',latest.done],['In progress',latest.in_progress],['Overdue',latest.overdue],['Stale open (30d)',latest.stale_30d]].map(([label,value])=><div className="intel-kpi" key={label}><span>{label}</span><strong>{value}</strong></div>)}
    </div>
    {data.points.length < 2 && <p className="intel-empty">First snapshot captured. Run Jira synchronization on subsequent days to establish time-series trends.</p>}
    <div className="intel-charts">
      <TrendChart title="Completion trajectory (%)" points={data.points} keys={[{key:'completion_pct',label:'Completed %',color:'#1674c5'}]}/>
      <TrendChart title="Work-item flow" points={data.points} keys={[{key:'total',label:'Total',color:'#64748b'},{key:'done',label:'Done',color:'#16a085'},{key:'in_progress',label:'In progress',color:'#e49a28'}]}/>
      <TrendChart title="Delivery exposure" points={data.points} keys={[{key:'overdue',label:'Overdue',color:'#d94b55'},{key:'stale_30d',label:'Stale open',color:'#8b5cf6'}]}/>
    </div></>}
    {data && <p className="intel-caveat">Source: {data.source}. {data.caveat} Last observation: {data.last_snapshot ?? 'None'}.</p>}
  </div>
}
