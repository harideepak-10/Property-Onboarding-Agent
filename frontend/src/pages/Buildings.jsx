import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { ErrorBox, Icon, Loading, useToast } from '../components/ui'
import { ImportButton } from './Contacts'

const BLANK = { name: '', street_number: '', street_name: '', management_company: '', management_email: '', management_phone: '', registration_notes: '' }

export default function Buildings({ embedded }) {
  const [list, setList] = useState(null)
  const [edit, setEdit] = useState(null)
  const [err, setErr] = useState(null)
  const toast = useToast()
  const load = () => api.buildings().then(setList).catch(setErr)
  useEffect(() => { load() }, [])

  const save = async (e) => {
    e.preventDefault(); setErr(null)
    try { await api.saveBuilding(edit); setEdit(null); toast('Building saved.'); load() } catch (e2) { setErr(e2) }
  }

  if (!list) return err ? <ErrorBox error={err} /> : <Loading />
  return (
    <>
      <div className="row"><p className="muted" style={{ margin: 0 }}>Management offices the Intake agent emails to register units, keys, fobs and parking.</p><span className="spacer" />
        <ImportButton kind="buildings" columns="street_number, street_name, name, management_company, management_email, management_phone, notes" onDone={load} />
        <button className="btn primary" type="button" onClick={() => setEdit({ ...BLANK })}><Icon name="plus" small />Add building</button></div>
      <ErrorBox error={err} />
      <section className="card"><div className="table-wrap"><table>
        <thead><tr><th>Building</th><th>Management</th><th>Email</th><th>What they need</th><th className="r">Units</th><th /></tr></thead>
        <tbody>{list.map(b => (
          <tr key={b.id}>
            <td><b className="sm">{b.name || `${b.street_number} ${b.street_name}`}</b><div className="muted sm">{b.street_number} {b.street_name}</div></td>
            <td className="sm">{b.management_company || '—'}<div className="muted sm">{b.management_phone}</div></td>
            <td className="sm">{b.management_email || <span className="pill p-warn nodot">Missing</span>}</td>
            <td className="sm muted" style={{ maxWidth: 320 }}>{b.registration_notes || '—'}</td>
            <td className="r num">{b.units}</td>
            <td className="r"><button className="btn small ghost" onClick={() => setEdit({ ...b })}>Edit</button></td>
          </tr>))}
          {!list.length && <tr><td colSpan={6} className="empty">No buildings yet.</td></tr>}</tbody></table></div></section>
      {edit && <EditBuilding b={edit} setB={setEdit} onSave={save} onClose={() => setEdit(null)} />}
    </>
  )
}

function EditBuilding({ b, setB, onSave, onClose }) {
  const ref = useRef()
  useEffect(() => { ref.current?.showModal() }, [])
  const set = k => e => setB({ ...b, [k]: e.target.value })
  const f = (k, label, props = {}) => <div className="field"><label htmlFor={'b-' + k}>{label}</label><input id={'b-' + k} value={b[k] || ''} onChange={set(k)} {...props} /></div>
  return (
    <dialog ref={ref} onClose={onClose}><form onSubmit={onSave}>
      <div className="dlg-h"><h2>{b.id ? 'Edit building' : 'Add building'}</h2><span className="spacer" /><button className="btn ghost small" type="button" onClick={onClose}>Close</button></div>
      <div className="dlg-b"><div className="form-grid">
        {f('street_number', 'Street number', { required: true })}{f('street_name', 'Street', { required: true })}
        {f('name', 'Building name')}{f('management_company', 'Management company')}
        {f('management_email', 'Management email', { type: 'email' })}{f('management_phone', 'Phone')}
        <div className="field" style={{ gridColumn: '1/-1' }}><label htmlFor="b-notes">What this building needs</label>
          <textarea id="b-notes" className="input" rows={4} value={b.registration_notes} onChange={set('registration_notes')} placeholder="Forms, fob fees, elevator booking, parking rules…" /></div>
      </div></div>
      <div className="dlg-f"><span className="spacer" /><button className="btn primary" type="submit">Save building</button></div>
    </form></dialog>
  )
}
