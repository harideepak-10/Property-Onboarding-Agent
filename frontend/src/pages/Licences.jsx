import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import AgentRun from '../components/AgentRun'
import { ErrorBox, Icon, Kpi, Loading, useToast } from '../components/ui'

const STATUS = { approved: 'p-ok', submitted: 'p-warn', returned: 'p-bad', not_started: 'p-info', expired: 'p-bad' }

export default function Licences() {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState(null)
  const [run, setRun] = useState(null)
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()
  const toast = useToast()
  const load = () => api.licences().then(setRows).catch(setErr)
  useEffect(() => { load() }, [])

  const sweep = async () => {
    setBusy(true)
    try { const r = await api.runSweeps(); setRun(r); toast('Daily checks finished. New drafts are in Approvals.'); load() } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  if (!rows) return err ? <ErrorBox error={err} /> : <Loading />
  const expiring = rows.filter(r => r.days_left !== null && r.days_left <= 60 && r.days_left >= 0).length
  return (
    <>
      <div className="page-head"><div><h1>STR licences</h1><p>One licence and one unique email per unit. The Compliance agent tracks packets, expiry and renewals.</p></div><span className="spacer" />
        <button className="btn" type="button" disabled={busy} onClick={sweep}>{busy ? <span className="spin" /> : <Icon name="clock" small />}Run daily checks now</button></div>
      <ErrorBox error={err} />
      <div className="kpis">
        <Kpi tone="ic-ok" icon="shield" label="Approved" value={rows.filter(r => r.status === 'approved').length} detail="Active licences" />
        <Kpi tone="ic-warn" icon="clock" label="In review" value={rows.filter(r => r.status === 'submitted').length} detail="Submitted to the City" />
        <Kpi tone="ic-bad" icon="alert" label="Returned or expired" value={rows.filter(r => ['returned', 'expired'].includes(r.status)).length} detail="Need action" />
        <Kpi tone="ic-warn" icon="cal" label="Expiring" value={expiring} detail="Within 60 days" />
      </div>
      {run && <section className="card"><div className="card-b"><AgentRun run={run} animate /></div></section>}
      <section className="card">
        <div className="table-wrap"><table>
          <thead><tr><th>Unit</th><th>Status</th><th>Licence no.</th><th>Expiry</th><th>Licence packet</th><th>Unit email</th></tr></thead>
          <tbody>{rows.map(r => (
            <tr key={r.property} className="click" tabIndex={0} onClick={() => nav(`/properties/${r.property}`)} onKeyDown={e => e.key === 'Enter' && nav(`/properties/${r.property}`)}>
              <td><b className="mono sm">{r.nickname}</b><div className="muted sm">{r.address}</div></td>
              <td><span className={`pill ${STATUS[r.status]}`}>{r.status_label}</span></td>
              <td className="mono sm">{r.number || '—'}</td>
              <td className="num sm">{r.expires_on ? <>{r.expires_on}<div className={r.days_left <= 30 ? '' : 'muted'} style={r.days_left <= 30 ? { color: 'var(--bad)', fontWeight: 600 } : {}}>{r.days_left < 0 ? 'Expired' : `${r.days_left} days left`}</div></> : '—'}</td>
              <td><div className="row sm" style={{ gap: 8, flexWrap: 'nowrap' }}><div className={`bar ${r.packet.total && r.packet.ready === r.packet.total ? 'done' : ''}`} style={{ width: 80 }}><i style={{ width: `${r.packet.total ? r.packet.ready / r.packet.total * 100 : 0}%` }} /></div><span className="muted num">{r.packet.ready}/{r.packet.total}</span></div></td>
              <td className="mono sm">{r.unit_email || <span className="muted">Not created</span>}</td>
            </tr>))}</tbody></table></div>
      </section>
    </>
  )
}
