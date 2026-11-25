import { useEffect, useState } from 'react'
import { api } from '../../api'
import AgentRun from '../../components/AgentRun'
import { ErrorBox, Icon, Loading, useCan, useToast } from '../../components/ui'

const CH_KEY = { Airbnb: 'airbnb', 'Booking.com': 'booking', 'Direct-booking site': 'direct' }

export default function GoLiveTab({ p, onChanged }) {
  const toast = useToast()
  const [d, setD] = useState(null)
  const [run, setRun] = useState(null)
  const [confirm, setConfirm] = useState(false)
  const [unlisting, setUnlisting] = useState(false)
  const canApprove = useCan('approve_go_live')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => { api.goLive(p.id).then(setD).catch(setErr) }, [p.id])
  if (!d) return err ? <ErrorBox error={err} /> : <Loading />

  const act = async (fn, msg) => {
    setBusy(true); setErr(null)
    try { const r = await fn(); setD(r); if (r.run) setRun(r.run); if (msg) toast(msg); onChanged?.() } catch (e) { setErr(e) } finally { setBusy(false); setConfirm(false) }
  }
  const blocking = d.checks.filter(c => c.blocking && !c.ok).length
  const allChannels = d.channels.every(c => c.live)

  return (
    <div className="cols">
      <div style={{ display: 'grid', gap: 22, minWidth: 0 }}>
        <section className="card">
          <div className="card-h"><h2>Final check</h2><span className="spacer" />
            <span className={`pill ${d.is_listed ? 'p-ok' : d.ready ? 'p-acc' : 'p-warn'}`}>{d.is_listed ? 'Listed' : d.ready ? 'Ready to go live' : `${blocking} to fix`}</span></div>
          <div className="card-b" style={{ display: 'grid', gap: 12 }}>
            <ErrorBox error={err} />
            {d.checks.map(c => (
              <div key={c.label} className={`rcheck ${c.ok ? 'ok' : ''}`} style={!c.ok && c.blocking ? { color: 'var(--ink)' } : undefined}>
                <Icon name={c.ok ? 'checkc' : c.blocking ? 'alert' : 'clock'} small />
                <span><b style={{ fontWeight: 600 }}>{c.label}</b>{!c.blocking && <span className="muted"> · advisory</span>}{c.detail && <div className="muted sm">{c.detail}</div>}</span>
              </div>))}
          </div>
        </section>
        {run && <section className="card"><div className="card-b"><AgentRun run={run} animate /></div></section>}
        {d.is_listed && <section className="card">
          <div className="card-h"><h2>Confirm each channel</h2><span className="sub">Open the live listing and check the photos, price and licence number</span></div>
          <div className="card-b" style={{ display: 'grid', gap: 12 }}>
            {d.channels.map(c => (
              <div key={c.name} className="sum-row" style={{ padding: 0, alignItems: 'center' }}><span>{c.name}</span>
                {c.live ? <span className="pill p-ok">Live</span>
                  : <button className="btn small" type="button" disabled={busy} onClick={() => act(() => api.confirmChannel(p.id, CH_KEY[c.name]), `${c.name} confirmed live.`)}>Mark live</button>}</div>))}
            {allChannels && <div className="note ok" style={{ margin: 0 }}><Icon name="checkc" small /><span>Live everywhere. Onboarding is complete.</span></div>}
          </div>
        </section>}
      </div>
      <div className="sticky">
        <section className="card">
          <div className="card-h"><h2>{d.is_listed ? 'Listed' : 'Go live'}</h2>{d.dry_run && <span className="dry">Dry run</span>}</div>
          <div className="card-b" style={{ display: 'grid', gap: 12 }}>
            {!d.is_listed ? <>
              <span className="muted sm">Approving lists the property on its connected channels in Guesty (Airbnb, Booking.com and the direct site).</span>
              {!confirm ? <button className="btn primary" type="button" disabled={!d.ready || busy} onClick={() => setConfirm(true)} style={{ justifyContent: 'center' }}><Icon name="sparkle" small />Approve go-live</button>
                : <div className="note warn" style={{ margin: 0 }}><Icon name="alert" small /><div>List <b className="mono">{p.nickname}</b> on all connected channels now?
                  <div className="row" style={{ gap: 8, marginTop: 10 }}><button className="btn small primary" type="button" disabled={busy || !canApprove} title={canApprove ? '' : 'A manager or admin approves go-live'} onClick={() => act(() => api.approveGoLive(p.id), 'Approved. The property is listed.')}>Yes, go live</button>
                    <button className="btn small ghost" type="button" onClick={() => setConfirm(false)}>Cancel</button></div></div></div>}
              {!d.ready && <span className="muted sm" style={{ textAlign: 'center' }}>Fix the items marked with a warning first.</span>}
            </> : <>
              <div className="sum-row" style={{ padding: 0 }}><span className="muted">Listed</span><span className="sm">{new Date(d.listed_at).toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' })}</span></div>
              <div className="sum-row" style={{ padding: 0 }}><span className="muted">Guesty ID</span><span className="mono sm">{d.guesty_listing_id}</span></div>
              {!unlisting ? <button className="btn ghost small" type="button" disabled={!canApprove} onClick={() => setUnlisting(true)} style={{ justifySelf: 'start' }}>Unlist property…</button>
                : <form style={{ display: 'grid', gap: 8 }} onSubmit={e => { e.preventDefault(); act(() => api.unlist(p.id, reason), 'Property unlisted.'); setUnlisting(false) }}>
                  <input className="input" placeholder="Reason (e.g. licence renewal, repairs)" value={reason} onChange={e => setReason(e.target.value)} required aria-label="Reason for unlisting" />
                  <div className="row" style={{ gap: 8 }}><button className="btn small" type="submit" disabled={busy}>Unlist</button><button className="btn small ghost" type="button" onClick={() => setUnlisting(false)}>Cancel</button></div>
                </form>}
            </>}
          </div>
        </section>
      </div>
    </div>
  )
}
