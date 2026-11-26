import { useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, fmtDate, money } from '../api'
import { CountUp, ErrorBox, Icon, Kpi, Loading, PhotoPlaceholder, Pill, Ring, STATE, UserCtx, useToast } from '../components/ui'

const ATT = { blocked: ['ic-bad', 'alert'], licence: ['ic-warn', 'shield'], waiting: ['ic-warn', 'clock'] }
const VISIT_ICON = { inspection: 'checkc', setup_day: 'home', photo_shoot: 'sparkle', delivery: 'truck', repair: 'key', other: 'cal' }
const AGENTS = [
  ['Intake agent', 'file', 'Reads signed agreements, creates the Drive folder and tracker row, drafts the building email.'],
  ['Compliance agent', 'shield', 'Unit email, licence packet, renewal reminders at 60, 30 and 7 days.'],
  ['Procurement agent', 'cart', 'Builds the kit from the master list, checks price and stock, stages store carts.'],
  ['Listing agent', 'sparkle', 'Creates the Guesty listing, uploads photos cover-first, briefs Angel Host.'],
]

function ago(t) {
  const m = Math.round((Date.now() - new Date(t)) / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  return h < 24 ? `${h} h ago` : `${Math.round(h / 24)} d ago`
}

export default function Dashboard() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [sweeping, setSweeping] = useState(false)
  const user = useContext(UserCtx)
  const toast = useToast()
  const nav = useNavigate()
  useEffect(() => { api.dashboard().then(setD).catch(setErr) }, [])
  if (err) return <ErrorBox error={err} />
  if (!d) return <Loading />

  const k = d.kpis
  const active = d.properties.filter(p => p.state !== 'live')
  const avg = Math.round(active.reduce((a, p) => a + p.progress, 0) / Math.max(1, active.length))
  const hour = new Date().getHours()
  const greet = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
  const first = (user?.name || '').split(' ')[0]
  const today = new Date().toLocaleDateString('en-CA', { weekday: 'long', month: 'long', day: 'numeric' })
  const firstBlocked = d.attention.find(a => a.kind === 'blocked')
  const sweep = async () => {
    setSweeping(true)
    try { const r = await api.runSweeps(); toast(r.trace.map(s => s.detail).filter(Boolean).join(' · ') || 'Daily checks done.'); setD(await api.dashboard()) }
    catch (e) { toast(e.message) } finally { setSweeping(false) }
  }
  const progressSpark = [...d.properties].sort((a, b) => a.progress - b.progress).map(p => p.progress)

  return (
    <>
      <section className="hero2">
        <div>
          <div className="eyebrow"><span className="live-dot" />{today} · agents online</div>
          <h1>{greet}{first ? `, ${first}` : ''}. <em>{k.onboarding} homes</em> on their way to live.</h1>
          <p>{d.attention.length ? `${d.attention.length} thing${d.attention.length === 1 ? '' : 's'} need${d.attention.length === 1 ? 's' : ''} your attention today.` : 'Nothing needs your attention today.'} Agents prepare the work; you approve what goes out.</p>
          <div className="actions">
            {firstBlocked && <button className="btn primary" type="button" onClick={() => nav(`/properties/${firstBlocked.property}`)}><Icon name="alert" small />Review blocked property</button>}
            <button className="btn" type="button" onClick={sweep} disabled={sweeping}><Icon name="bot" small />{sweeping ? 'Running checks…' : 'Run daily checks'}</button>
            <button className="btn" type="button" onClick={() => nav('/reports')}><Icon name="chart" small />Reports</button>
          </div>
        </div>
        <div className="hero-stats">
          <div><b><CountUp value={`${avg}%`} /></b><span>Average progress</span></div>
          <div><b><CountUp value={k.live} /></b><span>Live on all channels</span></div>
          <div><b><CountUp value={d.spend?.lines ? `${Math.round(d.spend.delivered / d.spend.lines * 100)}%` : '0%'} /></b><span>Items delivered</span></div>
        </div>
      </section>

      <div className="kpis stagger">
        <Kpi tone="ic-acc" icon="layers" label="Onboarding" value={k.onboarding} detail="Properties in progress" spark={progressSpark} />
        <Kpi tone="ic-bad" icon="alert" label="Blocked" value={k.blocked} detail="Need a decision or document" />
        <Kpi tone="ic-warn" icon="clock" label="Waiting" value={k.waiting} detail="On building, city or vendors" />
        <Kpi tone="ic-warn" icon="shield" label="Licences" value={k.licences_expiring} detail="Expiring within 60 days" />
        <Kpi tone="ic-ok" icon="cart" label="Committed spend" value={money(d.spend?.planned)} detail={d.spend?.late ? `${d.spend.late} deliveries late` : 'Approved orders'} />
      </div>

      <section>
        <div className="row" style={{ marginBottom: 14 }}><h2 style={{ fontSize: 17 }}>Portfolio</h2><span className="muted sm">{d.properties.length} properties</span><span className="spacer" />
          <button className="btn ghost small" type="button" onClick={() => nav('/properties')}>View all →</button></div>
        <div className="portfolio stagger">
          {d.properties.map(p => (
            <button key={p.id} type="button" className="pcard" onClick={() => nav(`/properties/${p.id}`)}>
              <div className="ph">
                {p.cover_url ? <img src={p.cover_url} alt="" loading="lazy" /> : <PhotoPlaceholder p={p} />}
                <Pill map={STATE} value={p.state} />
                <span className="ring-wrap"><Ring pct={p.progress} size={44} stroke={4} /></span>
              </div>
              <div className="pb">
                <span className="mono">{p.nickname}</span>
                <b>{p.listing_title || p.address}</b>
                <span className="step">{p.current_step ? <>Step {p.current_step.number} · {p.current_step.name}</> : <><Icon name="checkc" small />Live on Airbnb, Booking.com and direct</>}</span>
                <div className="dots12" aria-label={`${p.progress}% complete`}>{(p.step_statuses || []).map((s, i) => <i key={i} className={s} />)}</div>
              </div>
            </button>
          ))}
        </div>
      </section>

      <div className="cols">
        <div style={{ display: 'grid', gap: 24 }}>
          <section className="card">
            <div className="card-h"><h2>Pipeline</h2><span className="sub">Where every property is right now</span></div>
            <div className="funnel">{d.pipeline.map(s => <div key={s.stage} className={s.stage === 'Live' ? 'live' : ''}><b><CountUp value={s.count} /></b><span>{s.stage}</span></div>)}</div>
          </section>
          <section className="card">
            <div className="card-h"><h2>Your agents</h2><span className="sub">Working in the background; anything that leaves the company waits for approval</span></div>
            <div className="card-b agents-row">{AGENTS.map(([name, icon, text]) => (
              <div className="agent-card" key={name}>
                <div className="head"><span className="orb"><Icon name={icon} small /></span><b className="sm">{name}</b><span className="status"><i />Ready</span></div>
                <p>{text}</p>
              </div>))}</div>
          </section>
          <section className="card">
            <div className="card-h"><h2>Recent activity</h2></div>
            <ul className="feed2">{(d.activity || []).slice(0, 6).map(a => {
              const agent = /agent|operations/i.test(a.actor)
              return <li key={a.id} style={{ cursor: 'pointer' }} onClick={() => nav(`/properties/${a.property}`)}>
                <span className={`av ${agent ? 'agent' : ''}`}><Icon name={agent ? 'bot' : 'user'} small /></span>
                <div><p><b>{a.actor}</b> · {a.message}</p><small><span className="mono">{a.nickname}</span> · {ago(a.created_at)}</small></div>
              </li>
            })}{!d.activity?.length && <li><span /><p className="muted">No activity yet.</p></li>}</ul>
          </section>
        </div>

        <div className="sticky" style={{ display: 'grid', gap: 24 }}>
          <section className="card">
            <div className="card-h"><h2>Needs attention</h2><span className="spacer" /><span className={`pill ${d.attention.length ? 'p-bad' : 'p-ok'} nodot`}>{d.attention.length}</span></div>
            <ul className="att">
              {d.attention.map((a, i) => (
                <li key={i} style={{ cursor: 'pointer' }} onClick={() => nav(`/properties/${a.property}`)}>
                  <div className={`kpi-ic ${ATT[a.kind][0]}`}><Icon name={ATT[a.kind][1]} small /></div>
                  <div><b className="mono">{a.nickname}</b><p>{a.text}</p></div>
                </li>
              ))}
              {!d.attention.length && <li><div className="kpi-ic ic-ok"><Icon name="checkc" small /></div><div><p>All clear.</p></div></li>}
            </ul>
          </section>
          <section className="card">
            <div className="card-h"><h2>This week</h2><span className="spacer" /><button className="btn ghost small" type="button" onClick={() => nav('/schedule')}>Schedule →</button></div>
            <ul className="att">
              {(d.visits || []).map(v => (
                <li key={v.id} style={{ cursor: 'pointer' }} onClick={() => nav(`/properties/${v.property}`)}>
                  <div className="kpi-ic ic-acc"><Icon name={VISIT_ICON[v.kind] || 'cal'} small /></div>
                  <div><b className="sm">{v.kind_label}</b> <span className="muted sm">· {fmtDate(v.date)}{v.time ? `, ${v.time}` : ''}</span><p><span className="mono">{v.nickname}</span>{v.assigned_to ? ` · ${v.assigned_to}` : ''}</p></div>
                </li>
              ))}
              {!d.visits?.length && <li><div className="kpi-ic ic-info"><Icon name="cal" small /></div><div><p>Nothing booked in the next 7 days.</p></div></li>}
            </ul>
          </section>
        </div>
      </div>
    </>
  )
}
