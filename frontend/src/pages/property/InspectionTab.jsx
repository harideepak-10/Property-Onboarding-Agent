import { useEffect, useState } from 'react'
import { api, fmtDate, money, openHtml } from '../../api'
import { ErrorBox, Icon, Loading, useToast } from '../../components/ui'

const CONDITIONS = [['', '—'], ['good', 'Good'], ['fair', 'Fair'], ['poor', 'Poor'], ['missing', 'Missing'], ['na', 'N/A']]
const ACTIONS = [['', '—'], ['none', 'No action'], ['clean', 'Clean'], ['repair', 'Repair'], ['replace', 'Replace'], ['buy', 'Buy'], ['owner', 'Ask owner']]
const TONE = { good: 'p-ok', fair: 'p-warn', poor: 'p-bad', missing: 'p-bad', na: 'p-info' }

export default function InspectionTab({ p, onSaved }) {
  const toast = useToast()
  const [list, setList] = useState(null)
  const [cur, setCur] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = () => api.inspections(p.id).then(l => { setList(l); setCur(l[0] ? structuredClone(l[0]) : null) }).catch(setErr)
  useEffect(() => { load() }, [p.id])
  if (!list) return err ? <ErrorBox error={err} /> : <Loading />

  const start = async () => {
    setBusy(true); setErr(null)
    try { await api.startInspection({ property: p.id }); await load(); toast('Inspection started with the standard checklist.') } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  if (!cur) return (
    <section className="card"><div className="card-b" style={{ display: 'grid', gap: 12, maxWidth: 560 }}>
      <ErrorBox error={err} />
      <h2 style={{ margin: 0 }}>No inspection yet</h2>
      <p className="muted" style={{ margin: 0 }}>Start one on the day of the visit. It creates a checklist for every room (kitchen, each bedroom and bathroom, safety) plus room measurements. Book the handyman in the Schedule tab first.</p>
      <button className="btn primary" style={{ justifySelf: 'start' }} disabled={busy} onClick={start}><Icon name="checkc" small />Start inspection</button>
    </div></section>)

  const final = cur.status === 'done'
  const setItem = (id, k, v) => setCur({ ...cur, items: cur.items.map(i => i.id === id ? { ...i, [k]: v, _dirty: true } : i) })
  const setRoom = (id, k, v) => setCur({ ...cur, rooms: cur.rooms.map(r => r.id === id ? { ...r, [k]: v, _dirty: true } : r) })
  const save = async (quiet) => {
    setBusy(true); setErr(null)
    try {
      const d = await api.saveInspection(cur.id, {
        inspector: cur.inspector, inspected_on: cur.inspected_on, summary: cur.summary, photos_link: cur.photos_link,
        items: cur.items.filter(i => i._dirty).map(({ id, condition, action, est_cost, notes }) => ({ id, condition, action, est_cost, notes })),
        rooms: cur.rooms.filter(r => r._dirty || !r.id),
      })
      setCur(structuredClone(d)); if (!quiet) toast('Inspection saved.'); onSaved?.(); return true
    } catch (e) { setErr(e); return false } finally { setBusy(false) }
  }
  const complete = async () => {
    if (!(await save(true))) return
    setBusy(true)
    try { const d = await api.completeInspection(cur.id); setCur(structuredClone(d)); toast('Condition report generated. Step 4 updated.'); onSaved?.() }
    catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const allGood = (area) => setCur({ ...cur, items: cur.items.map(i => i.area === area && !i.condition ? { ...i, condition: 'good', action: 'none', _dirty: true } : i) })
  const report = async () => { try { if (!openHtml(await api.inspectionReport(cur.id))) toast('Allow pop-ups to open the report.') } catch (e) { setErr(e) } }
  const photo = async (item, file) => {
    try { const r = await api.inspectionPhoto(cur.id, item.id, file); setCur({ ...cur, items: cur.items.map(i => i.id === item.id ? { ...i, photo_url: r.photo_url } : i) }) } catch (e) { setErr(e) }
  }

  const areas = []
  cur.items.forEach(i => { let a = areas.find(x => x[0] === i.area); if (!a) areas.push(a = [i.area, []]); a[1].push(i) })
  const t = cur.totals
  const checked = cur.items.filter(i => i.condition).length

  return (
    <div className="cols">
      <div style={{ display: 'grid', gap: 18 }}>
        <ErrorBox error={err} />
        <section className="card">
          <div className="card-h"><h2>Inspection #{cur.id}</h2><span className={`pill ${final ? 'p-ok' : 'p-warn'}`}>{cur.status_label}</span><span className="spacer" />
            <button className="btn small" type="button" onClick={report}><Icon name="file" small />Condition report</button></div>
          <div className="card-b form-grid">
            <div className="field"><label htmlFor="ii">Inspector</label><input id="ii" disabled={final} value={cur.inspector} onChange={e => setCur({ ...cur, inspector: e.target.value })} /></div>
            <div className="field"><label htmlFor="id">Date</label><input id="id" type="date" disabled={final} value={cur.inspected_on || ''} onChange={e => setCur({ ...cur, inspected_on: e.target.value })} /></div>
            <div className="field" style={{ gridColumn: '1/-1' }}><label htmlFor="pl">Photos (Drive link)</label><input id="pl" type="url" disabled={final} value={cur.photos_link} onChange={e => setCur({ ...cur, photos_link: e.target.value })} placeholder="https://drive.google.com/…" /></div>
            <div className="field" style={{ gridColumn: '1/-1' }}><label htmlFor="su">Summary</label><textarea id="su" className="input" rows={2} disabled={final} value={cur.summary} onChange={e => setCur({ ...cur, summary: e.target.value })} /></div>
          </div>
        </section>

        <section className="card">
          <div className="card-h"><h2>Room measurements</h2><span className="sub">Rooms in feet · windows in inches</span></div>
          <div className="table-wrap"><table className="tight">
            <thead><tr><th>Room</th><th className="r">Length</th><th className="r">Width</th><th className="r">Sq ft</th><th className="r">Windows</th><th className="r">Window W</th><th className="r">Window H</th></tr></thead>
            <tbody>{cur.rooms.map(r => <tr key={r.id}>
              <td className="sm"><b>{r.room}</b></td>
              {['length_ft', 'width_ft'].map(k => <td key={k} className="r"><input className="input num" type="number" step="0.1" disabled={final} value={r[k] ?? ''} onChange={e => setRoom(r.id, k, e.target.value)} style={{ width: 72 }} aria-label={`${r.room} ${k}`} /></td>)}
              <td className="r num sm">{r.length_ft && r.width_ft ? (r.length_ft * r.width_ft).toFixed(0) : '—'}</td>
              {['windows', 'window_width_in', 'window_height_in'].map(k => <td key={k} className="r"><input className="input num" type="number" step={k === 'windows' ? 1 : 0.5} disabled={final} value={r[k] ?? ''} onChange={e => setRoom(r.id, k, e.target.value)} style={{ width: 80 }} aria-label={`${r.room} ${k}`} /></td>)}
            </tr>)}</tbody></table></div>
        </section>

        <section className="card">
          <div className="card-h"><h2>Checklist</h2><span className="sub">{checked} of {cur.items.length} checked</span></div>
          <div className="table-wrap"><table className="tight">
            <thead><tr><th>Item</th><th>Condition</th><th>Action</th><th className="r">Est. cost</th><th>Notes</th><th>Photo</th></tr></thead>
            <tbody>{areas.map(([area, items]) => [
              <tr className="cat" key={'a' + area}><td colSpan={6}>{area}{!final && items.some(i => !i.condition) && <button className="btn ghost small" style={{ marginLeft: 10, padding: '0 8px' }} type="button" onClick={() => allGood(area)}>Mark rest good</button>}</td></tr>,
              ...items.map(i => <tr key={i.id} className={['poor', 'missing'].includes(i.condition) ? 'flag' : ''}>
                <td className="sm">{i.item}</td>
                <td>{final ? (i.condition ? <span className={`pill ${TONE[i.condition]}`}>{CONDITIONS.find(c => c[0] === i.condition)?.[1]}</span> : '—')
                  : <select className="input" value={i.condition} onChange={e => setItem(i.id, 'condition', e.target.value)} aria-label={`${i.item} condition`}>{CONDITIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>}</td>
                <td>{final ? <span className="sm">{ACTIONS.find(a => a[0] === i.action)?.[1]}</span>
                  : <select className="input" value={i.action} onChange={e => setItem(i.id, 'action', e.target.value)} aria-label={`${i.item} action`}>{ACTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>}</td>
                <td className="r">{final ? <span className="num sm">{i.est_cost ? money(i.est_cost) : ''}</span>
                  : <input className="input num" type="number" step="1" value={i.est_cost ?? ''} onChange={e => setItem(i.id, 'est_cost', e.target.value)} style={{ width: 80 }} aria-label={`${i.item} cost`} />}</td>
                <td>{final ? <span className="sm">{i.notes}</span> : <input className="input" value={i.notes} onChange={e => setItem(i.id, 'notes', e.target.value)} aria-label={`${i.item} notes`} />}</td>
                <td>{i.photo_url ? <a href={i.photo_url} target="_blank" rel="noreferrer"><img src={i.photo_url} alt="" style={{ width: 44, height: 32, objectFit: 'cover', borderRadius: 4 }} /></a>
                  : !final && <label className="btn ghost small" style={{ padding: '0 6px' }}><Icon name="upload" small /><input type="file" accept="image/*" hidden onChange={e => e.target.files[0] && photo(i, e.target.files[0])} /></label>}</td>
              </tr>)])}</tbody></table></div>
        </section>
      </div>

      <div className="sticky">
        <section className="card">
          <div className="card-h"><h2>Report</h2></div>
          <div className="card-b" style={{ display: 'grid', gap: 10 }}>
            <div className="sum-row"><span className="muted">Checked</span><b className="num">{checked} / {cur.items.length}</b></div>
            <div className="sum-row"><span className="muted">Issues found</span><b className="num">{t.issues}</b></div>
            <div className="sum-row"><span className="muted">Actions</span><b className="num">{t.actions}</b></div>
            <div className="sum-row total"><span>Est. repairs</span><span className="num">{money(t.est_cost)}</span></div>
            {!final && <>
              <button className="btn" disabled={busy} onClick={() => save()}>Save progress</button>
              <button className="btn primary" disabled={busy || checked < cur.items.length} onClick={complete} style={{ justifyContent: 'center' }}><Icon name="check" small />Finish and generate report</button>
              {checked < cur.items.length && <div className="muted sm" style={{ textAlign: 'center' }}>{cur.items.length - checked} item(s) still need a condition</div>}
            </>}
            {final && <div className="note ok" style={{ margin: 0 }}><Icon name="checkc" small /><span>Finalised {fmtDate(cur.completed_at?.slice(0, 10))}. Open the condition report to print or save as PDF.</span></div>}
            {final && <button className="btn ghost small" disabled={busy} onClick={start}>Start a new inspection</button>}
          </div>
        </section>
        {list.length > 1 && <section className="card"><div className="card-h"><h2>Earlier inspections</h2></div>
          <div className="card-b" style={{ display: 'grid', gap: 6 }}>{list.slice(1).map(x =>
            <button key={x.id} className="btn ghost small" style={{ justifyContent: 'space-between' }} onClick={() => setCur(structuredClone(x))}>#{x.id} · {fmtDate(x.inspected_on)}<span className="muted">{x.totals.issues} issues</span></button>)}</div></section>}
      </div>
    </div>
  )
}
