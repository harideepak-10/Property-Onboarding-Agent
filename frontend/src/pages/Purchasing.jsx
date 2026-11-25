import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, downloadText, money } from '../api'
import { ErrorBox, Icon, Kpi, Loading } from '../components/ui'
import PurchaseTable, { PSTATUS } from '../components/PurchaseTable'

export default function Purchasing() {
  const [d, setD] = useState(null)
  const [props, setProps] = useState([])
  const [stores, setStores] = useState([])
  const [f, setF] = useState({ property: '', store: '', status: '', q: '', late: '' })
  const [err, setErr] = useState(null)
  const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v))
  const load = () => api.purchasing(params).then(setD).catch(setErr)
  useEffect(() => { api.properties().then(setProps).catch(() => {}); api.stores().then(setStores).catch(() => {}) }, [])
  useEffect(() => { load() }, [JSON.stringify(f)])
  const set = k => e => setF({ ...f, [k]: e.target.type === 'checkbox' ? (e.target.checked ? '1' : '') : e.target.value })
  const csv = async () => { try { downloadText(await api.purchasingCsv(params), 'purchasing.csv') } catch (e) { setErr(e) } }

  if (!d) return err ? <ErrorBox error={err} /> : <Loading />
  const c = d.counts
  const planned = d.by_property.reduce((a, r) => a + +r.planned, 0)
  const spent = d.by_property.reduce((a, r) => a + +r.spent, 0)
  return (
    <>
      <div className="page-head"><div><h1>Purchasing</h1><p>Every item bought for every property: where from, order number, and whether it arrived.</p></div><span className="spacer" />
        <button className="btn" onClick={csv}><Icon name="download" small />Export CSV</button></div>
      <ErrorBox error={err} />
      <div className="kpis">
        <Kpi tone="ic-warn" icon="cart" label="To buy" value={c.to_buy} detail="Approved, not ordered yet" />
        <Kpi tone="ic-acc" icon="truck" label="On the way" value={c.ordered + c.shipped} detail={`${d.late} late`} />
        <Kpi tone="ic-ok" icon="checkc" label="Delivered" value={c.delivered} detail={`${d.rows.length} lines shown`} />
        <Kpi tone="ic-bad" icon="alert" label="Missing / damaged" value={c.missing + c.damaged + c.returned} detail="Roll into a top-up order" />
      </div>
      <div className="cols">
        <section className="card">
          <div className="card-b filters row" style={{ gap: 8, borderBottom: '1px solid var(--line-2)' }}>
            <input className="input" placeholder="Search items" value={f.q} onChange={set('q')} aria-label="Search items" style={{ maxWidth: 200 }} />
            <select className="input mono" value={f.property} onChange={set('property')} aria-label="Property" style={{ maxWidth: 210 }}><option value="">All properties</option>{props.map(p => <option key={p.id} value={p.id}>{p.nickname}</option>)}</select>
            <select className="input" value={f.store} onChange={set('store')} aria-label="Store" style={{ maxWidth: 150 }}><option value="">All stores</option>{stores.map(s => <option key={s.code} value={s.code}>{s.name}</option>)}</select>
            <select className="input" value={f.status} onChange={set('status')} aria-label="Status" style={{ maxWidth: 160 }}><option value="">Any status</option>
              <option value="to_buy,ordered,shipped">Not delivered</option>{PSTATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            <label className="row sm" style={{ gap: 6 }}><input type="checkbox" checked={!!f.late} onChange={set('late')} />Late only</label>
          </div>
          <PurchaseTable rows={d.rows} showProperty onRow={load} />
        </section>
        <div className="sticky">
          <section className="card">
            <div className="card-h"><h2>By property</h2></div>
            <div className="card-b" style={{ display: 'grid', gap: 10 }}>
              {d.by_property.map(r => <div key={r.nickname}>
                <div className="sum-row" style={{ padding: 0 }}><Link className="mono sm" to={`/properties/${r.property}`}>{r.nickname}</Link><span className="num sm">{r.delivered}/{r.lines}</span></div>
                <div className={`bar ${r.delivered === r.lines ? "done" : ""}`} style={{ margin: "4px 0" }}><i style={{ width: `${r.lines ? r.delivered / r.lines * 100 : 0}%` }} /></div>
                <div className="muted sm">Cart {money(r.planned)} · paid {money(r.spent)}{r.late ? ` · ${r.late} late` : ''}{r.problems ? ` · ${r.problems} problem` : ''}</div>
              </div>)}
              {!d.by_property.length && <span className="muted sm">No approved orders.</span>}
              {d.by_property.length > 0 && <div className="sum-row total"><span>Total</span><span className="num">{money(planned)}</span></div>}
              {d.by_property.length > 0 && <div className="muted sm">Paid so far {money(spent)}</div>}
            </div>
          </section>
          <section className="card">
            <div className="card-h"><h2>By store</h2></div>
            <div className="card-b">{d.by_store.map(s => <div key={s.store} className="sum-row"><span className="muted">{s.store}</span><span className="num sm">{money(s.planned)}{s.open ? <span className="muted"> · {s.open} open</span> : ''}</span></div>)}</div>
          </section>
        </div>
      </div>
    </>
  )
}
