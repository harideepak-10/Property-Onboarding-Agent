import { useEffect, useState } from 'react'
import { api } from '../../api'
import { ErrorBox, Icon, Loading, useToast } from '../../components/ui'

const MASK = '••••••'
const SECTIONS = [
  ['Arrival', [['check_in_time', 'Check-in time'], ['check_out_time', 'Check-out time'], ['arrival_instructions', 'Getting in', true], ['buzzer_instructions', 'Building buzzer', true]]],
  ['Access', [['lockbox_location', 'Lockbox location'], ['lockbox_code', 'Lockbox code', false, true], ['wifi_name', 'Wi-Fi name'], ['wifi_password', 'Wi-Fi password', false, true]]],
  ['Staying', [['parking_instructions', 'Parking', true], ['garbage_instructions', 'Garbage and recycling', true], ['house_rules', 'House rules', true], ['local_tips', 'Local tips', true]]],
  ['Support', [['emergency_contact', 'Emergency contact (24/7)'], ['enso_guidebook_url', 'Enso Connect guidebook link']]],
]

export default function GuestTab({ p, onSaved }) {
  const toast = useToast()
  const [g, setG] = useState(null)
  const [f, setF] = useState(null)
  const [revealed, setRevealed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => { api.guestGuide(p.id).then(d => { setG(d); setF(d) }).catch(setErr) }, [p.id])
  if (!g) return err ? <ErrorBox error={err} /> : <Loading />

  const set = k => e => setF({ ...f, [k]: e.target.value })
  const reveal = async () => {
    try { const r = await api.revealGuide(p.id); setF({ ...f, lockbox_code: r.lockbox_code, wifi_password: r.wifi_password }); setRevealed(true) } catch (e) { setErr(e) }
  }
  const copyGuide = async () => {
    try { const r = await api.revealGuide(p.id); await navigator.clipboard.writeText(r.guidebook_text); toast('Guidebook copied. Paste it into Enso Connect.') }
    catch (e) { setErr(e.name === 'NotAllowedError' ? new Error('The browser blocked copying. Try again.') : e) }
  }
  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    const body = Object.fromEntries(SECTIONS.flatMap(([, fs]) => fs.map(([k]) => [k, f[k] ?? ''])))
    try {
      const d = await api.updateGuestGuide(p.id, body)
      setG(d); setF(d); setRevealed(false)
      toast(d.notes?.length ? d.notes[0] : 'Guest guide saved.')
      onSaved?.()
    } catch (e2) { setErr(e2) } finally { setBusy(false) }
  }

  return (
    <div className="cols">
      <form className="card" onSubmit={save}>
        <div className="card-h"><h2>Guest guide</h2><span className="sub">Becomes the Enso Connect guidebook</span><span className="spacer" />
          {!revealed && (g.lockbox_code || g.wifi_password) && <button className="btn small" type="button" onClick={reveal}><Icon name="lock" small />Show codes</button>}</div>
        <div className="card-b" style={{ display: 'grid', gap: 22 }}>
          <ErrorBox error={err} />
          {SECTIONS.map(([title, fields]) => (
            <div key={title} style={{ display: 'grid', gap: 12 }}>
              <h3 className="fh" style={{ margin: 0 }}>{title}</h3>
              <div className="form-grid">{fields.map(([k, label, long, secret]) => (
                <div className="field" key={k} style={long ? { gridColumn: '1/-1' } : undefined}>
                  <label htmlFor={'gg-' + k}>{label}{secret && <span className="muted"> · hidden</span>}</label>
                  {long ? <textarea id={'gg-' + k} className="input" rows={3} value={f[k] || ''} onChange={set(k)} />
                    : <input id={'gg-' + k} value={f[k] || ''} onChange={set(k)} type={k.endsWith('url') ? 'url' : 'text'}
                        onFocus={e => { if (secret && f[k] === MASK) setF({ ...f, [k]: '' }) }} autoComplete="off" />}
                </div>))}</div>
            </div>
          ))}
          <div className="row"><button className="btn primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save guest guide'}</button>
            <span className="muted sm">Codes are hidden after saving. Each time someone views them, it's logged.</span></div>
        </div>
      </form>
      <div className="sticky">
        <section className="card">
          <div className="card-h"><h2>Step 11 · Guest experience</h2></div>
          <div className="card-b" style={{ display: 'grid', gap: 9 }}>
            {g.step.tasks.map(t => <div key={t.title} className={`rcheck ${t.done ? 'ok' : ''}`}><Icon name={t.done ? 'checkc' : 'clock'} small /><span>{t.title}</span></div>)}
            {g.step.status === 'locked' && <div className="note info" style={{ margin: 0 }}><Icon name="lock" small /><span>Unlocks after setup day (step 7). Fill the guide now; it counts once unlocked.</span></div>}
          </div>
        </section>
        <section className="card">
          <div className="card-h"><h2>Still missing</h2><span className="spacer" /><b className="num sm">{g.missing.length}</b></div>
          <div className="card-b" style={{ display: 'grid', gap: 8 }}>
            {g.missing.length ? g.missing.map(m => <div key={m} className="rcheck"><Icon name="alert" small /><span>{m}</span></div>)
              : <div className="note ok" style={{ margin: 0 }}><Icon name="checkc" small /><span>The guide is complete.</span></div>}
          </div>
        </section>
        <section className="card">
          <div className="card-h"><h2>Enso Connect</h2></div>
          <div className="card-b" style={{ display: 'grid', gap: 10 }}>
            <span className="muted sm">Enso Connect has no public API, so the guide is copied in. Paste it into the property's guidebook in Enso, then add the guidebook link here.</span>
            <button className="btn" type="button" onClick={copyGuide}><Icon name="copy" small />Copy guidebook for Enso</button>
            {g.enso_guidebook_url && <a className="sm" href={g.enso_guidebook_url} target="_blank" rel="noreferrer">Open the guidebook ↗</a>}
          </div>
        </section>
      </div>
    </div>
  )
}
