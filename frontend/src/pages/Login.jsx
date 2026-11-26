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
    <div className="login2">
      <div className="lf">
        <form onSubmit={submit}>
          <div className="logo" style={{ padding: 0 }}><div className="logo-mark">PO</div><div><b>Onboarding</b><span className="muted sm">Short-term rentals</span></div></div>
          <div><h1>Welcome back</h1><p className="muted" style={{ margin: '6px 0 0' }}>Sign in to follow every home from signed agreement to live listing.</p></div>
          <ErrorBox error={err} />
          <div className="field"><label htmlFor="u">Username</label><input id="u" value={username} onChange={e => setU(e.target.value)} autoComplete="username" required /></div>
          <div className="field"><label htmlFor="p">Password</label><input id="p" type="password" value={password} onChange={e => setP(e.target.value)} autoComplete="current-password" required /></div>
          <button className="btn primary" type="submit" disabled={busy} style={{ justifyContent: 'center', padding: 12 }}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
      </div>
      <div className="art" aria-hidden="true">
        <div className="sm" style={{ opacity: .7, letterSpacing: '.12em', textTransform: 'uppercase' }}>Property onboarding</div>
        <h2>From signed agreement to <em>live listing</em>, in one calm place.</h2>
        <div className="steps">
          <div><i>✓</i>Agreement read and property created<span>Intake agent</span></div>
          <div><i>✓</i>Licence packet and unit email ready<span>Compliance agent</span></div>
          <div><i>✓</i>Kit priced, checked and carted<span>Procurement agent</span></div>
          <div><i>✓</i>Listing built in Guesty with photos<span>Listing agent</span></div>
        </div>
      </div>
    </div>
  )
}
