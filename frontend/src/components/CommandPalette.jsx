import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Icon } from './ui'

const PAGES = [
  ['Dashboard', '/', 'grid'], ['Properties', '/properties', 'home'], ['Procurement', '/procurement', 'cart'],
  ['Purchasing', '/purchasing', 'truck'], ['Schedule', '/schedule', 'cal'], ['Approvals', '/approvals', 'mail'],
  ['Licences', '/licences', 'shield'], ['Buildings', '/buildings', 'building'], ['Master list', '/master-list', 'list'],
  ['Reports', '/reports', 'chart'],
]

/** ⌘K / Ctrl+K: jump to any property or page. */
export default function CommandPalette({ open, onClose, onNewProperty }) {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [props, setProps] = useState([])
  const [sel, setSel] = useState(0)
  const input = useRef()

  useEffect(() => {
    if (!open) return
    setQ(''); setSel(0)
    api.properties().then(setProps).catch(() => {})
    setTimeout(() => input.current?.focus(), 10)
  }, [open])

  const items = useMemo(() => {
    const t = q.trim().toLowerCase()
    const m = (s) => !t || s.toLowerCase().includes(t)
    const out = []
    props.filter(p => m(`${p.nickname} ${p.address} ${p.owner_name} ${p.listing_title || ''}`)).slice(0, 6)
      .forEach(p => out.push({ group: 'Properties', label: p.address, sub: p.nickname, img: p.cover_url, go: () => nav(`/properties/${p.id}`) }))
    PAGES.filter(([l]) => m(l)).forEach(([l, to, icon]) => out.push({ group: 'Go to', label: l, icon, go: () => nav(to) }))
    if (m('new property add')) out.push({ group: 'Actions', label: 'New property', icon: 'plus', go: onNewProperty })
    return out
  }, [q, props])

  useEffect(() => { setSel(0) }, [q])
  if (!open) return null
  const run = (it) => { onClose(); it.go() }
  const key = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(items.length - 1, s + 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(0, s - 1)) }
    if (e.key === 'Enter' && items[sel]) run(items[sel])
    if (e.key === 'Escape') onClose()
  }
  let last = ''
  return (
    <div className="cmdk-back" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="cmdk" role="dialog" aria-label="Search">
        <div className="cmdk-in"><Icon name="search" /><input ref={input} value={q} onChange={e => setQ(e.target.value)} onKeyDown={key}
          placeholder="Search properties, pages, actions…" aria-label="Search" /><span className="kbd">esc</span></div>
        <div className="cmdk-list" role="listbox">
          {items.map((it, i) => {
            const head = it.group !== last ? (last = it.group, <div className="cmdk-g" key={'g' + it.group}>{it.group}</div>) : null
            return [head, <div key={i} className="cmdk-i" role="option" aria-selected={i === sel} onMouseEnter={() => setSel(i)} onClick={() => run(it)}>
              {it.group === 'Properties' ? (it.img ? <img src={it.img} alt="" /> : <span className="kpi-ic ic-acc" style={{ width: 36, height: 26 }}><Icon name="home" small /></span>) : <Icon name={it.icon} small />}
              <span>{it.label}</span>{it.sub && <span className="sub mono">{it.sub}</span>}</div>]
          })}
          {!items.length && <div className="cmdk-i muted">No matches</div>}
        </div>
        <div className="cmdk-f"><span>↑↓ to move</span><span>↵ to open</span><span>esc to close</span></div>
      </div>
    </div>
  )
}
