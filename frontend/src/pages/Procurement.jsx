import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, money } from '../api'
import { ErrorBox, Icon, Loading, useToast } from '../components/ui'

const CATEGORY = { furniture: 'Furniture (step 5)', kitchen: 'Kitchen', bath: 'Bath', bedroom: 'Bedroom', living: 'Living', electronics: 'Electronics and fixtures', cleaning: 'Cleaning' }
const FLOW = [['draft', 'Calculate', 'Quantities from unit size'], ['checked', 'Check', 'Price and stock at each store'], ['carts_built', 'Carts', 'Staged for your review'], ['approved', 'Approve', 'You check out, doc saved']]
const RANK = { draft: 1, checked: 2, carts_built: 3, approved: 4 }

export default function Procurement() {
  const { propertyId } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const [props, setProps] = useState(null)
  const [order, setOrder] = useState(undefined)
  const [stores, setStores] = useState([])
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState('items')

  useEffect(() => { api.properties().then(setProps).catch(setErr); api.stores().then(setStores).catch(() => {}) }, [])
  const pid = propertyId || props?.find(p => p.state !== 'live')?.id || props?.[0]?.id
  const prop = props?.find(p => String(p.id) === String(pid))

  const loadOrder = useCallback(() => {
    if (!pid) return
    setOrder(undefined)
    api.orders(pid).then(list => setOrder(list[0] || null)).catch(setErr)
  }, [pid])
  useEffect(() => { loadOrder() }, [loadOrder])
  useEffect(() => { if (order?.status === 'approved') setTab('doc'); else if (order?.status === 'carts_built') setTab(t => t === 'items' ? 'carts' : t); else setTab('items') }, [order?.status])

  const run = async (fn, msg) => {
    setBusy(true); setErr(null)
    try { const o = await fn(); setOrder(o); if (msg) toast(msg) } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  if (!props) return err ? <ErrorBox error={err} /> : <Loading />
  if (!props.length) return <div className="card empty">Add a property first.</div>

  return (
    <>
      <div className="page-head"><div><h1>Procurement</h1><p>Master list × unit size → checked carts and one order document per property.</p></div><span className="spacer" />
        <div className="field" style={{ minWidth: 240 }}><label htmlFor="pp">Property</label>
          <select id="pp" className="mono" value={pid || ''} onChange={e => nav(`/procurement/${e.target.value}`)}>
            {props.map(p => <option key={p.id} value={p.id}>{p.nickname}</option>)}</select></div></div>
      <ErrorBox error={err} />
      {order === undefined ? <Loading /> : !order ? <StartOrder prop={prop} busy={busy} onStart={(counts) => run(() => api.createOrder({ property: pid, ...counts }), 'Quantities calculated.')} />
        : <OrderView order={order} stores={stores} tab={tab} setTab={setTab} busy={busy} run={run} prop={prop}
            onNew={() => setOrder(null)} />}
    </>
  )
}

function StartOrder({ prop, busy, onStart }) {
  const [c, setC] = useState({ bedrooms: prop.bedrooms, bathrooms: prop.bathrooms, beds: prop.beds })
  const set = k => e => setC({ ...c, [k]: Math.max(0, parseInt(e.target.value) || 0) })
  return (
    <section className="card">
      <div className="card-h"><h2>Start the order for <span className="mono">{prop.nickname}</span></h2></div>
      <div className="card-b" style={{ display: 'grid', gap: 16, maxWidth: 560 }}>
        <p className="muted" style={{ margin: 0 }}>Quantities come from the master list rules: fixed, per bedroom, per bathroom or per bed. Adjust the counts if the unit differs from the agreement.</p>
        <div className="counts">
          <div className="field"><label htmlFor="sb">Bedrooms</label><input id="sb" type="number" min="0" value={c.bedrooms} onChange={set('bedrooms')} /></div>
          <div className="field"><label htmlFor="sba">Bathrooms</label><input id="sba" type="number" min="1" value={c.bathrooms} onChange={set('bathrooms')} /></div>
          <div className="field"><label htmlFor="sbe">Beds</label><input id="sbe" type="number" min="1" value={c.beds} onChange={set('beds')} /></div>
        </div>
        <button className="btn primary" type="button" disabled={busy} onClick={() => onStart(c)} style={{ justifySelf: 'start' }}><Icon name="list" small />Calculate quantities</button>
      </div>
    </section>
  )
}

function OrderView({ order, stores, tab, setTab, busy, run, prop, onNew }) {
  const toast = useToast()
  const s = order.summary
  const rank = RANK[order.status]
  const approved = order.status === 'approved'
  const cc = order.cross_check
  const linesById = Object.fromEntries(order.lines.map(l => [l.id, l]))

  let cat = ''
  const rows = []
  order.lines.forEach(l => {
    if (l.category !== cat) { cat = l.category; rows.push(<tr className="cat" key={'c' + cat}><td colSpan={7}>{CATEGORY[cat] || cat}</td></tr>) }
    rows.push(<LineRow key={l.id} l={l} approved={approved} busy={busy} onResolve={(r) => run(() => api.resolveLine(l.id, r))}
      onDelete={() => run(() => api.deleteLine(l.id), 'Line removed.')} />)
  })

  const copyDoc = async () => {
    const rows = [['Item', 'Type', 'Qty', 'Store', 'Unit price', 'Line total', 'Link'],
      ...order.lines.filter(l => l.included).map(l => [l.name, l.item_type, l.quantity, l.store_name, l.unit_price, l.line_total, l.link])]
    try { await navigator.clipboard.writeText(rows.map(r => r.join('\t')).join('\n')); toast('Copied. Paste into a Google Sheet.') }
    catch { toast('Copy was blocked by the browser. Use Download CSV instead.') }
  }
  const downloadDoc = async () => {
    const text = await api.orderDocument(order.id)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
    a.download = `${order.property_nickname}-order-${order.id}.csv`
    a.click(); URL.revokeObjectURL(a.href)
  }

  return (
    <>
      <section className="card"><div className="flow">{FLOW.map(([k, t, d], i) => {
        const done = i < rank
        const active = i === rank
        return <div key={k} className={`flow-step ${done ? 'done' : ''} ${active ? 'active' : ''}`}><div className="n">{done ? <Icon name="check" small /> : i + 1}</div><div><b>{t}</b><span>{d}</span></div></div>
      })}</div></section>

      <div className="cols">
        <section className="card">
          <div className="tabs" role="tablist">
            <button className="tab" role="tab" aria-selected={tab === 'items'} onClick={() => setTab('items')}><Icon name="list" small />Item list<span className="cnt">{s.lines}</span></button>
            <button className="tab" role="tab" aria-selected={tab === 'carts'} disabled={rank < 3} onClick={() => setTab('carts')}><Icon name="cart" small />Store carts<span className="cnt">{order.carts.length}</span></button>
            <button className="tab" role="tab" aria-selected={tab === 'doc'} disabled={rank < 3} onClick={() => setTab('doc')}><Icon name="file" small />Order document</button>
          </div>
          {tab === 'items' && <>
            <div className="table-wrap"><table className="tight">
              <thead><tr><th>Item</th><th className="r">Qty</th><th>Store</th><th className="r">Typical</th><th className="r">Current</th><th className="r">Line total</th><th>Check</th></tr></thead>
              <tbody>{rows}</tbody></table></div>
            {!approved && <ManualLineForm stores={stores} onAdd={(d) => run(() => api.addManualLine(order.id, d), 'Item added.')} />}
          </>}
          {tab === 'carts' && <div className="store-carts">{order.carts.map(c => (
            <div className="cart" key={c.store_code}>
              <div className="cart-h"><span className="store-logo" style={{ background: c.color }}>{c.store_name.slice(0, 2).toUpperCase()}</span>
                <div><b className="sm">{c.store_name}</b><div className="muted sm">{c.line_ids.length} line{c.line_ids.length > 1 ? 's' : ''}</div></div><span className="spacer" />
                <span className={`pill ${approved ? 'p-ok' : 'p-warn'}`}>{approved ? 'Ordered' : 'Awaiting review'}</span></div>
              <ul>{c.line_ids.map(id => linesById[id]).map(l => <li key={l.id}><a href={l.link} target="_blank" rel="noreferrer">{l.quantity} × {l.name}</a><span className="num muted">{money(l.line_total)}</span></li>)}</ul>
              <div className="cart-f"><span className="muted">Cart total</span><b className="num">{money(c.total)}</b></div>
              {c.cart_url && <div className="cart-f"><a className="btn small primary" href={c.cart_url} target="_blank" rel="noreferrer"><Icon name="ext" small />Open filled cart</a></div>}
            </div>))}</div>}
          {tab === 'doc' && <>
            <div className="card-b row" style={{ borderBottom: '1px solid var(--line-2)' }}><div><b>Order document</b> <span className="mono muted sm">{order.property_nickname}</span><div className="muted sm">One record per property for reordering</div></div><span className="spacer" />
              <button className="btn" type="button" onClick={copyDoc}><Icon name="copy" small />Copy for Google Sheets</button>
              <button className="btn" type="button" onClick={downloadDoc}><Icon name="download" small />Download CSV</button></div>
            <div className="table-wrap"><table><thead><tr><th>Item</th><th>Type</th><th className="r">Qty</th><th>Store</th><th className="r">Unit price</th><th className="r">Line total</th><th>Link</th></tr></thead>
              <tbody>{order.lines.filter(l => l.included).map(l => <tr key={l.id}><td className="sm"><b>{l.name}</b></td><td className="muted sm">{l.item_type}</td><td className="r num">{l.quantity}</td><td className="sm">{l.store_name}</td><td className="r num sm">{money(l.unit_price)}</td><td className="r num sm"><b>{money(l.line_total)}</b></td><td><a className="sm" href={l.link} target="_blank" rel="noreferrer">Open ↗</a></td></tr>)}
                <tr><td colSpan={5}><b>Total (CAD, before tax)</b></td><td className="r num"><b>{money(s.total)}</b></td><td /></tr></tbody></table></div>
          </>}
        </section>

        <div className="sticky">
          <section className="card">
            <div className="card-h"><h2>Order summary</h2><span className="spacer" /><span className="mono muted sm">{order.property_nickname}</span></div>
            <div className="card-b" style={{ display: 'grid', gap: 12 }}>
              <div className="muted sm">For {order.bedrooms} bd · {order.bathrooms} ba · {order.beds} beds · {order.status_label}</div>
              <div>
                <div className="sum-row"><span className="muted">Order lines</span><b className="num">{s.lines}</b></div>
                <div className="sum-row"><span className="muted">Units to buy</span><b className="num">{s.units}</b></div>
                <div className="sum-row"><span className="muted">Furniture</span><span className="num">{money(s.furniture)}</span></div>
                <div className="sum-row"><span className="muted">Supplies kit</span><span className="num">{money(s.supplies)}</span></div>
                <div className="sum-row"><span className="muted">Decor (separate)</span><span className="num">{money(s.decor)}</span></div>
                <div className="sum-row total"><span>Estimated total</span><span className="num">{money(s.total)}</span></div>
                <div className="muted sm">CAD, before tax and delivery{s.unchecked > 0 ? ` · ${s.unchecked} item${s.unchecked > 1 ? 's' : ''} priced at typical (couldn't check automatically)` : ''}</div>
              </div>
              {order.status === 'draft' && <button className="btn primary" disabled={busy} style={{ justifyContent: 'center' }} onClick={() => run(() => api.checkOrder(order.id), 'Check complete. Review the flagged items.')}><Icon name="checkc" small />Run price and stock check</button>}
              {order.status === 'checked' && <><button className="btn primary" disabled={busy || s.flags_open > 0} style={{ justifyContent: 'center' }} onClick={() => run(() => api.buildCarts(order.id), 'Carts staged for review.')}><Icon name="cart" small />Build store carts</button>
                {s.flags_open > 0 && <div className="muted sm" style={{ textAlign: 'center' }}>Resolve {s.flags_open} flagged item{s.flags_open > 1 ? 's' : ''} first</div>}</>}
              {order.status === 'carts_built' && <><button className="btn primary" disabled={busy || !cc?.ok} style={{ justifyContent: 'center' }} onClick={() => run(() => api.approveOrder(order.id), 'Order approved. Step 6 updated.')}><Icon name="check" small />Approve order</button>
                {!cc?.ok && <div className="muted sm" style={{ textAlign: 'center' }}>Fix the cross-check issues first</div>}</>}
              {approved && <div className="note ok" style={{ margin: 0 }}><Icon name="checkc" small /><span>Approved {new Date(order.approved_at).toLocaleDateString('en-CA')}. The property's step 6 checklist is updated.</span></div>}
              {order.status !== 'draft' && !approved && <button className="btn ghost small" disabled={busy} style={{ justifySelf: 'center' }} onClick={() => run(() => api.checkOrder(order.id), 'Re-checked.')}>Re-run check</button>}
              <button className="btn ghost small" style={{ justifySelf: 'center' }} onClick={onNew}>Start a new order</button>
              <Link className="sm" style={{ justifySelf: 'center' }} to={`/properties/${prop.id}`}>View property checklist →</Link>
            </div>
          </section>
          <section className="card">
            <div className="card-h"><h2>Cross-check by item type</h2></div>
            <div className="card-b">
              {!cc ? <p className="muted sm" style={{ margin: 0 }}>Runs after the price and stock check.</p> : <>
                <div className="row" style={{ gap: 6 }}>
                  <span className={`pill ${cc.missing.length ? 'p-bad' : 'p-ok'}`}>{cc.missing.length} missing</span>
                  <span className={`pill ${Object.keys(cc.duplicates).length ? 'p-warn' : 'p-ok'}`}>{Object.keys(cc.duplicates).length} duplicates</span>
                  <span className="pill p-info nodot">{cc.required} types</span></div>
                {cc.missing.map(t => <div key={t} className="note bad"><Icon name="alert" small /><span>No <b>{t}</b> in any cart.</span></div>)}
                {Object.entries(cc.duplicates).map(([t, ids]) => <div key={t} className="note warn"><Icon name="copy" small /><div>Duplicate <b>{t}</b>: {ids.map(id => `${linesById[id]?.name} (${linesById[id]?.store_name})`).join(' and ')}.
                  {ids.map(id => linesById[id]).filter(l => l?.source === 'manual').map(l => <div key={l.id} style={{ marginTop: 8 }}><button className="btn small" disabled={busy} onClick={() => run(() => api.deleteLine(l.id), 'Removed.')}>Remove the team-added one</button></div>)}</div></div>)}
                {cc.ok && <div className="note ok"><Icon name="checkc" small /><span>Every required item type is covered exactly once.</span></div>}
              </>}
            </div>
          </section>
          <DecorCard order={order} busy={busy} run={run} />
        </div>
      </div>
    </>
  )
}

function LineRow({ l, approved, busy, onResolve, onDelete }) {
  let check = <span className="pill p-info nodot">Not checked</span>
  if (l.current_price !== null) {
    if (l.needs_decision) check = <span className="pill p-bad">{l.flag}</span>
    else if (l.resolution === 'remove') check = <span className="pill p-info">Removed</span>
    else if (l.replaced_from) check = <span className="pill p-ok">Replaced</span>
    else if (l.resolution === 'keep') check = <span className="pill p-warn">Kept, over price</span>
    else check = <span className="pill p-ok">In stock</span>
  }
  if (l.check_note && l.current_price === null && !l.needs_decision && l.resolution !== 'remove') {
    check = <span className="pill p-warn nodot">Check by hand</span>
  }
  return (
    <tr className={`${l.needs_decision ? 'flag' : ''} ${!l.included ? 'zero' : ''}`}>
      <td style={{ minWidth: 220 }}>
        <b className="sm">{l.replaced_from || l.name}</b>
        {l.replaced_from && <div className="sm" style={{ color: 'var(--ok)' }}>→ {l.name}</div>}
        {l.check_note && <div className="sm" style={{ color: 'var(--warn)' }}>{l.check_note}</div>}
        <div className="muted sm">{l.source === 'manual' ? 'Added by team' : `${l.rule?.label}${l.rule?.multiplier > 1 ? ` × ${l.rule.multiplier}` : ''}`} · type: {l.item_type}
          {l.source === 'manual' && !approved && <> · <button className="btn ghost small" style={{ padding: '0 6px' }} disabled={busy} onClick={onDelete}>Delete</button></>}</div>
        {l.needs_decision && !approved && (
          <div className="note warn" style={{ marginTop: 8 }}><Icon name="info" small /><div>
            {l.alternative ? <>Suggested replacement: <b>{l.alternative.name}</b> · {l.alternative.store} · {money(l.alternative.price)}</> : 'No approved replacement in the master list.'}
            <div className="row" style={{ gap: 6, marginTop: 8 }}>
              {l.alternative && <button className="btn small" disabled={busy} onClick={() => onResolve('replace')}>Use replacement</button>}
              {l.in_stock && <button className="btn small" disabled={busy} onClick={() => onResolve('keep')}>Keep at this price</button>}
              <button className="btn small ghost" disabled={busy} onClick={() => onResolve('remove')}>Remove</button>
            </div></div></div>
        )}
      </td>
      <td className="r num"><b>{l.quantity}</b></td>
      <td><a className="sm" href={l.link} target="_blank" rel="noreferrer">{l.store_name}</a></td>
      <td className="r num muted sm">{money(l.typical_price)}</td>
      <td className="r num sm">{l.current_price !== null ? money(l.current_price) : '—'}</td>
      <td className="r num sm"><b>{l.included ? money(l.line_total) : '—'}</b></td>
      <td>{check}</td>
    </tr>
  )
}

function ManualLineForm({ stores, onAdd }) {
  const [f, setF] = useState({ name: '', item_type: '', store_code: 'amazon', price: '', quantity: 1 })
  const set = k => e => setF({ ...f, [k]: e.target.value })
  return (
    <form className="card-b" style={{ borderTop: '1px solid var(--line-2)' }} onSubmit={e => { e.preventDefault(); onAdd({ ...f, quantity: +f.quantity || 1 }); setF({ ...f, name: '', item_type: '', price: '' }) }}>
      <b className="sm">Add an item by hand</b>
      <div className="inline-form">
        <input className="input" placeholder="Item name" value={f.name} onChange={set('name')} required aria-label="Item name" />
        <input className="input" placeholder="Type (e.g. kettle)" value={f.item_type} onChange={set('item_type')} required aria-label="Item type" style={{ maxWidth: 170 }} />
        <select className="input" value={f.store_code} onChange={set('store_code')} aria-label="Store" style={{ maxWidth: 140 }}>{stores.map(s => <option key={s.code} value={s.code}>{s.name}</option>)}</select>
        <input className="input" placeholder="Price" type="number" step="0.01" value={f.price} onChange={set('price')} aria-label="Price" style={{ maxWidth: 100 }} />
        <input className="input" type="number" min="1" value={f.quantity} onChange={set('quantity')} aria-label="Quantity" style={{ maxWidth: 80 }} />
        <button className="btn small" type="submit">Add</button>
      </div>
    </form>
  )
}

function DecorCard({ order, busy, run }) {
  const [name, setName] = useState('')
  const [price, setPrice] = useState('')
  return (
    <section className="card">
      <div className="card-h"><h2>Decor</h2><span className="sub">Picked by hand, never auto-added</span></div>
      <div className="card-b" style={{ display: 'grid', gap: 10 }}>
        {order.decor.map(d => <div key={d.id} className="sum-row" style={{ padding: 0 }}><span className="sm">{d.name}</span><span className="row" style={{ gap: 8 }}><span className="num sm">{money(d.price)}</span>
          <button className="btn ghost small" style={{ padding: '0 6px' }} disabled={busy} onClick={() => run(() => api.deleteDecor(d.id))} aria-label={`Remove ${d.name}`}>×</button></span></div>)}
        {!order.decor.length && <span className="muted sm">No decor added yet.</span>}
        <form className="row" style={{ gap: 8, flexWrap: 'nowrap' }} onSubmit={e => { e.preventDefault(); if (!name.trim()) return; run(() => api.addDecor(order.id, { name, price: price || 0 })); setName(''); setPrice('') }}>
          <input className="input" placeholder="Lamp, art, throw…" value={name} onChange={e => setName(e.target.value)} aria-label="Decor item" style={{ flex: '1 1 100px', width: 100, minWidth: 0 }} />
          <input className="input" placeholder="$" type="number" step="0.01" value={price} onChange={e => setPrice(e.target.value)} aria-label="Price" style={{ width: 80, flex: 'none' }} />
          <button className="btn small" type="submit">Add</button>
        </form>
      </div>
    </section>
  )
}
