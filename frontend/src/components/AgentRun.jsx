import { useEffect, useState } from 'react'
import { Icon } from './ui'

const ICON = { ok: 'check', warn: 'alert', error: 'alert', skip: 'info' }
const STATUS = { succeeded: ['p-ok', 'Finished'], partial: ['p-warn', 'Finished with warnings'], failed: ['p-bad', 'Failed'], running: ['p-acc', 'Running'] }

/** Plays an agent's trace back step by step when `animate` is set, so people can watch it work. */
export default function AgentRun({ run, animate = false }) {
  const [shown, setShown] = useState(animate ? 0 : run.trace.length)

  useEffect(() => {
    if (!animate) { setShown(run.trace.length); return }
    setShown(0)
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduce) { setShown(run.trace.length); return }
    let i = 0
    const t = setInterval(() => { i += 1; setShown(i); if (i >= run.trace.length) clearInterval(t) }, 550)
    return () => clearInterval(t)
  }, [run.id, animate, run.trace.length])

  const done = shown >= run.trace.length
  const [cls, label] = done ? (STATUS[run.status] || STATUS.running) : STATUS.running
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="row" style={{ gap: 8 }}><b className="sm">{run.agent_label}</b><span className={`pill ${cls}`}>{label}</span>
        <span className="spacer" /><span className="muted sm">{new Date(run.started_at).toLocaleString('en-CA', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span></div>
      <ul className="trace">
        {run.trace.slice(0, shown).map((s, i) => (
          <li key={i}><span className={`tdot ${s.status}`}><Icon name={ICON[s.status] || 'check'} small /></span>
            <div><b>{s.label}</b>{s.dry_run && <span className="dry">Dry run</span>}{s.detail && <div className="td">{s.detail}</div>}</div></li>
        ))}
        {!done && <li><span className="tdot pending"><span className="spin" /></span><div><b className="muted">Working…</b></div></li>}
      </ul>
    </div>
  )
}
