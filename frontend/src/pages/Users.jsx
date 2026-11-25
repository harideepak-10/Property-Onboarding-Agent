import { useEffect, useState } from 'react'
import { api, fmtDate } from '../api'
import { ErrorBox, Icon, Loading, ROLE_LABEL, useToast } from '../components/ui'

const ROLE_HELP = {
  admin: 'Everything, including users',
  manager: 'Approves orders, sends emails, approves go-live, edits the master list',
  coordinator: 'Day-to-day work; can’t approve spending, send email or go live',
  viewer: 'Read-only',
}

export default function Users() {
  const toast = useToast()
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const blank = { username: '', first_name: '', last_name: '', email: '', password: '', role: 'coordinator' }
  const [f, setF] = useState(blank)
  const load = () => api.users().then(setD).catch(setErr)
  useEffect(() => { load() }, [])
  if (!d) return err ? <ErrorBox error={err} /> : <Loading />
  const set = k => e => setF({ ...f, [k]: e.target.value })
  const upd = async (u, data, msg) => { try { await api.updateUser(u.id, data); toast(msg); load() } catch (e) { setErr(e) } }
  const add = async (e) => {
    e.preventDefault(); setErr(null)
    try { await api.addUser(f); setF(blank); toast('User added. Share the temporary password with them directly.'); load() } catch (e2) { setErr(e2) }
  }
  return (
    <>
      <div className="page-head"><div><h1>Users</h1><p>Who can sign in, and what each role can do.</p></div></div>
      <ErrorBox error={err} />
      <div className="cols">
        <section className="card"><div className="table-wrap"><table>
          <thead><tr><th>User</th><th>Role</th><th>Last sign-in</th><th /></tr></thead>
          <tbody>{d.users.map(u => <tr key={u.id} className={u.is_active ? '' : 'zero'}>
            <td><b className="sm">{u.name || u.username}</b><div className="muted sm mono">{u.username}{u.email ? ` · ${u.email}` : ''}</div></td>
            <td><select className="input" value={u.role} onChange={e => upd(u, { role: e.target.value }, 'Role updated.')} aria-label={`Role for ${u.username}`}>
              {d.roles.map(r => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select></td>
            <td className="sm">{u.last_login ? fmtDate(u.last_login.slice(0, 10)) : 'Never'}</td>
            <td><button className="btn ghost small" onClick={() => upd(u, { is_active: !u.is_active }, u.is_active ? 'Deactivated.' : 'Reactivated.')}>{u.is_active ? 'Deactivate' : 'Reactivate'}</button></td>
          </tr>)}</tbody></table></div></section>
        <div className="sticky">
          <form className="card" onSubmit={add}>
            <div className="card-h"><h2>Add a user</h2></div>
            <div className="card-b form-grid">
              <div className="field"><label htmlFor="nu">Username</label><input id="nu" required value={f.username} onChange={set('username')} autoComplete="off" /></div>
              <div className="field"><label htmlFor="nr">Role</label><select id="nr" value={f.role} onChange={set('role')}>{d.roles.map(r => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select></div>
              <div className="field"><label htmlFor="nf">First name</label><input id="nf" value={f.first_name} onChange={set('first_name')} /></div>
              <div className="field"><label htmlFor="nl">Last name</label><input id="nl" value={f.last_name} onChange={set('last_name')} /></div>
              <div className="field" style={{ gridColumn: '1/-1' }}><label htmlFor="ne">Email</label><input id="ne" type="email" value={f.email} onChange={set('email')} /></div>
              <div className="field" style={{ gridColumn: '1/-1' }}><label htmlFor="np">Temporary password</label><input id="np" type="password" minLength={8} required value={f.password} onChange={set('password')} autoComplete="new-password" /></div>
              <button className="btn primary" type="submit"><Icon name="plus" small />Add user</button>
            </div>
          </form>
          <section className="card"><div className="card-h"><h2>Roles</h2></div>
            <div className="card-b" style={{ display: 'grid', gap: 8 }}>{Object.entries(ROLE_HELP).map(([r, h]) => <div key={r}><b className="sm">{ROLE_LABEL[r]}</b><div className="muted sm">{h}</div></div>)}</div></section>
        </div>
      </div>
    </>
  )
}
