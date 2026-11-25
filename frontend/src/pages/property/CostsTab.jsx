import { useEffect, useState } from 'react'
import { api, fmtDate, money } from '../../api'
import { ErrorBox, Icon, Loading, useToast } from '../../components/ui'

const CATS = [['licence', 'Licence / permits'], ['inspection', 'Inspection'], ['repair', 'Repairs'], ['cleaning', 'Cleaning'], ['photography', 'Photography'], ['labour', 'Setup labour'], ['building', 'Building fees (fobs, parking)'], ['utilities', 'Utilities set-up'], ['delivery', 'Delivery / assembly'], ['other', 'Other']]

export default function CostsTab({ p }) {
  const toast = useToast()
  const [c, setC] = useState(null)
  const [ex, setEx] = useState([])
  const [err, setErr] = useState(null)
  const blank = { category: 'other', description: '', amount: '', date: new Date().toISOString().slice(0, 10), paid_by: '' }
  const [f, setF] = useState(blank)
  const load = () => Promise.all([api.costs(p.id).then(setC), api.expenses(p.id).then(setEx)]).catch(setErr)
  useEffect(() => { load() }, [p.id])
  if (!c) return err ? <ErrorBox error={err} /> : <Loading />
  const set = k => e => setF({ ...f, [k]: e.target.value })
  const add = async (e) => {
    e.preventDefault()
    try { await api.addExpense({ ...f, property: p.id }); setF(blank); toast('Expense added.'); load() } catch (e2) { setErr(e2) }
  }
  const del = async (x) => { try { await api.deleteExpense(x.id); load() } catch (e) { setErr(e) } }
  const pu = c.purchases
  const budget = +pu.budget
  return (
    <div className="cols">
      <div style={{ display: 'grid', gap: 18 }}>
        <ErrorBox error={err} />
        <section className="card">
          <div className="card-h"><h2>Expenses</h2><span className="sub">Everything that isn't a store purchase</span></div>
          <div className="table-wrap"><table className="tight">
            <thead><tr><th>Date</th><th>Category</th><th>Description</th><th>Paid by</th><th className="r">Amount</th><th /></tr></thead>
            <tbody>{ex.map(x => <tr key={x.id}><td className="sm">{fmtDate(x.date)}</td><td className="sm">{x.category_label}</td>
              <td className="sm">{x.description}{x.from_visit && <span className="muted"> · from schedule</span>}{x.receipt_url && <> <a href={x.receipt_url} target="_blank" rel="noreferrer">receipt</a></>}</td>
              <td className="sm">{x.paid_by}</td><td className="r num sm"><b>{money(x.amount)}</b></td>
              <td>{!x.from_visit && <button className="btn ghost small" style={{ padding: '0 6px' }} onClick={() => del(x)} aria-label="Delete expense">×</button>}</td></tr>)}
              {!ex.length && <tr><td colSpan={6} className="muted sm">No expenses yet.</td></tr>}</tbody></table></div>
          <form className="card-b form-grid" style={{ borderTop: '1px solid var(--line-2)' }} onSubmit={add}>
            <div className="field"><label htmlFor="ec">Category</label><select id="ec" value={f.category} onChange={set('category')}>{CATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
            <div className="field"><label htmlFor="ed">Description</label><input id="ed" required value={f.description} onChange={set('description')} /></div>
            <div className="field"><label htmlFor="ea">Amount ($)</label><input id="ea" type="number" step="0.01" required value={f.amount} onChange={set('amount')} /></div>
            <div className="field"><label htmlFor="edt">Date</label><input id="edt" type="date" required value={f.date} onChange={set('date')} /></div>
            <div className="field"><label htmlFor="ep">Paid by</label><input id="ep" value={f.paid_by} onChange={set('paid_by')} placeholder="Company card, owner…" /></div>
            <div className="row" style={{ alignSelf: 'end' }}><button className="btn primary" type="submit"><Icon name="plus" small />Add expense</button></div>
          </form>
        </section>
        {Object.keys(c.by_store).length > 0 && <section className="card">
          <div className="card-h"><h2>Purchases by store</h2></div>
          <div className="card-b">{Object.entries(c.by_store).map(([s, v]) => <div className="sum-row" key={s}><span className="muted">{s}</span><span className="num">{money(v)}</span></div>)}</div>
        </section>}
      </div>
      <div className="sticky">
        <section className="card">
          <div className="card-h"><h2>Onboarding cost</h2></div>
          <div className="card-b">
            <div className="sum-row"><span className="muted">Furniture and supplies</span><span className="num">{money(pu.planned)}</span></div>
            <div className="sum-row"><span className="muted">· paid so far</span><span className="num">{money(pu.spent)}</span></div>
            <div className="sum-row"><span className="muted">Decor</span><span className="num">{money(pu.decor)}</span></div>
            {Object.entries(c.expenses).map(([k, v]) => <div className="sum-row" key={k}><span className="muted">{k}</span><span className="num">{money(v)}</span></div>)}
            <div className="sum-row total"><span>Total</span><span className="num">{money(c.total)}</span></div>
            {budget > 0 && <div className="sum-row"><span className="muted">Budget</span><span className="num" style={{ color: +c.purchase_total > budget ? 'var(--bad)' : 'var(--ok)' }}>{money(budget)}</span></div>}
            <div className="muted sm">CAD before tax · {c.orders} approved order{c.orders === 1 ? '' : 's'}</div>
          </div>
        </section>
        <section className="card"><div className="card-b">
          <div className="sum-row"><span className="muted">Monthly utilities</span><b className="num">{money(c.monthly_utilities)}</b></div>
          <div className="muted sm">Running cost, not part of onboarding. Set on the Unit tab.</div></div></section>
      </div>
    </div>
  )
}
