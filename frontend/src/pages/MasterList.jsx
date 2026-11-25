import { useEffect, useMemo, useRef, useState } from 'react'
import { api, money } from '../api'
import { ErrorBox, Icon, Loading, useToast } from '../components/ui'

const CATS = [['furniture', 'Furniture'], ['kitchen', 'Kitchen'], ['bath', 'Bath'], ['bedroom', 'Bedroom'], ['living', 'Living'], ['electronics', 'Electronics and fixtures'], ['cleaning', 'Cleaning']]
const RULES = [['fixed', 'Fixed'], ['per_bedroom', 'Per bedroom'], ['per_bathroom', 'Per bathroom'], ['per_bed', 'Per bed'], ['per_guest', 'Per guest (sleeps)']]
const BLANK = { category: 'kitchen', name: '', item_type: '', store_code: 'amazon', typical_price: '', rule: 'fixed', multiplier: 1, bed_size: '', include_sofa_beds: false, product_url: '', store_sku: '', is_active: true }

export default function MasterList() {
  const [items, setItems] = useState(null)
  const [stores, setStores] = useState([])
  const [err, setErr] = useState(null)
  const [edit, setEdit] = useState(null)
  const [filter, setFilter] = useState('')
  const [preview, setPreview] = useState({ bedrooms: 2, bathrooms: 1, beds: 2 })
  const fileRef = useRef()
  const toast = useToast()

  const load = () => api.masterItems().then(setItems).catch(setErr)
  useEffect(() => { load(); api.stores().then(setStores) }, [])

  // preview assumes queen beds and no sofa beds
  const qty = (it) => ({ fixed: 1, per_bedroom: preview.bedrooms, per_bathroom: preview.bathrooms, per_bed: !it.bed_size || it.bed_size === 'queen' ? preview.beds : 0, per_guest: preview.beds * 2 }[it.rule] ?? 0) * it.multiplier
  const shown = useMemo(() => (items || []).filter(i => !filter || (i.name + ' ' + i.item_type).toLowerCase().includes(filter.toLowerCase())), [items, filter])
  const est = (items || []).filter(i => i.is_active).reduce((a, i) => a + qty(i) * Number(i.typical_price), 0)

  const save = async (e) => {
    e.preventDefault(); setErr(null)
    try { await api.saveMasterItem({ ...edit, typical_price: edit.typical_price || 0 }); setEdit(null); toast('Item saved.'); load() } catch (e2) { setErr(e2) }
  }
  const importFile = async (file) => {
    if (!file) return
    setErr(null)
    try { const r = await api.importMasterList(file); toast(`Imported: ${r.created} new, ${r.updated} updated.`); load() } catch (e) { setErr(e) }
    fileRef.current.value = ''
  }
  const toggle = async (it) => { try { await api.saveMasterItem({ id: it.id, is_active: !it.is_active }); load() } catch (e) { setErr(e) } }

  if (!items) return err ? <ErrorBox error={err} /> : <Loading />
  let cat = ''

  return (
    <>
      <div className="page-head"><div><h1>Master list</h1><p>{items.length} items. Quantities scale with each unit by rule. Export the team's Google Sheet as CSV to import it.</p></div><span className="spacer" />
        <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={e => importFile(e.target.files[0])} />
        <button className="btn" type="button" onClick={() => fileRef.current.click()}><Icon name="upload" small />Import CSV</button>
        <button className="btn primary" type="button" onClick={() => setEdit({ ...BLANK })}><Icon name="plus" small />Add item</button></div>
      <ErrorBox error={err} />

      <div className="cols">
        <section className="card">
          <div className="card-h"><h2>Items</h2><span className="spacer" />
            <input className="input" placeholder="Filter items" value={filter} onChange={e => setFilter(e.target.value)} aria-label="Filter items" style={{ width: 220 }} /></div>
          <div className="table-wrap"><table className="tight mi-table">
            <thead><tr><th>Item</th><th>Rule</th><th>Store</th><th className="r">Typical</th><th className="r">Qty*</th><th>Replacement</th><th /></tr></thead>
            <tbody>{shown.map(it => {
              const head = it.category !== cat ? (cat = it.category, <tr className="cat" key={'c' + cat}><td colSpan={7}>{it.category_label}</td></tr>) : null
              return [head,
                <tr key={it.id} className={it.is_active ? '' : 'zero'}>
                  <td><b className="sm">{it.name}</b><div className="muted sm">type: {it.item_type}{it.store_sku ? ` · SKU ${it.store_sku}` : ''}</div></td>
                  <td className="sm">{it.rule_label.replace(' (one per unit)', '')}{it.multiplier > 1 ? ` × ${it.multiplier}` : ''}{it.bed_size ? <div className="muted sm">{it.bed_size} beds{it.include_sofa_beds ? ' + sofa beds' : ''}</div> : it.include_sofa_beds ? <div className="muted sm">+ sofa beds</div> : null}</td>
                  <td className="sm">{stores.find(s => s.code === it.store_code)?.name || it.store_code}</td>
                  <td className="r num sm">{money(it.typical_price)}</td>
                  <td className="r num"><b>{it.is_active ? qty(it) : '—'}</b></td>
                  <td className="sm muted">{it.alternatives[0] ? `${it.alternatives[0].name} (${money(it.alternatives[0].typical_price)})` : '—'}</td>
                  <td className="r" style={{ whiteSpace: 'nowrap' }}><button className="btn small ghost" onClick={() => setEdit({ ...it })}>Edit</button>
                    <button className="btn small ghost" onClick={() => toggle(it)}>{it.is_active ? 'Disable' : 'Enable'}</button></td>
                </tr>]
            })}</tbody></table></div>
        </section>
        <div className="sticky">
          <section className="card">
            <div className="card-h"><h2>Quantity preview</h2><span className="sub">*Qty column</span></div>
            <div className="card-b" style={{ display: 'grid', gap: 12 }}>
              <div className="counts">{[['bedrooms', 'Bedrooms'], ['bathrooms', 'Bathrooms'], ['beds', 'Beds']].map(([k, l]) =>
                <div className="field" key={k}><label htmlFor={'pv' + k}>{l}</label><input id={'pv' + k} type="number" min="0" value={preview[k]} onChange={e => setPreview({ ...preview, [k]: Math.max(0, parseInt(e.target.value) || 0) })} /></div>)}</div>
              <div className="sum-row total"><span>Estimated kit</span><span className="num">{money(est)}</span></div>
              <div className="muted sm">At typical prices, active items only.</div>
            </div>
          </section>
          <section className="card">
            <div className="card-h"><h2>CSV columns</h2></div>
            <div className="card-b sm muted" style={{ lineHeight: 1.7 }}>category, name, item_type, store, typical_price, rule, multiplier, bed_size, include_sofa_beds, product_url, store_sku, alt_name, alt_store, alt_price, alt_url
              <div style={{ marginTop: 8 }}>Rules: fixed, per bedroom, per bathroom, per bed. Rows match on name + store, so re-importing updates prices. If any row has an error, nothing is imported.</div></div>
          </section>
        </div>
      </div>

      {edit && <EditDialog item={edit} setItem={setEdit} stores={stores} onSave={save} onClose={() => setEdit(null)} />}
    </>
  )
}

