import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, money } from '../../api'
import { ErrorBox, Icon, Loading } from '../../components/ui'
import PurchaseTable from '../../components/PurchaseTable'

export default function PurchasesTab({ p, onSaved }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const load = () => api.purchasing({ property: p.id }).then(setD).catch(setErr)
  useEffect(() => { load() }, [p.id])
  if (!d) return err ? <ErrorBox error={err} /> : <Loading />
  const s = d.by_property[0]
  const problems = d.counts.missing + d.counts.damaged + d.counts.returned
  return (
    <section className="card">
      <div className="card-h"><h2>What was bought</h2><span className="sub">Every approved order line, where from, and whether it arrived</span><span className="spacer" />
        <Link className="btn small" to={`/procurement/${p.id}`}><Icon name="cart" small />Orders</Link></div>
      {s && <div className="card-b row" style={{ gap: 8 }}>
        <span className="pill p-ok">{d.counts.delivered}/{s.lines} delivered</span>
        {d.late > 0 && <span className="pill p-bad">{d.late} late</span>}
        {problems > 0 && <span className="pill p-warn">{problems} missing/damaged</span>}
        <span className="pill p-info nodot">Cart {money(s.planned)} · paid {money(s.spent)}</span>
        {problems > 0 && <Link className="sm" to={`/procurement/${p.id}?topup=1`}>Start a top-up order →</Link>}
      </div>}
      <PurchaseTable rows={d.rows} onRow={() => { load(); onSaved?.() }} />
    </section>
  )
}
