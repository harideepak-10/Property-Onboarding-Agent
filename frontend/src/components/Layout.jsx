import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Icon } from './ui'
import NewPropertyDialog from './NewPropertyDialog'

const TITLES = { '': 'Dashboard', properties: 'Properties', procurement: 'Procurement', 'master-list': 'Master list', approvals: 'Approvals', licences: 'Licences', buildings: 'Buildings' }
const INT_LABEL = { live: 'live', dry_run: 'dry run', heuristic: 'basic reader' }

export default function Layout({ user, onLogout }) {
  const loc = useLocation()
  const nav = useNavigate()
  const [counts, setCounts] = useState({ onboarding: 0, alerts: 0, drafts: 0 })
  const [integ, setInteg] = useState(null)
  const [newOpen, setNewOpen] = useState(false)
  const [q, setQ] = useState('')
  const section = loc.pathname.split('/')[1] || ''

  useEffect(() => {
    Promise.all([api.dashboard(), api.emails({ status: 'draft' })])
      .then(([d, e]) => setCounts({ onboarding: d.kpis.onboarding, alerts: d.attention.length, drafts: e.length })).catch(() => {})
  }, [loc.pathname, loc.key])
  useEffect(() => { api.integrations().then(setInteg).catch(() => {}) }, [])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
        e.preventDefault(); document.getElementById('global-search')?.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const search = (e) => { e.preventDefault(); nav(`/properties?q=${encodeURIComponent(q)}`) }
  const initials = (user?.name || 'U').split(' ').map(s => s[0]).join('').slice(0, 2).toUpperCase()

  return (
    <div className="app">
      <aside className="side">
        <div className="logo"><div className="logo-mark">PO</div><div><b>Onboarding</b><span>STR operations</span></div></div>
        <div className="nav-label">Workspace</div>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end><Icon name="grid" />Dashboard</NavLink>
          <NavLink to="/properties"><Icon name="home" />Properties<span className="badge">{counts.onboarding}</span></NavLink>
          <NavLink to="/procurement"><Icon name="cart" />Procurement</NavLink>
          <NavLink to="/approvals"><Icon name="mail" />Approvals{counts.drafts > 0 && <span className="badge red">{counts.drafts}</span>}</NavLink>
          <NavLink to="/licences"><Icon name="shield" />Licences</NavLink>
          <NavLink to="/buildings"><Icon name="building" />Buildings</NavLink>
          <NavLink to="/master-list"><Icon name="list" />Master list</NavLink>
        </nav>
        {integ && <div className="side-promo">
          <b>Agents</b>
          <p>Intake, Compliance and Listing agents prepare the work. Emails and go-live wait for your approval.</p>
          <div className="int-chips">
            <span>Claude: {INT_LABEL[integ.anthropic]}</span>
            {integ.guesty && <span>Guesty: {INT_LABEL[integ.guesty]}</span>}
            {Object.entries(integ.google).map(([k, v]) => <span key={k}>{k[0].toUpperCase() + k.slice(1)}: {INT_LABEL[v]}</span>)}
          </div>
        </div>}
        <div className="side-foot">
          <div className="avatar">{initials}</div>
          <div style={{ flex: 1, minWidth: 0 }}><b>{user?.name}</b><span>Signed in</span></div>
          <button className="icon-btn" type="button" onClick={onLogout} aria-label="Sign out" title="Sign out"><Icon name="logout" small /></button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="crumbs"><span>Workspace</span><span>/</span><b>{TITLES[section] || 'Properties'}</b></div>
          <span className="spacer" />
          <form className="search" onSubmit={search}>
            <Icon name="search" small />
            <input id="global-search" value={q} onChange={e => setQ(e.target.value)} placeholder="Search properties" aria-label="Search properties" />
            <span className="kbd">/</span>
          </form>
          <button className="icon-btn" type="button" aria-label="Alerts" onClick={() => nav('/')}>
            <Icon name="alert" />{counts.alerts > 0 && <span className="dot">{counts.alerts}</span>}
          </button>
          <button className="btn primary" type="button" onClick={() => setNewOpen(true)}><Icon name="plus" small />New property</button>
        </header>
        <main className="content"><Outlet /></main>
      </div>
      {newOpen && <NewPropertyDialog onClose={() => setNewOpen(false)} onCreated={(p, run) => { setNewOpen(false); nav(`/properties/${p.id}`, { state: { run } }) }} />}
    </div>
  )
}
