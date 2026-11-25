import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, money } from '../api'
import { ErrorBox, Icon, Kpi, Loading, useCan, useToast } from '../components/ui'

export default function Reports() {
  const toast = useToast()
  const [d, setD] = useState(null)
  const [dg, setDg] = useState(null)
  const [err, setErr] = useState(null)
  const canSend = useCan('send_emails')
  useEffect(() => { api.reports().then(setD).catch(setErr); api.digest().then(setDg).catch(() => {}) }, [])
  if (!d) return err ? <ErrorBox error={err} /> : <Loading />
  const { costs, timeline } = d
  const maxDays = Math.max(1, ...timeline.steps.map(s => s.avg_step_days || 0))
  const send = async () => {
    try { const r = await api.sendDigest(); toast(r.some(n => n.dry_run) ? 'Digest prepared (dry run until Gmail is connected).' : 'Digest sent.'); setDg(await api.digest()) } catch (e) { setErr(e) }
  }
  const slowest = [...timeline.steps].filter(s => s.avg_step_days != null).sort((a, b) => b.avg_step_days - a.avg_step_days)[0]
  return (
    <>
      <div className="page-head"><div><h1>Reports</h1><p>What onboarding costs per property, and how long each step takes.</p></div></div>
      <ErrorBox error={err} />
      <div className="kpis">
        <Kpi tone="ic-acc" icon="dollar" label="Average cost" value={money(costs.average)} detail="Per property with costs" />
        <Kpi tone="ic-info" icon="clock" label="Agreement → live" value={timeline.avg_total_days != null ? `${timeline.avg_total_days} days` : '—'} detail="Average for live properties" />
        <Kpi tone="ic-warn" icon="alert" label="Slowest step" value={slowest ? `${slowest.avg_step_days} d` : '—'} detail={slowest?.name || 'Not enough data yet'} />
        <Kpi tone="ic-ok" icon="home" label="Properties" value={timeline.properties.length} detail={`${timeline.properties.filter(p => p.progress === 100).length} live`} />
      </div>
      <div className="cols">
        <div style={{ display: 'grid', gap: 18 }}>
          <section className="card">
            <div className="card-h"><h2>Cost per property</h2><span className="sub">Purchases (cart or paid price) + expenses</span></div>
            <div className="table-wrap"><table>
              <thead><tr><th>Property</th><th className="r">Purchases</th><th className="r">Expenses</th><th className="r">Total</th><th className="r">Budget</th></tr></thead>
              <tbody>{costs.rows.map(r => <tr key={r.property}><td><Link className="mono sm" to={`/properties/${r.property}`}>{r.nickname}</Link></td>
                <td className="r num sm">{money(r.purchases)}</td><td className="r num sm">{money(r.expenses)}</td><td className="r num"><b>{money(r.total)}</b></td>
                <td className="r num sm" style={{ color: +r.budget && +r.purchases > +r.budget ? 'var(--bad)' : undefined }}>{+r.budget ? money(r.budget) : '—'}</td></tr>)}</tbody></table></div>
          </section>
          <section className="card">
            <div className="card-h"><h2>Time per step</h2><span className="sub">Average days each step takes, from completed properties</span></div>
            <div className="card-b" style={{ display: 'grid', gap: 10 }}>{timeline.steps.map(s => <div key={s.number} style={{ display: 'grid', gridTemplateColumns: '220px 1fr 80px', gap: 12, alignItems: 'center' }}>
              <span className="sm"><b>{s.number}.</b> {s.name}<div className="muted sm">{s.owner}</div></span>
              <div className="bar"><i style={{ width: `${(s.avg_step_days || 0) / maxDays * 100}%` }} /></div>
              <span className="num sm r">{s.avg_step_days != null ? `${s.avg_step_days} d` : <span className="muted">no data</span>}</span></div>)}
              <div className="muted sm">Measured from when the property was created to when each step was finished. Gets more accurate as more units go live.</div></div>
          </section>
          <section className="card">
            <div className="card-h"><h2>Where each property is</h2></div>
            <div className="table-wrap"><table>
              <thead><tr><th>Property</th><th>Current step</th><th className="r">Progress</th><th className="r">Days since start</th></tr></thead>
              <tbody>{timeline.properties.map(p => <tr key={p.property}><td><Link className="mono sm" to={`/properties/${p.property}`}>{p.nickname}</Link></td><td className="sm">{p.current}</td>
                <td className="r num sm">{p.progress}%</td><td className="r num sm">{p.days_open}</td></tr>)}</tbody></table></div>
          </section>
        </div>
        <div className="sticky">
          <section className="card">
            <div className="card-h"><h2>Daily digest</h2><span className="spacer" />{canSend && <button className="btn small" onClick={send}><Icon name="send" small />Send now</button>}</div>
            <div className="card-b" style={{ display: 'grid', gap: 10 }}>
              <span className="muted sm">Emailed to the ops inbox each morning by the daily check (and to Slack if a webhook is set).</span>
              {dg && <pre className="sm" style={{ whiteSpace: 'pre-wrap', margin: 0, background: 'var(--surface-2)', padding: 12, borderRadius: 8, fontFamily: 'inherit' }}>{dg.preview}</pre>}
              {dg?.recent?.length > 0 && <span className="muted sm">Last sent {new Date(dg.recent[0].sent_at).toLocaleString('en-CA')}{dg.recent[0].dry_run ? ' (dry run)' : ''} by {dg.recent[0].channel}</span>}
            </div>
          </section>
        </div>
      </div>
    </>
  )
}
