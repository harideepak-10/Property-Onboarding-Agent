import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtDate, money } from '../api'
import { Icon, useToast } from './ui'

export const PSTATUS = [['to_buy', 'To buy'], ['ordered', 'Ordered'], ['shipped', 'Shipped'], ['delivered', 'Delivered'], ['missing', 'Missing'], ['damaged', 'Damaged'], ['returned', 'Returned']]
export const PTONE = { to_buy: 'p-info', ordered: 'p-acc', shipped: 'p-acc', delivered: 'p-ok', missing: 'p-bad', damaged: 'p-bad', returned: 'p-warn' }

/** One row per purchased line. Rows come from /purchasing/ (cross-property) or an order's lines. */
export default function PurchaseTable({ rows, onRow, showProperty }) {
  const toast = useToast()
  const [open, setOpen] = useState(null)
  const save = async (r, data, msg) => {
    try { const nr = await api.trackLine(r.id, data); onRow?.(nr); if (msg) toast(msg) } catch (e) { toast(e.message) }
  }
  const receipt = async (r, file) => {
    try { const nr = await api.uploadReceipt(r.id, file); onRow?.(nr); toast('Receipt attached.') } catch (e) { toast(e.message) }
  }
  if (!rows.length) return <div className="card-b muted sm">Nothing here. Lines appear once an order is approved.</div>
  return (
    <div className="table-wrap"><table className="tight">
      <thead><tr>{showProperty && <th>Property</th>}<th>Item</th><th className="r">Qty</th><th>Store</th><th>Status</th><th>Store order #</th><th>Expected</th><th className="r">Paid</th><th /></tr></thead>
      <tbody>{rows.map(r => [
        <tr key={r.id} className={r.late || ['missing', 'damaged'].includes(r.purchase_status) ? 'flag' : ''}>
          {showProperty && <td><Link className="mono sm" to={`/properties/${r.property}`}>{r.nickname}</Link></td>}
          <td style={{ minWidth: 200 }}><a className="sm" href={r.link} target="_blank" rel="noreferrer"><b>{r.name}</b></a>
            {r.notes && <div className="muted sm">{r.notes}</div>}
            {r.order_kind === 'top_up' && <span className="pill p-warn nodot" style={{ marginTop: 4 }}>Top-up</span>}</td>
          <td className="r num sm">{r.quantity_received != null && r.quantity_received !== r.quantity ? `${r.quantity_received}/` : ''}{r.quantity}</td>
          <td className="sm">{r.store_name}</td>
          <td><select className={`pstatus ${PTONE[r.purchase_status]}`} value={r.purchase_status}
            onChange={e => save(r, { purchase_status: e.target.value })} aria-label={`${r.name} status`}>{PSTATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            {r.late && <div className="sm" style={{ color: 'var(--bad)' }}>Late</div>}</td>
          <td className="mono sm">{r.store_order_number || '—'}</td>
          <td className="sm">{r.purchase_status === 'delivered' ? `✓ ${fmtDate(r.delivered_at)}` : fmtDate(r.expected_delivery)}</td>
          <td className="r num sm">{r.purchase_status === 'to_buy' ? '—' : money(r.actual_total)}{r.receipt_url && <> <a href={r.receipt_url} target="_blank" rel="noreferrer" title="Receipt"><Icon name="file" small /></a></>}</td>
          <td><button className="btn ghost small" style={{ padding: '0 6px' }} onClick={() => setOpen(open === r.id ? null : r.id)} aria-label="Edit details">{open === r.id ? '▴' : '▾'}</button></td>
        </tr>,
        open === r.id && <tr key={r.id + 'd'}><td colSpan={showProperty ? 9 : 8}><LineDetails r={r} onSave={(d) => save(r, d, 'Saved.')} onReceipt={(f) => receipt(r, f)} /></td></tr>,
      ])}</tbody></table></div>
  )
}

function LineDetails({ r, onSave, onReceipt }) {
  const [f, setF] = useState({ store_order_number: r.store_order_number, actual_unit_price: r.actual_unit_price ?? '', quantity_received: r.quantity_received ?? '',
    ordered_at: r.ordered_at || '', expected_delivery: r.expected_delivery || '', delivered_at: r.delivered_at || '', purchase_notes: r.notes })
  const set = k => e => setF({ ...f, [k]: e.target.value })
  return (
    <form className="form-grid" style={{ padding: '6px 0 10px' }} onSubmit={e => { e.preventDefault(); onSave(f) }}>
      <div className="field"><label>Store order #</label><input value={f.store_order_number} onChange={set('store_order_number')} /></div>
      <div className="field"><label>Paid per unit (cart {money(r.unit_price)})</label><input type="number" step="0.01" value={f.actual_unit_price} onChange={set('actual_unit_price')} /></div>
      <div className="field"><label>Received (of {r.quantity})</label><input type="number" min="0" value={f.quantity_received} onChange={set('quantity_received')} /></div>
      <div className="field"><label>Ordered</label><input type="date" value={f.ordered_at} onChange={set('ordered_at')} /></div>
      <div className="field"><label>Expected</label><input type="date" value={f.expected_delivery} onChange={set('expected_delivery')} /></div>
      <div className="field"><label>Delivered</label><input type="date" value={f.delivered_at} onChange={set('delivered_at')} /></div>
      <div className="field" style={{ gridColumn: '1/-1' }}><label>Notes</label><input value={f.purchase_notes} onChange={set('purchase_notes')} /></div>
      <div className="row" style={{ gridColumn: '1/-1' }}><button className="btn small primary" type="submit">Save</button>
        <label className="btn small"><Icon name="upload" small />Receipt<input type="file" hidden onChange={e => e.target.files[0] && onReceipt(e.target.files[0])} /></label></div>
    </form>
  )
}
