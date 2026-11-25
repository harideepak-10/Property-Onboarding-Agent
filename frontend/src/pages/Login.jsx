import { useState } from 'react'
import { api, setToken } from '../api'
import { ErrorBox } from '../components/ui'

export default function Login({ onLogin }) {
  const [username, setU] = useState('')
  const [password, setP] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      const r = await api.login(username, password)
      setToken(r.token)
      onLogin(r.user)
    } catch (e2) { setErr(e2) } finally { setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="logo" style={{ padding: 0 }}><div className="logo-mark">PO</div><div><b>Onboarding</b><span className="muted sm">STR operations</span></div></div>
        <div><h1 style={{ fontSize: 24 }}>Sign in</h1><p className="muted" style={{ margin: '4px 0 0' }}>From signed agreement to live listing.</p></div>
        <ErrorBox error={err} />
        <div className="field"><label htmlFor="u">Username</label><input id="u" value={username} onChange={e => setU(e.target.value)} autoComplete="username" required /></div>
        <div className="field"><label htmlFor="p">Password</label><input id="p" type="password" value={password} onChange={e => setP(e.target.value)} autoComplete="current-password" required /></div>
        <button className="btn primary" type="submit" disabled={busy} style={{ justifyContent: 'center', padding: 12 }}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}
