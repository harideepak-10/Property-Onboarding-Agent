import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { api } from '../api'
import AgentRun from '../components/AgentRun'
import { Lightbox, Mosaic } from '../components/Gallery'
import ListingTab from './property/ListingTab'
import PhotosTab from './property/PhotosTab'
import GuestTab from './property/GuestTab'
import GoLiveTab from './property/GoLiveTab'
import { ErrorBox, Icon, Loading, Pill, Ring, STATE, STEP_STATUS, useToast } from '../components/ui'

const LICENCE_STATUSES = [['not_started', 'Not started'], ['submitted', 'Submitted'], ['returned', 'Returned by city'], ['approved', 'Approved'], ['expired', 'Expired']]

export default function PropertyDetail() {
  const { id } = useParams()
  const [p, setP] = useState(null)
  const [err, setErr] = useState(null)
  const toast = useToast()
  const [listing, setListing] = useState(null)
  const [tab, setTab] = useState('onboarding')
  const [light, setLight] = useState(null)
  const [listingRun, setListingRun] = useState(null)
  const [running, setRunning] = useState(false)
  const load = useCallback(() => Promise.all([api.property(id).then(setP), api.listing(id).then(setListing)]).catch(setErr), [id])
  useEffect(() => { setP(null); setListing(null); setTab('onboarding'); setListingRun(null); load() }, [load])

  const runListing = async () => {
    setRunning(true)
    try { const r = await api.runAgent(id, 'listing'); setListingRun(r); setTimeout(load, r.trace.length * 550 + 200) }
    catch (e) { toast(e.message) } finally { setRunning(false) }
  }

  if (err) return <ErrorBox error={err} />
  if (!p || !listing) return <Loading />
  const photos = listing.photo_set?.photos || []
  const stepsDone = p.steps.filter(s => s.status === 'done').length

  return (
    <>
      <div className="row"><Link className="btn ghost small" to="/properties"><Icon name="back" small />All properties</Link></div>
      <div className="prop-head">
        <div style={{ minWidth: 0 }}>
          <div className="row" style={{ gap: 10 }}><span className="chip mono">{p.nickname}</span><Pill map={STATE} value={p.state} /></div>
          <h1 className="prop-title">{p.address}</h1>
          <div className="res-loc" style={{ fontSize: 14 }}><Icon name="pin" small /><span>{p.city}{p.postal_code ? `, ${p.postal_code}` : ''}</span></div>
        </div>
        <div className="row">
          {p.drive_folder_url && <a className="btn" href={p.drive_folder_url} target="_blank" rel="noreferrer"><Icon name="folder" small />Drive folder</a>}
          <Link className="btn primary" to={`/procurement/${p.id}`}><Icon name="cart" small />Procurement</Link>
        </div>
      </div>

      <Mosaic photos={photos} onOpen={setLight} />
      <Lightbox photos={photos} index={light} onClose={() => setLight(null)} />

      <section className="card stat-strip">
        <div className="ss"><Ring pct={p.progress} size={64} stroke={7} /><div><b>Onboarding</b><span>{stepsDone} of 12 steps done</span></div></div>
        <div className="ss"><div className="kpi-ic ic-acc"><Icon name="sparkle" small /></div><div><b>{listing.readiness.pct}% listing-ready</b><span>{listing.readiness.checks.filter(c => !c.ok).length} checks left</span></div></div>
        <div className="ss"><div className="kpi-ic ic-info"><Icon name="bed" small /></div><div><b>{p.bedrooms} bd · {p.bathrooms} ba · {p.beds} bed{p.beds > 1 ? 's' : ''}</b><span>Unit size</span></div></div>
        <div className="ss"><div className={`kpi-ic ${p.licence?.status === 'approved' ? 'ic-ok' : p.licence?.status === 'returned' ? 'ic-bad' : 'ic-warn'}`}><Icon name="shield" small /></div><div><b>Licence: {p.licence?.status_label}</b><span>{p.licence?.expires_on ? `Expires ${p.licence.expires_on}` : 'City of Toronto'}</span></div></div>
        <div className="ss"><div className="kpi-ic ic-acc"><Icon name="user" small /></div><div><b>{p.owner_name}</b><span>{p.owner_type === 'agent' ? 'Agent' : 'Owner'}{p.lease_end ? ` · lease to ${p.lease_end}` : ''}</span></div></div>
      </section>

      <div className="ptabs" role="tablist">
        {[['onboarding', 'list', 'Onboarding', `${p.progress}%`], ['listing', 'file', 'Listing', `${listing.readiness.pct}% ready`], ['photos', 'folder', 'Photos', photos.length], ['guest', 'users', 'Guest experience', p.steps[10]?.status === 'done' ? 'Done' : `${p.steps[10]?.tasks.filter(t => t.done).length || 0}/3`], ['golive', 'sparkle', 'Go live', p.steps[11]?.status === 'done' ? 'Live' : `${p.steps[11]?.tasks.filter(t => t.done).length || 0}/4`]].map(([k, i, l, c]) =>
          <button key={k} className="ptab" role="tab" type="button" aria-selected={tab === k} onClick={() => setTab(k)}><Icon name={i} small />{l}<span className="cnt">{c}</span></button>)}
      </div>
      {tab === 'listing' && <>
        {listingRun && <section className="card"><div className="card-b"><AgentRun run={listingRun} animate /></div></section>}
        <ListingTab p={p} listing={listing} setListing={setListing} onRunAgent={runListing} running={running} />
      </>}
      {tab === 'photos' && <PhotosTab p={p} listing={listing} setListing={setListing} onOpen={setLight} />}
      {tab === 'guest' && <GuestTab p={p} onSaved={load} />}
      {tab === 'golive' && <GoLiveTab p={p} onChanged={load} />}
      {tab === 'onboarding' && <>
      <div className="cols">
        <section className="card">
          <div className="card-h"><h2>Onboarding checklist</h2><span className="sub">Steps unlock when the steps they depend on are done</span></div>
          <ol className="timeline">{p.steps.map(s => <Step key={s.id} s={s} steps={p.steps} pid={p.id} onChange={(np, msg) => { setP(np); if (msg) toast(msg) }} />)}</ol>
        </section>
        <div className="sticky">
          <AgentsCard p={p} onDone={load} />
          <PacketCard p={p} />
          <LicenceCard p={p} onSaved={() => { toast('Licence saved.'); load() }} />
          <section className="card"><div className="card-h"><h2>Details</h2></div><div className="card-b"><dl className="dl">
            <dt>Listing nickname</dt><dd className="mono">{p.nickname}</dd>
            <dt>Owner email</dt><dd>{p.owner_email || '—'}</dd>
            <dt>Lease</dt><dd className="num">{p.lease_start || '—'} → {p.lease_end || '—'}</dd>
            <dt>Unit email</dt><dd className="mono sm">{p.unit_email || 'Not created'}</dd>
            <dt>Guesty listing</dt><dd className="mono sm">{p.guesty_listing_id || '—'}</dd>
          </dl></div></section>
          <section className="card"><div className="card-h"><h2>Activity</h2><span className="sub">{p.activity.length} recent</span></div>
            <ul className="feed">{p.activity.slice(0, 12).map(a => (
              <li key={a.id}><span className="dot" /><div><div className="t"><b>{a.actor}</b> · {a.message}</div><div className="m num">{new Date(a.created_at).toLocaleString('en-CA', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</div></div></li>
            ))}</ul></section>
        </div>
      </div>
      </>}
    </>
  )
}

function Step({ s, steps, pid, onChange }) {
  const [proofFor, setProofFor] = useState(null)
  const [proof, setProof] = useState({ url: '', note: '' })
  const [mode, setMode] = useState(null) // 'block' | 'wait'
  const [text, setText] = useState('')
  const [err, setErr] = useState(null)
  const locked = s.status === 'locked'
  const unmet = s.depends_on.map(n => steps.find(x => x.number === n)).filter(x => x && x.status !== 'done')
  const doneN = s.tasks.filter(t => t.done).length
  const isAgent = s.owner_kind === 'agent'

  const tick = async (t, done, extra = {}) => {
    setErr(null)
    if (done && t.requires_proof && !t.proof_url && !t.proof_note && !extra.proof_url && !extra.proof_note) { setProofFor(t.id); return }
    try {
      const r = await api.setTask(t.id, { done, ...extra })
      setProofFor(null); setProof({ url: '', note: '' })
      const names = r.unlocked.map(n => steps.find(x => x.number === n)?.name).filter(Boolean)
      onChange(r.property, names.length ? `Unlocked: ${names.join(', ')}` : null)
    } catch (e) { setErr(e) }
  }
  const saveFlag = async () => {
    try {
      const np = mode === 'block' ? await api.blockStep(s.id, text) : await api.waitStep(s.id, text)
      setMode(null); setText(''); onChange(np)
    } catch (e) { setErr(e) }
  }

  return (
    <li className={`tl s-${s.status}`}>
      <div className="n">{s.status === 'done' ? <Icon name="check" small /> : s.number}</div>
      <div className="tl-card">
        <div className="tl-head"><h3>{s.name}</h3>
          <span className={`owner ${isAgent ? 'agent' : ''}`}><Icon name={isAgent ? 'bot' : 'user'} small />{s.owner}</span>
          <span className="spacer" /><span className="muted sm num">{doneN}/{s.tasks.length}</span><Pill map={STEP_STATUS} value={s.status} /></div>
        <ul className="tasks">
          {s.tasks.map(t => (
            <li key={t.id}>
              <label><input type="checkbox" checked={t.done} disabled={locked} onChange={e => tick(t, e.target.checked)} />
                <span className={t.done ? 'done-t' : ''}>{t.title}{t.requires_proof && !t.done && <span className="muted sm"> · needs proof</span>}</span></label>
              {(t.proof_url || t.proof_note) && <span className="proof-link">{t.proof_url ? <a href={t.proof_url} target="_blank" rel="noreferrer">Proof link</a> : t.proof_note}{t.done_by ? ` · ${t.done_by}` : ''}</span>}
              {proofFor === t.id && (
                <div className="proof-form">
                  <span className="sm"><b>Add proof</b> for “{t.title}”</span>
                  <input className="input" placeholder="Link (Drive, email, portal…)" type="url" value={proof.url} onChange={e => setProof({ ...proof, url: e.target.value })} />
                  <input className="input" placeholder="Or a short note" value={proof.note} onChange={e => setProof({ ...proof, note: e.target.value })} />
                  <div className="row" style={{ gap: 8 }}><button className="btn small primary" type="button" disabled={!proof.url && !proof.note} onClick={() => tick(t, true, { proof_url: proof.url, proof_note: proof.note })}>Mark done</button>
                    <button className="btn small ghost" type="button" onClick={() => setProofFor(null)}>Cancel</button></div>
                </div>
              )}
            </li>
          ))}
        </ul>
        {err && <div className="note bad"><Icon name="alert" small /><span>{err.message}</span></div>}
        {s.status === 'blocked' && <div className="note bad"><Icon name="alert" small /><div><b>Blocked.</b> {s.blocked_reason}
          <div style={{ marginTop: 8 }}><button className="btn small" type="button" onClick={async () => onChange(await api.blockStep(s.id, ''))}>Mark as resolved</button></div></div></div>}
        {locked && <div className="note info"><Icon name="lock" small /><span>Unlocks when {unmet.map(u => `step ${u.number} (${u.name})`).join(' and ')} {unmet.length > 1 ? 'are' : 'is'} complete.</span></div>}
        {s.status === 'waiting' && <div className="note warn"><Icon name="clock" small /><div>{s.waiting_note}
          <div style={{ marginTop: 8 }}><button className="btn small" type="button" onClick={async () => onChange(await api.waitStep(s.id, ''))}>Clear</button></div></div></div>}
        {(s.number === 5 || s.number === 6) && !locked && s.status !== 'done' && <div style={{ marginTop: 10 }}><Link className="btn small" to={`/procurement/${pid}`}><Icon name="cart" small />Open procurement</Link></div>}
        {!locked && s.status !== 'done' && s.status !== 'blocked' && (
          mode ? (
            <div className="inline-form">
              <input className="input" autoFocus placeholder={mode === 'block' ? 'What is blocking this step?' : 'Who or what are we waiting on?'} value={text} onChange={e => setText(e.target.value)} />
              <button className="btn small primary" type="button" disabled={!text.trim()} onClick={saveFlag}>Save</button>
              <button className="btn small ghost" type="button" onClick={() => setMode(null)}>Cancel</button>
            </div>
          ) : (
            <div className="row" style={{ gap: 6, marginTop: 10 }}>
              <button className="btn small ghost" type="button" onClick={() => setMode('block')}>Mark blocked</button>
              {s.status !== 'waiting' && <button className="btn small ghost" type="button" onClick={() => setMode('wait')}>Waiting on someone</button>}
            </div>
          )
        )}
      </div>
    </li>
  )
}

function LicenceCard({ p, onSaved }) {
  const [f, setF] = useState({ status: p.licence?.status || 'not_started', number: p.licence?.number || '', submitted_on: p.licence?.submitted_on || '', expires_on: p.licence?.expires_on || '' })
  const [err, setErr] = useState(null)
  const set = k => e => setF({ ...f, [k]: e.target.value })
  const save = async (e) => {
    e.preventDefault(); setErr(null)
    const body = { ...f }; ['submitted_on', 'expires_on'].forEach(k => { if (!body[k]) body[k] = null })
    try { await api.updateLicence(p.id, body); onSaved() } catch (e2) { setErr(e2) }
  }
  return (
    <section className="card">
      <div className="card-h"><h2>STR licence</h2><span className="sub">City of Toronto</span></div>
      <form className="card-b" style={{ display: 'grid', gap: 12 }} onSubmit={save}>
        <ErrorBox error={err} />
        <div className="field"><label htmlFor="lic-status">Status</label><select id="lic-status" value={f.status} onChange={set('status')}>{LICENCE_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        <div className="field"><label htmlFor="lic-no">Licence number</label><input id="lic-no" value={f.number} onChange={set('number')} placeholder="STR-2026-…" /></div>
        <div className="counts" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className="field"><label htmlFor="lic-sub">Submitted</label><input id="lic-sub" type="date" value={f.submitted_on} onChange={set('submitted_on')} /></div>
          <div className="field"><label htmlFor="lic-exp">Expires</label><input id="lic-exp" type="date" value={f.expires_on} onChange={set('expires_on')} /></div>
        </div>
        <button className="btn small" type="submit" style={{ justifySelf: 'start' }}>Save licence</button>
      </form>
    </section>
  )
}

function AgentsCard({ p, onDone }) {
  const loc = useLocation()
  const fresh = loc.state?.run
  const [run, setRun] = useState(fresh && fresh.property === p.id ? fresh : null)
  const [animate, setAnimate] = useState(Boolean(fresh))
  const [drafts, setDrafts] = useState([])
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  const refresh = useCallback(() => {
    api.emails({ property: p.id, status: 'draft' }).then(setDrafts).catch(() => {})
  }, [p.id])
  useEffect(() => {
    refresh()
    if (!run) api.agentRuns(p.id).then(r => r[0] && setRun(r[0])).catch(() => {})
  }, [p.id])

  const go = async (agent) => {
    setBusy(agent); setErr(null)
    try { const r = await api.runAgent(p.id, agent); setRun(r); setAnimate(true); refresh(); setTimeout(onDone, r.trace.length * 550 + 200) }
    catch (e) { setErr(e) } finally { setBusy(null) }
  }
  return (
    <section className="card">
      <div className="card-h"><h2>AI agents</h2><span className="spacer" />
        {drafts.length > 0 && <Link className="pill p-bad nodot" to="/approvals">{drafts.length} email{drafts.length > 1 ? 's' : ''} to approve</Link>}</div>
      <div className="card-b" style={{ display: 'grid', gap: 14 }}>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn small" type="button" disabled={!!busy} onClick={() => go('intake')}>{busy === 'intake' ? <span className="spin" /> : <Icon name="bot" small />}Run Intake</button>
          <button className="btn small" type="button" disabled={!!busy} onClick={() => go('compliance')}>{busy === 'compliance' ? <span className="spin" /> : <Icon name="shield" small />}Run Compliance</button>
          <button className="btn small" type="button" disabled={!!busy} onClick={() => go('listing')}>{busy === 'listing' ? <span className="spin" /> : <Icon name="file" small />}Run Listing</button>
        </div>
        <ErrorBox error={err} />
        {run ? <AgentRun run={run} animate={animate} /> : <span className="muted sm">No agent has run on this property yet.</span>}
      </div>
    </section>
  )
}

const PACKET_STATUS = [['missing', 'Missing'], ['requested', 'Requested'], ['received', 'Received'], ['not_needed', 'Not needed']]

function PacketCard({ p }) {
  const [items, setItems] = useState(null)
  const load = useCallback(() => api.complianceItems(p.id).then(setItems).catch(() => setItems([])), [p.id])
  useEffect(() => { load() }, [load, p.activity.length])
  if (!items || !items.length) return null
  const ready = items.filter(i => ['received', 'not_needed'].includes(i.status)).length
  const update = async (i, status) => { await api.updateComplianceItem(i.id, { status }); load() }
  return (
    <section className="card">
      <div className="card-h"><h2>Licence packet</h2><span className="spacer" /><b className="num sm">{ready}/{items.length}</b></div>
      <div className="card-b" style={{ paddingTop: 6, paddingBottom: 10 }}>
        {items.map(i => (
          <div className="packet-row" key={i.id}>
            <div style={{ minWidth: 0 }}><div className="sm" style={{ fontWeight: 600 }}>{i.label}</div><div className="muted sm">From the {i.source}{i.note ? ` · ${i.note}` : ''}</div></div>
            <select value={i.status} onChange={e => update(i, e.target.value)} aria-label={`Status of ${i.label}`}>{PACKET_STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </div>
        ))}
        <div className="muted sm" style={{ marginTop: 8 }}>Default list. Confirm the City's exact requirements with the client.</div>
      </div>
    </section>
  )
}
