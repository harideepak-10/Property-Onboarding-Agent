import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { ErrorBox, Icon, Loading, useCan, useToast } from '../components/ui'

export default function Approvals() {
  const canSend = useCan('send_emails')
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'draft'
  const [list, setList] = useState(null)
  const [sel, setSel] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  const load = (keep) => api.emails({ status: tab }).then(l => {
    setList(l)
    setSel(cur => l.find(x => x.id === (keep ?? cur?.id)) || l[0] || null)
  }).catch(setErr)
  useEffect(() => { setList(null); setSel(null); load() }, [tab])

  const save = async () => {
    const d = await api.updateEmail(sel.id, { to: sel.to, cc: sel.cc, subject: sel.subject, body: sel.body })
    setSel(d); return d
  }
  const act = async (fn, msg) => {
    setBusy(true); setErr(null)
    try { await fn(); toast(msg); await load(null) } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <>
      <div className="page-head"><div><h1>Approvals</h1><p>Emails the agents drafted. Nothing is sent until you review and approve it.</p></div><span className="spacer" />
        <div className="seg" role="group" aria-label="Show">
          {[['draft', 'Needs review'], ['sent', 'Sent'], ['discarded', 'Discarded']].map(([k, l]) =>
            <button key={k} type="button" aria-pressed={tab === k} onClick={() => setParams({ tab: k })}>{l}</button>)}</div></div>
      <ErrorBox error={err} />
      {!list ? <Loading /> : !list.length ? <div className="card empty">{tab === 'draft' ? 'All caught up. No emails waiting for review.' : 'Nothing here yet.'}</div> : (
        <div className="cols" style={{ gridTemplateColumns: 'minmax(260px,360px) minmax(0,1fr)' }}>
          <section className="card" style={{ alignSelf: 'start' }}>
            <ul className="mail-list">{list.map(m => (
              <li key={m.id} aria-current={sel?.id === m.id} onClick={() => setSel(m)} tabIndex={0} onKeyDown={e => e.key === 'Enter' && setSel(m)}>
                <span className="row sm" style={{ gap: 6 }}><span className="mono">{m.property_nickname}</span><span className="spacer" />{m.warning && <span className="pill p-warn nodot">Check</span>}</span>
                <b className="sm">{m.subject}</b>
                <span className="muted sm">{m.kind_label} · {m.created_by_agent}</span>
              </li>))}</ul>
          </section>
          {sel && <section className="card">
            <div className="card-h"><div><h2>{sel.kind_label}</h2><div className="sub">For <Link to={`/properties/${sel.property}`} className="mono">{sel.property_nickname}</Link> · drafted by {sel.created_by_agent}</div></div></div>
            <div className="card-b mail-editor">
              {sel.warning && <div className="note warn" style={{ margin: 0 }}><Icon name="alert" small /><span>{sel.warning}</span></div>}
              {sel.status === 'sent' && <div className="note ok" style={{ margin: 0 }}><Icon name="checkc" small /><span>{sel.sent_dry_run ? 'Dry run: logged as sent, but no email left the system (Gmail not connected yet).' : `Sent ${new Date(sel.sent_at).toLocaleString('en-CA')}.`}</span></div>}
              <div className="form-grid">
                <div className="field"><label htmlFor="m-to">To</label><input id="m-to" value={sel.to} disabled={sel.status !== 'draft'} onChange={e => setSel({ ...sel, to: e.target.value })} placeholder="name@example.com" /></div>
                <div className="field"><label htmlFor="m-cc">Cc</label><input id="m-cc" value={sel.cc} disabled={sel.status !== 'draft'} onChange={e => setSel({ ...sel, cc: e.target.value })} /></div>
              </div>
              <div className="field"><label htmlFor="m-sub">Subject</label><input id="m-sub" value={sel.subject} disabled={sel.status !== 'draft'} onChange={e => setSel({ ...sel, subject: e.target.value })} /></div>
              <div className="field"><label htmlFor="m-body">Message</label><textarea id="m-body" value={sel.body} disabled={sel.status !== 'draft'} onChange={e => setSel({ ...sel, body: e.target.value })} /></div>
              {sel.attachment && <span className="chip" style={{ justifySelf: 'start' }}><Icon name="file" small />{sel.attachment}</span>}
              {sel.status === 'draft' && <div className="row">
                <button className="btn primary" type="button" disabled={busy || !sel.to.trim() || !canSend} title={canSend ? '' : 'A manager or admin sends emails'} onClick={() => act(async () => { await save(); await api.sendEmail(sel.id) }, 'Email approved and sent.')}><Icon name="send" small />Approve and send</button>
                <button className="btn" type="button" disabled={busy} onClick={() => act(save, 'Draft saved.')}>Save changes</button>
                <span className="spacer" />
                <button className="btn ghost" type="button" disabled={busy} onClick={() => act(() => api.discardEmail(sel.id), 'Draft discarded.')}>Discard</button>
              </div>}
            </div>
          </section>}
        </div>
      )}
    </>
  )
}
