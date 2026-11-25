import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { ErrorBox, Icon, Kpi, Loading, Pill, STATE } from '../components/ui'

const ATT = { blocked: ['ic-bad', 'alert'], licence: ['ic-warn', 'shield'], waiting: ['ic-warn', 'clock'] }

export default function Dashboard() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const nav = useNavigate()
  useEffect(() => { api.dashboard().then(setD).catch(setErr) }, [])
  if (err) return <ErrorBox error={err} />
  if (!d) return <Loading />
  const k = d.kpis
  const active = d.properties.filter(p => p.state !== 'live')
  const avg = Math.round(active.reduce((a, p) => a + p.progress, 0) / Math.max(1, active.length))
  const max = Math.max(1, ...d.pipeline.map(s => s.count))
  const today = new Date().toLocaleDateString('en-CA', { weekday: 'long', month: 'long', day: 'numeric' })
  const firstBlocked = d.attention.find(a => a.kind === 'blocked')

  return (
    <>
      <section className="welcome">
        <div>
          <div className="eyebrow">{today}</div>
          <h1>Onboarding overview</h1>
          <p>{k.onboarding} properties are moving from signed agreement to live listing. {d.attention.length} item{d.attention.length === 1 ? '' : 's'} need attention.</p>
          <div className="row">
            {firstBlocked && <button className="btn light" type="button" onClick={() => nav(`/properties/${firstBlocked.property}`)}><Icon name="alert" small />Review blocked property</button>}
            <button className="btn glass-btn" type="button" onClick={() => nav('/procurement')}><Icon name="cart" small />Procurement</button>
          </div>
        </div>
        <div className="glass">
          <div className="g"><b>{avg}%</b><span>Avg. progress</span></div>
          <div className="g"><b>{k.onboarding}</b><span>Onboarding</span></div>
          <div className="g"><b>{k.live}</b><span>Live</span></div>
        </div>
      </section>

      <div className="kpis">
        <Kpi tone="ic-acc" icon="layers" label="Onboarding" value={k.onboarding} detail="Properties in progress" />
        <Kpi tone="ic-bad" icon="alert" label="Blocked" value={k.blocked} detail="Need a decision or document" />
        <Kpi tone="ic-warn" icon="clock" label="Waiting" value={k.waiting} detail="On building, city or vendors" />
        <Kpi tone="ic-warn" icon="shield" label="Licences" value={k.licences_expiring} detail="Expiring within 60 days" />
        <Kpi tone="ic-ok" icon="checkc" label="Live" value={k.live} detail="Published on all channels" />
      </div>

      <div className="cols">
        <section className="card">
          <div className="card-h"><h2>Properties</h2><span className="sub">{d.properties.length} total</span></div>
          <div className="table-wrap"><table>
            <thead><tr><th>Property</th><th>Current step</th><th>Progress</th><th>Status</th></tr></thead>
            <tbody>
              {d.properties.map(p => (
                <tr key={p.id} className="click" tabIndex={0} onClick={() => nav(`/properties/${p.id}`)} onKeyDown={e => e.key === 'Enter' && nav(`/properties/${p.id}`)}>
                  <td><div className="prop-cell"><div className="prop-ic"><Icon name="home" /></div><div><b className="mono">{p.nickname}</b>
                    <div className="muted sm">{p.address} · {p.bedrooms} bd · {p.bathrooms} ba · {p.beds} bed{p.beds > 1 ? 's' : ''}</div></div></div></td>
                  <td>{p.current_step ? <><b className="sm">{p.current_step.number}. {p.current_step.name}</b><div className="muted sm">{p.current_step.owner}</div></> : <span className="muted">—</span>}</td>
                  <td><div className="row" style={{ gap: 10, flexWrap: 'nowrap' }}><div className={`bar ${p.progress === 100 ? 'done' : ''}`} style={{ width: 96 }}><i style={{ width: `${p.progress}%` }} /></div><span className="num muted sm">{p.progress}%</span></div></td>
                  <td><Pill map={STATE} value={p.state} /></td>
                </tr>
              ))}
              {!d.properties.length && <tr><td colSpan={4} className="empty">No properties yet. Use “New property” to add the first one.</td></tr>}
            </tbody>
          </table></div>
        </section>
        <div style={{ display: 'grid', gap: 22 }}>
          <section className="card">
            <div className="card-h"><h2>Needs attention</h2><span className="pill p-bad nodot">{d.attention.length}</span></div>
            <ul className="att">
              {d.attention.map((a, i) => (
                <li key={i} style={{ cursor: 'pointer' }} onClick={() => nav(`/properties/${a.property}`)}>
                  <div className={`kpi-ic ${ATT[a.kind][0]}`}><Icon name={ATT[a.kind][1]} small /></div>
                  <div><b className="mono">{a.nickname}</b><p>{a.text}</p></div>
                </li>
              ))}
              {!d.attention.length && <li><div className="kpi-ic ic-ok"><Icon name="checkc" small /></div><div><p>Nothing needs attention right now.</p></div></li>}
            </ul>
          </section>
          <section className="card">
            <div className="card-h"><h2>Pipeline by stage</h2></div>
            <div className="card-b pipe">
              {d.pipeline.map(s => (
                <div className="pipe-row" key={s.stage}><span className="muted">{s.stage}</span>
                  <div className="pipe-track"><i style={{ width: `${s.count / max * 100}%`, ...(s.stage === 'Live' ? { background: 'var(--ok)' } : {}) }} /></div><b className="num">{s.count}</b></div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </>
  )
}
