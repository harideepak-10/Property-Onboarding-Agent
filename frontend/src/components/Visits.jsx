import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtDate, money } from '../api'
import { Icon, useToast } from './ui'

export const KINDS = [['inspection', 'Inspection'], ['setup_day', 'Setup day'], ['photo_shoot', 'Photo shoot'], ['delivery', 'Delivery window'], ['repair', 'Repair / handyman'], ['other', 'Other']]
const KIND_ICON = { inspection: 'checkc', setup_day: 'home', photo_shoot: 'sparkle', delivery: 'truck', repair: 'key', other: 'cal' }
const STATUS_TONE = { booked: 'p-acc', done: 'p-ok', cancelled: 'p-info' }

export function BookVisitForm({ propertyId, properties, defaultKind = 'inspection', onBooked }) {
  const toast = useToast()
  const blank = { property: propertyId || '', kind: defaultKind, date: '', time: '', assigned_to: '', contact_email: '', contact_phone: '', cost: '', notes: '', draft_email: true }
  const [f, setF] = useState(blank)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = k => e => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      const v = await api.bookVisit({ ...f, cost: f.cost === '' ? null : f.cost })
      toast(`${v.kind_label} booked${f.contact_email && f.draft_email ? '. Confirmation email drafted in Approvals.' : '.'}`)
      setF({ ...blank, kind: f.kind, property: f.property }); onBooked?.(v)
    } catch (e2) { setErr(e2) } finally { setBusy(false) }
  }
  return (
    <form className="card-b form-grid" onSubmit={submit}>
      {err && <div className="error" style={{ gridColumn: '1/-1' }}>{err.message}</div>}
      {properties && <div className="field"><label htmlFor="bv-p">Property</label>
        <select id="bv-p" className="mono" required value={f.property} onChange={set('property')}><option value="">Choose…</option>{properties.map(p => <option key={p.id} value={p.id}>{p.nickname}</option>)}</select></div>}
      <div className="field"><label htmlFor="bv-k">What</label><select id="bv-k" value={f.kind} onChange={set('kind')}>{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
      <div className="field"><label htmlFor="bv-d">Date</label><input id="bv-d" type="date" required value={f.date} onChange={set('date')} /></div>
      <div className="field"><label htmlFor="bv-t">Time</label><input id="bv-t" placeholder="10:00–14:00" value={f.time} onChange={set('time')} /></div>
      <div className="field"><label htmlFor="bv-a">Who</label><input id="bv-a" placeholder="Person or company" value={f.assigned_to} onChange={set('assigned_to')} /></div>
      <div className="field"><label htmlFor="bv-e">Their email</label><input id="bv-e" type="email" value={f.contact_email} onChange={set('contact_email')} /></div>
      <div className="field"><label htmlFor="bv-ph">Phone</label><input id="bv-ph" value={f.contact_phone} onChange={set('contact_phone')} /></div>
      <div className="field"><label htmlFor="bv-c">Cost ($)</label><input id="bv-c" type="number" step="0.01" value={f.cost} onChange={set('cost')} /></div>
      <div className="field" style={{ gridColumn: '1/-1' }}><label htmlFor="bv-n">Notes for them</label><input id="bv-n" value={f.notes} onChange={set('notes')} /></div>
      <div className="row" style={{ gridColumn: '1/-1' }}>
        <button className="btn primary" type="submit" disabled={busy}><Icon name="cal" small />{busy ? 'Booking…' : 'Book'}</button>
        {f.contact_email && <label className="row sm" style={{ gap: 6 }}><input type="checkbox" checked={f.draft_email} onChange={set('draft_email')} />Draft a confirmation email</label>}
      </div>
    </form>
  )
}

export function VisitCard({ v, onChange, showProperty }) {
  const toast = useToast()
  const [link, setLink] = useState(v.drive_link)
  const [busy, setBusy] = useState(false)
  const upd = async (data, msg) => {
    setBusy(true)
    try { const nv = await api.updateVisit(v.id, data); onChange?.(nv); if (msg) toast(msg) } catch (e) { toast(e.message) } finally { setBusy(false) }
  }
  const toggle = (i) => upd({ checklist: v.checklist.map((c, j) => j === i ? { ...c, done: !c.done } : c) })
  const done = v.checklist.filter(c => c.done).length
  const past = v.date < new Date().toISOString().slice(0, 10)
  return (
    <div className="cart" style={{ opacity: v.status === 'cancelled' ? .6 : 1 }}>
      <div className="cart-h"><div className="kpi-ic ic-acc"><Icon name={KIND_ICON[v.kind]} small /></div>
        <div style={{ minWidth: 0 }}><b className="sm">{v.kind_label}{showProperty && <> · <Link className="mono" to={`/properties/${v.property}`}>{v.nickname}</Link></>}</b>
          <div className="muted sm">{fmtDate(v.date)}{v.time ? ` · ${v.time}` : ''}{v.assigned_to ? ` · ${v.assigned_to}` : ''}</div></div>
        <span className="spacer" /><span className={`pill ${STATUS_TONE[v.status]}`}>{v.status_label}</span></div>
      <div className="card-b" style={{ display: 'grid', gap: 8, paddingTop: 10 }}>
        {(v.contact_email || v.contact_phone || v.cost) && <div className="muted sm">{[v.contact_email, v.contact_phone, v.cost && money(v.cost)].filter(Boolean).join(' · ')}</div>}
        {v.notes && <div className="sm">{v.notes}</div>}
        {v.kind === 'setup_day' && <div style={{ display: 'grid', gap: 4 }}>
          <div className="muted sm">Checklist {done}/{v.checklist.length}</div>
          {v.checklist.map((c, i) => <label key={c.label} className="row sm" style={{ gap: 8 }}><input type="checkbox" checked={c.done} disabled={busy || v.status === 'cancelled'} onChange={() => toggle(i)} />{c.label}</label>)}
        </div>}
        {(v.kind === 'photo_shoot' || v.kind === 'inspection') && v.status !== 'cancelled' && <form className="row" style={{ gap: 6, flexWrap: 'nowrap' }} onSubmit={e => { e.preventDefault(); upd({ drive_link: link }, 'Drive link saved. Checklist updated.') }}>
          <input className="input" type="url" placeholder="Drive link to photos" value={link} onChange={e => setLink(e.target.value)} style={{ flex: 1, minWidth: 0 }} aria-label="Drive link" />
          <button className="btn small" type="submit" disabled={busy || link === v.drive_link}>Save</button></form>}
        {v.kind === 'photo_shoot' && past && !v.drive_link && v.status !== 'cancelled' && <div className="note warn" style={{ margin: 0 }}><Icon name="clock" small /><span>Shoot was {fmtDate(v.date)}; still waiting for photos.{v.followup_sent_at ? ' Follow-up drafted.' : ' The daily check drafts a follow-up after 3 days.'}</span></div>}
        {v.status === 'booked' && <div className="row" style={{ gap: 6 }}>
          <button className="btn small" disabled={busy} onClick={() => upd({ status: 'done' }, 'Marked done.')}><Icon name="check" small />Done</button>
          <button className="btn ghost small" disabled={busy} onClick={() => upd({ status: 'cancelled' }, 'Cancelled.')}>Cancel</button></div>}
      </div>
    </div>
  )
}
