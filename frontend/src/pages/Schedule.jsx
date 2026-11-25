import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/ui'
import { BookVisitForm, KINDS, VisitCard } from '../components/Visits'

export default function Schedule() {
  const [visits, setVisits] = useState(null)
  const [props, setProps] = useState([])
  const [kind, setKind] = useState('')
  const [upcoming, setUpcoming] = useState(true)
  const [err, setErr] = useState(null)
  const load = () => api.visits({ ...(kind ? { kind } : {}), ...(upcoming ? { upcoming: 1 } : {}) }).then(setVisits).catch(setErr)
  useEffect(() => { api.properties().then(setProps).catch(() => {}) }, [])
  useEffect(() => { load() }, [kind, upcoming])
  if (!visits) return err ? <ErrorBox error={err} /> : <Loading />
  const byDate = {}
  visits.forEach(v => { (byDate[v.date] ||= []).push(v) })
  return (
    <>
      <div className="page-head"><div><h1>Schedule</h1><p>Inspections, setup days, photo shoots, deliveries and repairs across all properties.</p></div></div>
      <div className="cols">
        <section className="card">
          <div className="card-b row" style={{ gap: 8, borderBottom: '1px solid var(--line-2)' }}>
            <select className="input" value={kind} onChange={e => setKind(e.target.value)} aria-label="Kind" style={{ maxWidth: 180 }}><option value="">Everything</option>{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            <label className="row sm" style={{ gap: 6 }}><input type="checkbox" checked={upcoming} onChange={e => setUpcoming(e.target.checked)} />Upcoming only</label>
          </div>
          {Object.entries(byDate).map(([date, vs]) => <div key={date}>
            <div className="card-b" style={{ paddingBottom: 0 }}><b className="sm">{new Date(date + 'T12:00').toLocaleDateString('en-CA', { weekday: 'long', month: 'long', day: 'numeric' })}</b></div>
            <div className="store-carts">{vs.map(v => <VisitCard key={v.id} v={v} showProperty onChange={load} />)}</div>
          </div>)}
          {!visits.length && <div className="card-b muted">Nothing scheduled.</div>}
        </section>
        <div className="sticky"><section className="card"><div className="card-h"><h2>Book a visit</h2></div>
          <BookVisitForm properties={props} onBooked={load} /></section></div>
      </div>
    </>
  )
}