function EditDialog({ item, setItem, stores, onSave, onClose }) {
  const ref = useRef()
  useEffect(() => { ref.current?.showModal() }, [])
  const set = k => e => setItem({ ...item, [k]: e.target.value })
  return (
    <dialog ref={ref} onClose={onClose}>
      <form onSubmit={onSave}>
        <div className="dlg-h"><h2>{item.id ? 'Edit item' : 'Add item'}</h2><span className="spacer" /><button className="btn ghost small" type="button" onClick={onClose}>Close</button></div>
        <div className="dlg-b"><div className="form-grid">
          <div className="field" style={{ gridColumn: '1/-1' }}><label htmlFor="e-name">Name</label><input id="e-name" value={item.name} onChange={set('name')} required /></div>
          <div className="field"><label htmlFor="e-type">Item type (for cross-check)</label><input id="e-type" value={item.item_type} onChange={set('item_type')} required placeholder="kettle" /></div>
          <div className="field"><label htmlFor="e-cat">Category</label><select id="e-cat" value={item.category} onChange={set('category')}>{CATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
          <div className="field"><label htmlFor="e-store">Store</label><select id="e-store" value={item.store_code} onChange={set('store_code')}>{stores.map(s => <option key={s.code} value={s.code}>{s.name}</option>)}</select></div>
          <div className="field"><label htmlFor="e-price">Typical price</label><input id="e-price" type="number" step="0.01" min="0" value={item.typical_price} onChange={set('typical_price')} required /></div>
          <div className="field"><label htmlFor="e-rule">Quantity rule</label><select id="e-rule" value={item.rule} onChange={set('rule')}>{RULES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
          <div className="field"><label htmlFor="e-mult">Multiplier</label><input id="e-mult" type="number" min="1" value={item.multiplier} onChange={set('multiplier')} /></div>
          {item.rule === 'per_bed' && <>
            <div className="field"><label htmlFor="e-bs">Bed size</label><select id="e-bs" value={item.bed_size || ''} onChange={set('bed_size')}>
              {[['', 'Any size'], ['king', 'King'], ['queen', 'Queen'], ['double', 'Double'], ['twin', 'Twin']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
            <label className="row sm" style={{ gap: 8, alignSelf: 'end' }}><input type="checkbox" checked={!!item.include_sofa_beds} onChange={e => setItem({ ...item, include_sofa_beds: e.target.checked })} />Also count sofa beds (bedding, not mattresses)</label>
          </>}
          <div className="field" style={{ gridColumn: '1/-1' }}><label htmlFor="e-url">Product link</label><input id="e-url" type="url" value={item.product_url} onChange={set('product_url')} placeholder="https://" /></div>
          <div className="field"><label htmlFor="e-sku">Store SKU / ASIN</label><input id="e-sku" value={item.store_sku} onChange={set('store_sku')} /></div>
        </div></div>
        <div className="dlg-f"><span className="spacer" /><button className="btn primary" type="submit">Save item</button></div>
      </form>
    </dialog>
  )
}
