import { useEffect, useState } from 'react'
import { api } from '../../api'
import { ErrorBox, Loading } from '../../components/ui'
import { BookVisitForm, VisitCard } from '../../components/Visits'

export default function ScheduleTab({ p, onSaved }) {
  const [visits, setVisits] = useState(null)
  const [err, setErr] = useState(null)
  const load = () => api.visits({ property: p.id }).then(setVisits).catch(setErr)
  useEffect(() => { load() }, [p.id])
  if (!visits) return err ? <ErrorBox error={err} /> : <Loading />
  const next = p.steps.find(s => ['ready', 'in_progress', 'waiting'].includes(s.status) && [4, 7, 8].includes(s.number))
  const suggested = { 4: 'inspection', 7: 'setup_day', 8: 'photo_shoot' }[next?.number] || 'inspection'
  const changed = (v) => { setVisits(visits.map(x => x.id === v.id ? v : x)); onSaved?.() }
  return (
    <div className="cols">
      <section className="card">
        <div className="card-h"><h2>Visits</h2><span className="sub">Inspection, setup day, photo shoot, deliveries, repairs</span></div>
        {visits.length ? <div className="store-carts">{visits.map(v => <VisitCard key={v.id} v={v} onChange={changed} />)}</div>
          : <div className="card-b muted">Nothing booked yet.</div>}
      </section>
      <div className="sticky">
        <section className="card">
          <div className="card-h"><h2>Book a visit</h2></div>
          <BookVisitForm key={suggested} propertyId={p.id} defaultKind={suggested} onBooked={() => { load(); onSaved?.() }} />
        </section>
        <section className="card"><div className="card-b muted sm" style={{ display: 'grid', gap: 6 }}>
          <span>Booking an inspection ticks “Inspection booked” (step 4); a photo shoot ticks “Shoot booked” (step 8).</span>
          <span>Setup-day checklist items tick step 7. Adding the photographer's Drive link ticks “Photos received”.</span>
          <span>A visit with a cost is added to the property's costs.</span></div></section>
      </div>
    </div>
  )
}
