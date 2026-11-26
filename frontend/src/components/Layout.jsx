import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Icon, ROLE_LABEL } from './ui'
import NewPropertyDialog from './NewPropertyDialog'
import CommandPalette from './CommandPalette'

const TITLES = { '': 'Dashboard', properties: 'Properties', procurement: 'Procurement', purchasing: 'Purchasing', schedule: 'Schedule', reports: 'Reports', users: 'Users', 'master-list': 'Master list', approvals: 'Approvals', licences: 'Licences', contacts: 'Contacts' }
const INT_LABEL = { live: 'live', dry_run: 'dry run', heuristic: 'basic reader' }

export default function Layout({ user, onLogout }) {
  const loc = useLocation()
  const nav = useNavigate()
  const [counts, setCounts] = useState({ onboarding: 0, alerts: 0, drafts: 0 })
  const [integ, setInteg] = useState(null)
  const [newOpen, setNewOpen] = useState(false)
  const [cmdk, setCmdk] = useState(false)
  const [menu, setMenu] = useState(false)
  useEffect(() => { setMenu(false) }, [loc.pathname])
  useEffect(() => { document.body.style.overflow = menu ? 'hidden' : ''; return () => { document.body.style.overflow = '' } }, [menu])
  const section = loc.pathname.split('/')[1] || ''

  useEffect(() => {
    Promise.all([api.dashboard(), api.emails({ status: 'draft' })])
      .then(([d, e]) => setCounts({ onboarding: d.kpis.onboarding, alerts: d.attention.length, drafts: e.length })).catch(() => {})
  }, [loc.pathname, loc.key])
  useEffect(() => { api.integrations().then(setInteg).catch(() => {}) }, [])

  useEffect(() => {
    const onKey = (e) => {
      const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) { e.preventDefault(); setCmdk(true) }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const mac = /Mac|iPhone|iPad/.test(navigator.platform)
  const initials = (user?.name || 'U').split(' ').map(s => s[0]).join('').slice(0, 2).toUpperCase()

  return (
    <div className="app">
      {menu && <div className="side-back" onClick={() => setMenu(false)} aria-hidden="true" />}
      <aside className={`side ${menu ? 'open' : ''}`} aria-label="Menu">
        <div className="logo"><div className="logo-mark">PO</div><div><b>Onboarding</b><span>Short-term rentals</span></div>
          <button className="icon-btn side-close" type="button" onClick={() => setMenu(false)} aria-label="Close menu">×</button></div>
        <div className="nav-label">Workspace</div>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end><Icon name="grid" />Dashboard</NavLink>
          <NavLink to="/properties"><Icon name="home" />Properties<span className="badge">{counts.onboarding}</span></NavLink>
          <NavLink to="/procurement"><Icon name="cart" />Procurement</NavLink>
          <NavLink to="/purchasing"><Icon name="truck" />Purchasing</NavLink>
          <NavLink to="/schedule"><Icon name="cal" />Schedule</NavLink>
          <NavLink to="/approvals"><Icon name="mail" />Approvals{counts.drafts > 0 && <span className="badge red">{counts.drafts}</span>}</NavLink>
          <NavLink to="/licences"><Icon name="shield" />Licences</NavLink>
          <NavLink to="/contacts"><Icon name="building" />Contacts</NavLink>
          <NavLink to="/master-list"><Icon name="list" />Master list</NavLink>
        </nav>
        <div className="nav-label">Insights</div>
        <nav className="nav" aria-label="Insights">
          <NavLink to="/reports"><Icon name="chart" />Reports</NavLink>
          {user?.permissions?.includes('manage_users') && <NavLink to="/users"><Icon name="users" />Users</NavLink>}
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
          <div style={{ flex: 1, minWidth: 0 }}><b>{user?.name}</b><span>{ROLE_LABEL[user?.role] || 'Signed in'}</span></div>
          <button className="icon-btn" type="button" onClick={onLogout} aria-label="Sign out" title="Sign out"><Icon name="logout" small /></button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" type="button" onClick={() => setMenu(true)} aria-label="Open menu" aria-expanded={menu}>
            <svg className="i" viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h10" /></svg></button>
          <div className="crumbs"><span>Workspace</span><span>/</span><b>{TITLES[section] || 'Properties'}</b></div>
          <b className="m-title">{TITLES[section] || 'Property'}</b>
          <span className="spacer" />
          <button type="button" className="search" onClick={() => setCmdk(true)} aria-label="Search">
            <Icon name="search" small /><span className="lbl" style={{ flex: 1, textAlign: 'left' }}>Search properties, pages…</span>
            <span className="kbd">{mac ? '⌘' : 'Ctrl'} K</span>
          </button>
          <button className="icon-btn" type="button" aria-label="Alerts" onClick={() => nav('/')}>
            <Icon name="alert" />{counts.alerts > 0 && <span className="dot">{counts.alerts}</span>}
          </button>
          <button className="btn primary new-btn" type="button" onClick={() => setNewOpen(true)} aria-label="New property"><Icon name="plus" small /><span className="lbl">New property</span></button>
        </header>
        <main className="content"><div className="page" key={loc.pathname}><Outlet /></div></main>
      </div>
      <nav className="tabbar" aria-label="Quick">
        <NavLink to="/" end><Icon name="grid" /><span>Home</span></NavLink>
        <NavLink to="/properties"><Icon name="home" /><span>Properties</span></NavLink>
        <button type="button" onClick={() => setCmdk(true)}><Icon name="search" /><span>Search</span></button>
        <NavLink to="/approvals"><Icon name="mail" /><span>Approvals</span>{counts.drafts > 0 && <i className="tb-dot">{counts.drafts}</i>}</NavLink>
        <button type="button" onClick={() => setMenu(true)}><svg className="i" viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h10" /></svg><span>More</span></button>
      </nav>
      <CommandPalette open={cmdk} onClose={() => setCmdk(false)} onNewProperty={() => setNewOpen(true)} />
      {newOpen && <NewPropertyDialog onClose={() => setNewOpen(false)} onCreated={(p, run) => { setNewOpen(false); nav(`/properties/${p.id}`, { state: { run } }) }} />}
    </div>
  )
}
