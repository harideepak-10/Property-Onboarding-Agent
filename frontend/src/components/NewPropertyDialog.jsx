import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { ErrorBox, Icon, useToast } from './ui'

const EMPTY = { owner_name: '', owner_type: 'owner', owner_email: '', owner_phone: '', street_number: '', street_name: '', unit: '',
  postal_code: '', bedrooms: 1, bathrooms: 1, beds: 1, lease_start: '', lease_end: '', parking: '', locker: '' }
const REQUIRED = ['owner_name', 'street_number', 'street_name', 'unit', 'bedrooms', 'bathrooms', 'lease_start', 'lease_end']

export default function NewPropertyDialog({ onClose, onCreated }) {
  const ref = useRef()
  const fileRef = useRef()
  const toast = useToast()
  const [mode, setMode] = useState('upload') // upload | manual
  const [doc, setDoc] = useState(null)
  const [f, setF] = useState(EMPTY)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)

  useEffect(() => { ref.current?.showModal() }, [])
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const upload = async (file) => {
    if (!file) return
    setErr(null); setBusy(true)
    try {
      const d = await api.uploadAgreement(file)
      if (d.status === 'failed') throw new Error(`Couldn't read this PDF. ${d.error}`)
      setDoc(d)
      const x = d.extracted
      setF({ ...EMPTY, ...Object.fromEntries(Object.entries(x).filter(([k, v]) => k in EMPTY && v !== null && v !== '')) })
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    const fields = { ...f, bedrooms: +f.bedrooms, bathrooms: +f.bathrooms, beds: +f.beds }
    for (const k of ['lease_start', 'lease_end']) if (!fields[k]) delete fields[k]
    try {
      if (doc) {
        const r = await api.createFromAgreement(doc.id, fields)
        toast(`Created ${r.property.nickname}. The Intake agent is working on it.`)
        onCreated(r.property, r.run)
      } else {
        const p = await api.createProperty(fields)
        toast(`Created ${p.nickname} with its 12-step checklist.`)
        onCreated(p, null)
      }
    } catch (e2) { setErr(e2) } finally { setBusy(false) }
  }

  const conf = (k) => doc?.confidence?.[k]
  const field = (k, label, props = {}) => {
    const missing = doc && REQUIRED.includes(k) && (f[k] === '' || f[k] === null)
    const low = doc && !missing && (doc.method === 'heuristic' ? f[k] !== '' : conf(k) === 'low')
    return (
      <div className={`field ${missing ? 'miss' : low ? 'low' : ''}`}>
        <label htmlFor={`np-${k}`}>{label}</label>
        <input id={`np-${k}`} value={f[k] ?? ''} onChange={set(k)} {...props} />
        {missing && <span className="hint">Not found in the agreement</span>}
        {!missing && doc?.method !== 'heuristic' && conf(k) === 'low' && <span className="hint">Unclear in the PDF. Please check</span>}
      </div>
    )
  }

  const showForm = mode === 'manual' || doc
  return (
    <dialog ref={ref} onClose={onClose}>
      <form onSubmit={submit}>
        <div className="dlg-h">
          <div className="kpi-ic ic-acc"><Icon name="home" /></div>
          <div><h2>New property</h2><div className="muted sm">Start from the signed agreement</div></div>
          <span className="spacer" /><button className="btn ghost small" type="button" onClick={onClose}>Close</button>
        </div>
        <div className="dlg-b">
          {!doc && <div className="seg" role="group" aria-label="How to add">
            <button type="button" aria-pressed={mode === 'upload'} onClick={() => setMode('upload')}>Upload agreement</button>
            <button type="button" aria-pressed={mode === 'manual'} onClick={() => setMode('manual')}>Enter manually</button></div>}
          <ErrorBox error={err} />
          {mode === 'upload' && !doc && (
            <div className={`upload-zone ${drag ? 'drag' : ''}`} role="button" tabIndex={0}
              onClick={() => fileRef.current.click()} onKeyDown={e => e.key === 'Enter' && fileRef.current.click()}
              onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
              onDrop={e => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]) }}>
              {busy ? <><span className="spin" /><b>Reading the agreement…</b><span className="muted sm">The Intake agent is pulling out the owner, address, unit size and lease dates.</span></>
                : <><div className="kpi-ic ic-acc"><Icon name="upload" /></div><b>Drop the signed agreement here</b><span className="muted sm">PDF, up to 25 MB. You'll review everything before anything is created.</span></>}
              <input ref={fileRef} type="file" accept="application/pdf,.pdf" hidden onChange={e => upload(e.target.files[0])} />
            </div>
          )}
          {doc && <div className={`note ${doc.method === 'heuristic' ? 'warn' : 'ok'}`} style={{ margin: 0 }}><Icon name={doc.method === 'heuristic' ? 'alert' : 'sparkle'} small />
            <div><b>{doc.original_name}</b> · {doc.method === 'heuristic' ? 'Read with the basic text reader (no AI key set). Check every field.' : `Read by Claude (${doc.model}). Fields in amber were unclear.`}
              {doc.notes && <div className="sm" style={{ marginTop: 4 }}>{doc.notes}</div>}</div></div>}
          {showForm && <div className="form-grid">
            {field('owner_name', 'Owner or agent name', { required: true })}
            <div className="field"><label htmlFor="np-owner_type">Type</label>
              <select id="np-owner_type" value={f.owner_type} onChange={set('owner_type')}><option value="owner">Owner</option><option value="agent">Agent</option></select></div>
            {field('owner_email', 'Owner email', { type: 'email' })}
            {field('owner_phone', 'Owner phone')}
            {field('street_number', 'Street number', { required: true })}
            {field('street_name', 'Street', { required: true, placeholder: 'e.g. Spadina Ave' })}
            {field('unit', 'Unit', { required: true })}
            {field('postal_code', 'Postal code')}
            {field('bedrooms', 'Bedrooms', { type: 'number', min: 0, required: true })}
            {field('bathrooms', 'Bathrooms', { type: 'number', min: 1, required: true })}
            {field('beds', 'Beds', { type: 'number', min: 1, required: true })}
            {field('parking', 'Parking')}
            {field('lease_start', 'Lease start', { type: 'date' })}
            {field('lease_end', 'Lease end', { type: 'date' })}
          </div>}
        </div>
        <div className="dlg-f">
          {doc ? <><button className="btn ghost small" type="button" onClick={() => { setDoc(null); setF(EMPTY) }}>Use a different file</button><span className="spacer" />
            <button className="btn primary" type="submit" disabled={busy}><Icon name="sparkle" small />{busy ? 'Creating…' : 'Create and run Intake agent'}</button></>
            : <><span className="muted sm">{mode === 'manual' ? 'The nickname is generated automatically.' : ''}</span><span className="spacer" />
              {mode === 'manual' && <button className="btn primary" type="submit" disabled={busy}>{busy ? 'Creating…' : 'Create property'}</button>}</>}
        </div>
      </form>
    </dialog>
  )
}
