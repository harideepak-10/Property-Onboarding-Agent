import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, money } from '../api'
import { ErrorBox, Icon, Loading, useToast } from '../components/ui'
import Buildings from './Buildings'

export const VENDOR_KINDS = [['handyman', 'Handyman / inspector'], ['photographer', 'Photographer'], ['cleaner', 'Cleaner'], ['mover', 'Movers / assembly'], ['other', 'Other']]

export default function Contacts() {
  const [qs, setQs] = useSearchParams()
  const tab = qs.get('tab') || 'buildings'
  return (
    <>
      <div className="page-head"><div><h1>Contacts</h1><p>Building management offices and the vendors you book for inspections, setup and photos.</p></div></div>
      <div className="ptabs" role="tablist">
        {[['buildings', 'building', 'Buildings'], ['vendors', 'users', 'Vendors']].map(([k, i, l]) =>
          <button key={k} className="ptab" role="tab" type="button" aria-selected={tab === k} onClick={() => setQs({ tab: k })}><Icon name={i} small />{l}</button>)}
      </div>
      {tab === 'buildings' ? <Buildings embedded /> : <Vendors />}
    </>
  )
}

/** Upload a CSV exported from the client's sheet. */
export function ImportButton({ kind, columns, onDone }) {
  const toast = useToast()
  const ref = useRef()
  const [busy, setBusy] = useState(false)
  const pick = async (file) => {
    setBusy(true)
    try { const r = await api.importContacts(kind, file); toast(`Imported: ${r.created} new, ${r.updated} updated.`); onDone?.() }
    catch (e) { toast(e.message) } finally { setBusy(false); ref.current.value = '' }
  }
  return <>
    <input ref={ref} type="file" accept=".csv,text/csv" hidden onChange={e => e.target.files[0] && pick(e.target.files[0])} />
    <button className="btn" type="button" disabled={busy} onClick={() => ref.current.click()} title={`CSV columns: ${columns}`}><Icon name="upload" small />{busy ? 'Importing…' : 'Import CSV'}</button>
  </>
}

const BLANK = { name: '', kind: 'handyman', company: '', email: '', phone: '', rate: '', notes: '', is_active: true }

function Vendors() {
  const toast = useToast()
  const [list, setList] = useState(null)
  const [edit, setEdit] = useState(null)
  const [err, setErr] = useState(null)
  const load = () => api.vendors().then(setList).catch(setErr)
  useEffect(() => { load() }, [])
  const save = async (e) => {
    e.preventDefault(); setErr(null)
    try { await api.saveVendor({ ...edit, rate: edit.rate === '' ? null : edit.rate }); setEdit(null); toast('Vendor saved.'); load() } catch (e2) { setErr(e2) }
  }
  if (!list) return err ? <ErrorBox error={err} /> : <Loading />
  return <>
    <div className="row"><p className="muted" style={{ margin: 0 }}>Pick these when booking a visit; their details and usual rate fill in automatically.</p><span className="spacer" />
      <ImportButton kind="vendors" columns="name, kind, company, email, phone, rate, notes" onDone={load} />
      <button className="btn primary" type="button" onClick={() => setEdit({ ...BLANK })}><Icon name="plus" small />Add vendor</button></div>
    <ErrorBox error={err} />
    <section className="card"><div className="table-wrap"><table>
      <thead><tr><th>Vendor</th><th>Type</th><th>Contact</th><th className="r">Usual rate</th><th className="r">Visits</th><th /></tr></thead>
      <tbody>{list.map(v => (
        <tr key={v.id} className={v.is_active ? '' : 'zero'}>
          <td><b className="sm">{v.name}</b>{v.company && <div className="muted sm">{v.company}</div>}</td>
          <td className="sm">{v.kind_label}</td>
          <td className="sm">{v.email || '—'}<div className="muted sm">{v.phone}</div></td>
          <td className="r num sm">{v.rate ? money(v.rate) : '—'}</td>
          <td className="r num sm">{v.visits}</td>
          <td className="r"><button className="btn small ghost" onClick={() => setEdit({ ...v, rate: v.rate ?? '' })}>Edit</button></td>
        </tr>))}
        {!list.length && <tr><td colSpan={6} className="empty">No vendors yet. Add them or import the client's list.</td></tr>}</tbody></table></div></section>
    {edit && <EditVendor v={edit} setV={setEdit} onSave={save} onClose={() => setEdit(null)} />}
  </>
}

function EditVendor({ v, setV, onSave, onClose }) {
  const ref = useRef()
  useEffect(() => { ref.current?.showModal() }, [])
  const set = k => e => setV({ ...v, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const f = (k, label, props = {}) => <div className="field"><label htmlFor={'v-' + k}>{label}</label><input id={'v-' + k} value={v[k] ?? ''} onChange={set(k)} {...props} /></div>
  return (
    <dialog ref={ref} onClose={onClose}><form onSubmit={onSave}>
      <div className="dlg-h"><h2>{v.id ? 'Edit vendor' : 'Add vendor'}</h2><span className="spacer" /><button className="btn ghost small" type="button" onClick={onClose}>Close</button></div>
      <div className="dlg-b"><div className="form-grid">
        {f('name', 'Name', { required: true })}
        <div className="field"><label htmlFor="v-kind">Type</label><select id="v-kind" value={v.kind} onChange={set('kind')}>{VENDOR_KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
        {f('company', 'Company')}{f('email', 'Email', { type: 'email' })}{f('phone', 'Phone')}{f('rate', 'Usual rate ($)', { type: 'number', step: '0.01' })}
        <div className="field" style={{ gridColumn: '1/-1' }}><label htmlFor="v-notes">Notes</label><input id="v-notes" value={v.notes || ''} onChange={set('notes')} /></div>
        <label className="row sm" style={{ gap: 8 }}><input type="checkbox" checked={v.is_active} onChange={set('is_active')} />Active</label>
      </div></div>
      <div className="dlg-f"><span className="spacer" /><button className="btn primary" type="submit">Save vendor</button></div>
    </form></dialog>
  )
}
