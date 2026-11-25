import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorBox, Icon, Loading } from '../components/ui'

export default function Decisions() {
  const [list, setList] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { api.decisions().then(setList).catch(setErr) }, [])
  if (!list) return err ? <ErrorBox error={err} /> : <Loading />
  const areas = [...new Set(list.map(d => d.area))]
  return (
    <>
      <div className="page-head"><div><h1>Decisions</h1><p>Open questions we answered with a sensible default so the work isn't blocked. Each can be changed; tell us if any should be different.</p></div></div>
      {areas.map(a => <section className="card" key={a}>
        <div className="card-h"><h2>{a}</h2></div>
        <div className="card-b" style={{ display: 'grid', gap: 18 }}>{list.filter(d => d.area === a).map(d => <div key={d.question} style={{ display: 'grid', gap: 4 }}>
          <b>{d.question}</b>
          <div className="row" style={{ gap: 8, alignItems: 'flex-start', flexWrap: 'nowrap' }}><span style={{ color: 'var(--ok)' }}><Icon name="checkc" small /></span><span>{d.decision}</span></div>
          <div className="muted sm">Why: {d.why}</div>
          {d.change !== '—' && <div className="muted sm">To change: {d.change}</div>}
        </div>)}</div>
      </section>)}
    </>
  )
}
