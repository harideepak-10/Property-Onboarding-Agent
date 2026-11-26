import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { ErrorBox, Icon, Loading, Pill, STATE, PhotoPlaceholder } from '../components/ui'

const STATES = [['blocked', 'Blocked'], ['waiting', 'Waiting'], ['on_track', 'On track'], ['live', 'Live']]
const ORDER = { blocked: 0, waiting: 1, on_track: 2, live: 3 }

export default function Properties() {
  const [params] = useSearchParams()
  const q = params.get('q') || ''
  const [list, setList] = useState(null)
  const [err, setErr] = useState(null)
  const [status, setStatus] = useState(new Set())
  const [beds, setBeds] = useState('any')
  const [sort, setSort] = useState('attention')
  const nav = useNavigate()

  useEffect(() => { setList(null); api.properties(q).then(setList).catch(setErr) }, [q])

  const shown = useMemo(() => {
    if (!list) return []
    let l = list.filter(p => (!status.size || status.has(p.state)) && (beds === 'any' || (beds === '3' ? p.bedrooms >= 3 : p.bedrooms === +beds)))
    if (sort === 'attention') l = [...l].sort((a, b) => ORDER[a.state] - ORDER[b.state])
    if (sort === 'progress') l = [...l].sort((a, b) => b.progress - a.progress)
    if (sort === 'nickname') l = [...l].sort((a, b) => a.nickname.localeCompare(b.nickname))
    return l
  }, [list, status, beds, sort])

  if (err) return <ErrorBox error={err} />
  if (!list) return <Loading />
  const counts = list.reduce((a, p) => ({ ...a, [p.state]: (a[p.state] || 0) + 1 }), {})
  const toggle = (s) => { const n = new Set(status); n.has(s) ? n.delete(s) : n.add(s); setStatus(n) }

  return (
    <>
      <div className="page-head"><div><h1>Properties</h1><p>{q ? <>Results for “{q}” · <Link to="/properties">clear search</Link></> : 'Every unit in onboarding, with its next step.'}</p></div></div>
      <div className="res-layout">
        <aside className="card filters">
          <div className="card-h"><h2>Filter by</h2><span className="spacer" />{(status.size > 0 || beds !== 'any') && <button className="btn ghost small" type="button" onClick={() => { setStatus(new Set()); setBeds('any') }}>Clear</button>}</div>
          <div className="card-b" style={{ display: 'grid', gap: 18 }}>
            <div><h3 className="fh">Status</h3>
              {STATES.map(([v, l]) => <label className="fopt" key={v}><input type="checkbox" checked={status.has(v)} onChange={() => toggle(v)} /><span>{l}</span><span className="muted num">{counts[v] || 0}</span></label>)}</div>
            <div><h3 className="fh">Size</h3>
              {[['any', 'Any'], ['1', '1 bedroom'], ['2', '2 bedrooms'], ['3', '3+ bedrooms']].map(([v, l]) =>
                <label className="fopt" key={v}><input type="radio" name="beds" checked={beds === v} onChange={() => setBeds(v)} /><span>{l}</span></label>)}</div>
          </div>
        </aside>
        <div style={{ display: 'grid', gap: 16, minWidth: 0, alignContent: 'start' }}>
          <div className="row"><b>{shown.length} propert{shown.length === 1 ? 'y' : 'ies'}</b><span className="spacer" />
            <label className="row sm" style={{ gap: 8 }}><span className="muted">Sort by</span>
              <select className="input" style={{ width: 'auto', padding: '7px 12px' }} value={sort} onChange={e => setSort(e.target.value)}>
                <option value="attention">Needs attention first</option><option value="progress">Most progress</option><option value="nickname">Nickname</option></select></label></div>
          {shown.map(p => (
            <article className="res card" key={p.id}>
              <button className="res-photo" type="button" onClick={() => nav(`/properties/${p.id}`)} aria-label={`Open ${p.nickname}`}>
                {p.cover_url ? <img src={p.cover_url} alt={p.listing_title || p.address} />
                  : <PhotoPlaceholder p={p} />}
                <span className="res-badge"><Pill map={STATE} value={p.state} /></span>
              </button>
              <div className="res-body">
                <div className="res-top"><div style={{ minWidth: 0 }}><div className="mono muted sm">{p.nickname}</div>
                  <h3 className="res-title"><Link to={`/properties/${p.id}`}>{p.listing_title || p.address}</Link></h3>
                  <div className="res-loc"><Icon name="pin" small /><span>{p.listing_title ? `${p.address}, ` : ''}{p.city}</span></div></div></div>
                <div className="res-chips"><span className="chip"><Icon name="bed" small />{p.bedrooms} bedroom{p.bedrooms === 1 ? '' : 's'}</span><span className="chip">{p.bathrooms} bath{p.bathrooms === 1 ? '' : 's'}</span><span className="chip">{p.beds} bed{p.beds === 1 ? '' : 's'}</span><span className="chip">{p.owner_name} ({p.owner_type})</span></div>
                <div className="res-step">{p.state === 'live' ? <span className="ok-text"><Icon name="checkc" small /> Live on all channels</span>
                  : p.current_step && <><b>Step {p.current_step.number}: {p.current_step.name}</b> <span className="muted">· {p.current_step.owner}</span></>}
                  <div className="muted sm res-need">{p.needs}</div></div>
              </div>
              <div className="res-side">
                <div className="res-price"><span className="muted sm">Licence</span><b style={{ fontSize: 17 }}>{p.licence?.status_label || '—'}</b><span className="muted sm">{p.licence?.expires_on ? `Expires ${p.licence.expires_on}` : ''}</span></div>
                <div style={{ width: '100%' }}><div className="row sm" style={{ justifyContent: 'space-between' }}><span className="muted">Onboarding</span><b className="num">{p.progress}%</b></div>
                  <div className={`bar ${p.progress === 100 ? 'done' : ''}`} style={{ marginTop: 6 }}><i style={{ width: `${p.progress}%` }} /></div></div>
                <button className="btn primary" type="button" onClick={() => nav(`/properties/${p.id}`)} style={{ width: '100%', justifyContent: 'center' }}>Open property</button>
              </div>
            </article>
          ))}
          {!shown.length && <div className="card empty">No properties match these filters.</div>}
        </div>
      </div>
    </>
  )
}
