import { useEffect, useState } from 'react'
import { api, fmtDate, money } from '../api'
import { CountUp, ErrorBox, Icon, Loading, useCan, useToast } from '../components/ui'

const ICONS = { portfolio: 'grid', property: 'home', spending: 'dollar', licences: 'shield' }
const USES_PERIOD = { portfolio: true, spending: true }
const USES_PROPERTY = { property: 'required', spending: 'optional' }

function cell(v, type) {
  if (v === null || v === undefined || v === '') return ''
  if (typeof v === 'string' && type !== 'date') return v
  if (type === 'money') return typeof v === 'string' ? v : money(v)
  if (type === 'pct') return `${Math.round(v * 100)}%`
  if (type === 'date') return /^\d{4}-\d{2}-\d{2}/.test(v) ? fmtDate(v.slice(0, 10)) : v
  if (type === 'num') return typeof v === 'number' ? v.toLocaleString('en-CA', { maximumFractionDigits: 1 }) : v
  return String(v)
}
const RIGHT = { money: 1, int: 1, num: 1, pct: 1 }

export default function Reports() {
  const toast = useToast()
  const [meta, setMeta] = useState(null)
  const [props, setProps] = useState([])
  const [key, setKey] = useState('portfolio')
  const [f, setF] = useState({ period: 'this_month', from: '', to: '', property: '', spendProp: '' })
  const [rep, setRep] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState(null)
  const [digest, setDigest] = useState(null)
  const canSend = useCan('send_emails')

  useEffect(() => {
    api.reports().then(setMeta).catch(setErr)
    api.properties().then(p => { setProps(p); setF(x => ({ ...x, property: x.property || String(p[0]?.id || '') })) }).catch(() => {})
    api.digest().then(setDigest).catch(() => {})
  }, [])

  const params = () => {
    const p = {}
    if (USES_PERIOD[key]) { p.period = f.period; if (f.period === 'custom') { p.from = f.from; p.to = f.to } }
    const prop = key === 'spending' ? f.spendProp : f.property
    if (USES_PROPERTY[key] && prop) p.property = prop
    return p
  }
  const ready = !(USES_PERIOD[key] && f.period === 'custom' && (!f.from || !f.to)) && !(USES_PROPERTY[key] === 'required' && !f.property)
  const sig = JSON.stringify([key, params()])

  useEffect(() => {
    if (!ready) return
    setLoading(true); setErr(null)
    api.report(key, params()).then(setRep).catch(setErr).finally(() => setLoading(false))
  }, [sig, ready])

  const download = async (kind) => {
    setBusy(kind)
    try { await api.reportFile(key, params(), kind); toast(`${kind === 'xlsx' ? 'Excel' : kind.toUpperCase()} downloaded.`) }
    catch (e) { toast(e.message) } finally { setBusy('') }
  }
  const send = async () => {
    try { const r = await api.sendDigest(); toast(r.some(n => n.dry_run) ? 'Summary prepared (dry run until Gmail is connected).' : 'Summary sent.'); setDigest(await api.digest()) }
    catch (e) { toast(e.message) }
  }

  if (!meta) return err ? <ErrorBox error={err} /> : <Loading />
  const set = k => e => setF({ ...f, [k]: e.target.value })

  return (
    <>
      <div className="page-head"><div><h1>Reports</h1><p>Pick a report, choose the period, and download it as a PDF for the client or Excel for accounting.</p></div></div>

      <div className="report-picker stagger">
        {meta.catalog.map(r => (
          <button key={r.key} type="button" className={`rp ${key === r.key ? 'on' : ''}`} onClick={() => { setKey(r.key); setRep(null) }}>
            <span className="kpi-ic ic-acc"><Icon name={ICONS[r.key]} small /></span>
            <b>{r.title}</b><span>{r.about}</span>
          </button>
        ))}
      </div>

      <section className="card report-bar">
        <div className="row" style={{ gap: 12, alignItems: 'flex-end' }}>
          {USES_PERIOD[key] && <div className="field" style={{ width: 180 }}><label htmlFor="rp-period">Period</label>
            <select id="rp-period" value={f.period} onChange={set('period')}>{meta.periods.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}</select></div>}
          {USES_PERIOD[key] && f.period === 'custom' && <>
            <div className="field" style={{ width: 160 }}><label htmlFor="rp-from">From</label><input id="rp-from" type="date" value={f.from} onChange={set('from')} /></div>
            <div className="field" style={{ width: 160 }}><label htmlFor="rp-to">To</label><input id="rp-to" type="date" value={f.to} onChange={set('to')} /></div></>}
          {USES_PROPERTY[key] && <div className="field" style={{ width: 230 }}><label htmlFor="rp-prop">Property</label>
            <select id="rp-prop" className="mono" value={key === 'spending' ? f.spendProp : f.property}
              onChange={e => setF({ ...f, [key === 'spending' ? 'spendProp' : 'property']: e.target.value })}>
              {USES_PROPERTY[key] === 'optional' && <option value="">All properties</option>}
              {props.map(p => <option key={p.id} value={p.id}>{p.nickname}</option>)}</select></div>}
          {!USES_PERIOD[key] && !USES_PROPERTY[key] && <span className="muted sm" style={{ paddingBottom: 9 }}>Shows every licence as of today.</span>}
          <span className="spacer" />
          <button className="btn primary" type="button" disabled={!ready || !!busy} onClick={() => download('pdf')}><Icon name="file" small />{busy === 'pdf' ? 'Preparing…' : 'Download PDF'}</button>
          <button className="btn" type="button" disabled={!ready || !!busy} onClick={() => download('xlsx')}><Icon name="download" small />{busy === 'xlsx' ? 'Preparing…' : 'Excel'}</button>
          <button className="btn" type="button" disabled={!ready || !!busy} onClick={() => download('csv')}><Icon name="download" small />CSV</button>
        </div>
      </section>

      <ErrorBox error={err} />
      {!ready ? <div className="card empty">Pick the dates for a custom period.</div>
        : (loading && !rep) ? <Loading />
        : rep && <article className={`report-doc ${loading ? 'dim' : ''}`}>
          <header>
            <div className="muted sm">{rep.eyebrow}</div>
            <h2 className="rd-title">{rep.title}</h2>
            <div className="muted">{rep.subtitle}</div>
          </header>
          <div className="rd-kpis">{rep.kpis.map(k => (
            <div key={k.label}><span>{k.label}</span>
              <b>{k.type === 'money' ? <CountUp value={k.value} format={v => money(v)} /> : k.type === 'pct' ? <CountUp value={`${Math.round(k.value * 100)}%`} /> : <CountUp value={k.value} />}</b>
              <small>{k.detail}</small></div>))}</div>
          {rep.note && <p className="muted sm" style={{ margin: 0 }}>{rep.note}</p>}
          {rep.sections.map(s => {
            const kv = s.columns.every(c => !c.label)
            return <section key={s.title} className="rd-sec">
              <h3>{s.title}</h3>{s.note && <p className="muted sm">{s.note}</p>}
              <div className="table-wrap"><table className={`tight ${kv ? 'kv' : ''}`}>
                {!kv && <thead><tr>{s.columns.map(c => <th key={c.key} className={RIGHT[c.type] ? 'r' : ''}>{c.label}</th>)}</tr></thead>}
                <tbody>
                  {s.rows.map((r, i) => <tr key={i}>{s.columns.map(c => <td key={c.key} className={`${RIGHT[c.type] ? 'r num' : ''} sm`}>{cell(r[c.key], c.type)}</td>)}</tr>)}
                  {!s.rows.length && <tr><td colSpan={s.columns.length} className="muted sm">Nothing in this period.</td></tr>}
                  {s.total && <tr className="rd-total">{s.columns.map(c => <td key={c.key} className={`${RIGHT[c.type] ? 'r num' : ''} sm`}>{cell(s.total[c.key], c.type)}</td>)}</tr>}
                </tbody></table></div>
            </section>
          })}
          <footer className="muted sm">Generated {new Date(rep.generated).toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' })}</footer>
        </article>}

      <section className="card">
        <div className="card-h"><h2>Daily summary email</h2><span className="sub">Sent to the ops inbox each morning by the daily check (and Slack if set up)</span><span className="spacer" />
          {canSend && <button className="btn small" type="button" onClick={send}><Icon name="send" small />Send now</button>}</div>
        {digest && <div className="card-b"><pre className="sm" style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit', color: 'var(--ink-2)' }}>{digest.preview}</pre>
          {digest.recent?.length > 0 && <div className="muted sm" style={{ marginTop: 10 }}>Last sent {new Date(digest.recent[0].sent_at).toLocaleString('en-CA')}{digest.recent[0].dry_run ? ' (dry run)' : ''}</div>}</div>}
      </section>
    </>
  )
}
