import { useEffect, useState } from 'react'
import { api } from '../../api'
import { ErrorBox, Icon, Loading, useToast } from '../../components/ui'

const SIZES = [['king', 'King'], ['queen', 'Queen'], ['double', 'Double'], ['twin', 'Twin']]
const UTIL_STATUS = [['not_started', 'Not started'], ['requested', 'Requested'], ['active', 'Active'], ['included', 'Included by building']]

export default function UnitTab({ p, onSaved }) {
  const toast = useToast()
  const [d, setD] = useState(null)
  const [rooms, setRooms] = useState([])
  const [sofa, setSofa] = useState(0)
  const [sleeps, setSleeps] = useState('')
  const [acc, setAcc] = useState({})
  const [utils, setUtils] = useState([])
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  const fill = (x) => {
    setD(x)
    setRooms(x.bedrooms.length ? x.bedrooms : Array.from({ length: Math.max(1, p.bedrooms) }, (_, i) => ({ name: `Bedroom ${i + 1}`, bed_size: 'queen', beds: 1, is_bedroom: true })))
    setSofa(x.sofa_beds); setSleeps(x.sleeps_override ?? ''); setAcc(x.access); setUtils(x.utilities)
  }
  useEffect(() => { api.unit(p.id).then(fill).catch(setErr) }, [p.id])
  if (!d) return err ? <ErrorBox error={err} /> : <Loading />

  const setRoom = (i, k, v) => setRooms(rooms.map((r, j) => j === i ? { ...r, [k]: v } : r))
  const setA = (k) => (e) => setAcc({ ...acc, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.type === 'number' ? (+e.target.value || 0) : e.target.value })
  const setU = (i, k, v) => setUtils(utils.map((u, j) => j === i ? { ...u, [k]: v } : u))

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const x = await api.saveUnit(p.id, {
        bedrooms: rooms.map(r => ({ ...r, beds: +r.beds || 0 })), sofa_beds: +sofa || 0, sleeps_override: sleeps === '' ? null : +sleeps,
        access: acc, utilities: utils.filter(u => u.id || u.status !== 'not_started' || u.provider),
      })
      fill(x); toast('Unit details saved. Step 2 updated.'); onSaved?.()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const lay = d.layout
  return (
    <div className="cols">
      <div style={{ display: 'grid', gap: 18 }}>
        <ErrorBox error={err} />
        <section className="card">
          <div className="card-h"><h2>Bedrooms and beds</h2><span className="sub">Drives bed-size purchasing (twin rooms get twin sheets)</span></div>
          <div className="table-wrap"><table className="tight">
            <thead><tr><th>Room</th><th>Bed size</th><th className="r">Beds</th><th>Counts as bedroom</th><th /></tr></thead>
            <tbody>{rooms.map((r, i) => <tr key={i}>
              <td><input className="input" value={r.name} onChange={e => setRoom(i, 'name', e.target.value)} aria-label="Room name" /></td>
              <td><select className="input" value={r.bed_size} onChange={e => setRoom(i, 'bed_size', e.target.value)} aria-label="Bed size">{SIZES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></td>
              <td className="r"><input className="input" type="number" min="0" max="6" value={r.beds} onChange={e => setRoom(i, 'beds', e.target.value)} style={{ width: 70 }} aria-label="Beds" /></td>
              <td><label className="row sm" style={{ gap: 6 }}><input type="checkbox" checked={r.is_bedroom !== false} onChange={e => setRoom(i, 'is_bedroom', e.target.checked)} />Bedroom</label></td>
              <td><button className="btn ghost small" type="button" onClick={() => setRooms(rooms.filter((_, j) => j !== i))} aria-label="Remove room">×</button></td>
            </tr>)}</tbody></table></div>
          <div className="card-b row" style={{ gap: 14 }}>
            <button className="btn small" type="button" onClick={() => setRooms([...rooms, { name: `Bedroom ${rooms.length + 1}`, bed_size: 'queen', beds: 1, is_bedroom: true }])}><Icon name="plus" small />Add room</button>
            <div className="field" style={{ width: 120 }}><label htmlFor="sofa">Sofa beds</label><input id="sofa" type="number" min="0" value={sofa} onChange={e => setSofa(e.target.value)} /></div>
            <div className="field" style={{ width: 150 }}><label htmlFor="slo">Sleeps (override)</label><input id="slo" type="number" min="1" placeholder={`auto: ${lay.sleeps}`} value={sleeps} onChange={e => setSleeps(e.target.value)} /></div>
          </div>
        </section>

        <section className="card">
          <div className="card-h"><h2>Keys, fobs and parking</h2></div>
          <div className="card-b form-grid">
            <div className="field"><label htmlFor="kc">Keys</label><input id="kc" type="number" min="0" value={acc.keys_count} onChange={setA('keys_count')} /></div>
            <div className="field"><label htmlFor="fc">Fobs</label><input id="fc" type="number" min="0" value={acc.fob_count} onChange={setA('fob_count')} /></div>
            <div className="field"><label htmlFor="fn">Fob numbers</label><input id="fn" value={acc.fob_numbers} onChange={setA('fob_numbers')} /></div>
            <div className="field"><label htmlFor="kl">Where spares are kept</label><input id="kl" value={acc.keys_location} onChange={setA('keys_location')} /></div>
            <label className="row sm" style={{ gap: 8 }}><input type="checkbox" checked={acc.registered_with_building} onChange={setA('registered_with_building')} />Fobs registered with the building</label>
            <label className="row sm" style={{ gap: 8 }}><input type="checkbox" checked={acc.mailbox_key} onChange={setA('mailbox_key')} />Mailbox key</label>
            <label className="row sm" style={{ gap: 8, gridColumn: '1/-1' }}><input type="checkbox" checked={acc.has_parking} onChange={setA('has_parking')} />Unit has parking</label>
            {acc.has_parking && <>
              <div className="field"><label htmlFor="ps">Parking spot</label><input id="ps" value={acc.parking_spot} onChange={setA('parking_spot')} /></div>
              <div className="field"><label htmlFor="pp">Permit / tag</label><input id="pp" value={acc.parking_permit} onChange={setA('parking_permit')} /></div>
              <label className="row sm" style={{ gap: 8 }}><input type="checkbox" checked={acc.parking_registered} onChange={setA('parking_registered')} />Parking registered with the building</label>
            </>}
            <div className="field"><label htmlFor="lk">Locker</label><input id="lk" value={acc.locker} onChange={setA('locker')} /></div>
            <div className="field" style={{ gridColumn: '1/-1' }}><label htmlFor="an">Notes</label><textarea id="an" className="input" rows={2} value={acc.notes} onChange={setA('notes')} /></div>
          </div>
        </section>

        <section className="card">
          <div className="card-h"><h2>Utilities and internet</h2><span className="sub">Required: {d.required_utilities.join(', ')}</span></div>
          <div className="table-wrap"><table className="tight">
            <thead><tr><th>Utility</th><th>Provider</th><th>Account #</th><th>Status</th><th>Active from</th><th className="r">$ / month</th></tr></thead>
            <tbody>{utils.map((u, i) => <tr key={u.kind}>
              <td className="sm"><b>{u.kind_label}</b>{d.required_utilities.includes(u.kind) && <span className="muted"> · required</span>}</td>
              <td><input className="input" value={u.provider} onChange={e => setU(i, 'provider', e.target.value)} aria-label={`${u.kind_label} provider`} /></td>
              <td><input className="input mono" value={u.account_number} onChange={e => setU(i, 'account_number', e.target.value)} aria-label={`${u.kind_label} account number`} style={{ maxWidth: 130 }} /></td>
              <td><select className="input" value={u.status} onChange={e => setU(i, 'status', e.target.value)} aria-label={`${u.kind_label} status`}>{UTIL_STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></td>
              <td><input className="input" type="date" value={u.active_from || ''} onChange={e => setU(i, 'active_from', e.target.value)} aria-label={`${u.kind_label} active from`} /></td>
              <td className="r"><input className="input num" type="number" step="0.01" value={u.monthly_cost ?? ''} onChange={e => setU(i, 'monthly_cost', e.target.value)} style={{ width: 90 }} aria-label={`${u.kind_label} monthly cost`} /></td>
            </tr>)}</tbody></table></div>
        </section>
        <div className="row"><button className="btn primary" type="button" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save unit details'}</button>
          <span className="muted sm">Saving updates the step 2 checklist automatically.</span></div>
      </div>

      <div className="sticky">
        <section className="card">
          <div className="card-h"><h2>Layout</h2></div>
          <div className="card-b">
            <div className="sum-row"><span className="muted">Bedrooms</span><b className="num">{lay.bedrooms}</b></div>
            <div className="sum-row"><span className="muted">Bathrooms</span><b className="num">{lay.bathrooms}</b></div>
            {Object.entries(lay.beds_by_size).filter(([, n]) => n).map(([s, n]) => <div key={s} className="sum-row"><span className="muted">{s[0].toUpperCase() + s.slice(1)} beds</span><b className="num">{n}</b></div>)}
            <div className="sum-row"><span className="muted">Sofa beds</span><b className="num">{lay.sofa_beds}</b></div>
            <div className="sum-row total"><span>Sleeps</span><span className="num">{lay.sleeps}</span></div>
            <div className="muted sm">Procurement uses this layout for every new order.</div>
          </div>
        </section>
        <section className="card">
          <div className="card-h"><h2>Step 2 · what's left</h2></div>
          <div className="card-b" style={{ display: 'grid', gap: 9 }}>
            {Object.entries(d.readiness).map(([task, missing]) => <div key={task}>
              <div className={`rcheck ${missing.length ? '' : 'ok'}`}><Icon name={missing.length ? 'clock' : 'checkc'} small /><span>{task}</span></div>
              {missing.map(m => <div key={m} className="muted sm" style={{ marginLeft: 26 }}>{m}</div>)}
            </div>)}
          </div>
        </section>
      </div>
    </div>
  )
}
