import { useState } from 'react'
import { api } from '../../api'
import { ErrorBox, Icon, useToast } from '../../components/ui'

const AMENITY_ICON = { Wifi: 'sparkle', Kitchen: 'cart', Washer: 'layers', 'Air conditioning': 'sparkle', TV: 'file', 'Laptop friendly workspace': 'list', 'Self check-in': 'lock' }

export default function ListingTab({ p, listing, setListing, onRunAgent, running }) {
  const toast = useToast()
  const prof = listing.profile
  const [edit, setEdit] = useState(false)
  const [f, setF] = useState(null)
  const [err, setErr] = useState(null)
  const photos = listing.photo_set?.photos || []
  const pro = listing.photo_set && listing.photo_set.kind !== 'inspection'

  const startEdit = () => { setF({ title: prof.title, neighbourhood: prof.neighbourhood, description: prof.description, base_price: prof.base_price ?? '', cleaning_fee: prof.cleaning_fee ?? '', accommodates: prof.effective_accommodates, amenities: prof.amenities }); setEdit(true) }
  const save = async (e) => {
    e.preventDefault(); setErr(null)
    try {
      const body = { ...f, base_price: f.base_price === '' ? null : +f.base_price, cleaning_fee: f.cleaning_fee === '' ? null : +f.cleaning_fee, accommodates: +f.accommodates }
      setListing(await api.updateListing(p.id, body)); setEdit(false); toast('Listing details saved.')
    } catch (e2) { setErr(e2) }
  }
  const toggleAmenity = (a) => setF({ ...f, amenities: f.amenities.includes(a) ? f.amenities.filter(x => x !== a) : [...f.amenities, a] })
  const price = prof.base_price || 150
  const bedrooms = Math.max(1, p.bedrooms)

  return (
    <div className="cols">
      <div style={{ display: 'grid', gap: 22, minWidth: 0 }}>
        {!photos.length && <div className="note info" style={{ margin: 0 }}><Icon name="info" small /><span>No photos yet. Add the photographer's set in the Photos tab.</span></div>}
        {photos.length > 0 && !pro && <div className="note warn" style={{ margin: 0 }}><Icon name="alert" small /><span>Preview uses inspection photos until the professional shoot arrives.</span></div>}
        {edit ? (
          <form className="card card-b" style={{ display: 'grid', gap: 14 }} onSubmit={save}>
            <h2>Edit listing details</h2>
            <ErrorBox error={err} />
            <div className="field"><label htmlFor="l-title">Title</label><input id="l-title" maxLength={120} value={f.title} onChange={e => setF({ ...f, title: e.target.value })} placeholder={prof.effective_title} /></div>
            <div className="form-grid">
              <div className="field"><label htmlFor="l-area">Neighbourhood</label><input id="l-area" value={f.neighbourhood} onChange={e => setF({ ...f, neighbourhood: e.target.value })} /></div>
              <div className="field"><label htmlFor="l-acc">Sleeps</label><input id="l-acc" type="number" min="1" value={f.accommodates} onChange={e => setF({ ...f, accommodates: e.target.value })} /></div>
              <div className="field"><label htmlFor="l-price">Target nightly rate (CAD)</label><input id="l-price" type="number" min="0" value={f.base_price} onChange={e => setF({ ...f, base_price: e.target.value })} /></div>
              <div className="field"><label htmlFor="l-clean">Cleaning fee (CAD)</label><input id="l-clean" type="number" min="0" value={f.cleaning_fee} onChange={e => setF({ ...f, cleaning_fee: e.target.value })} /></div>
            </div>
            <div className="field"><label htmlFor="l-desc">Description</label><textarea id="l-desc" className="input" rows={5} value={f.description} onChange={e => setF({ ...f, description: e.target.value })} placeholder="Angel Host writes the final description in step 10. A starting draft helps." /></div>
            <div><h3 className="fh">Amenities</h3><div className="amen">{listing.amenity_options.map(a =>
              <label key={a} className="fopt" style={{ padding: 0 }}><input type="checkbox" checked={f.amenities.includes(a)} onChange={() => toggleAmenity(a)} /><span>{a}</span></label>)}</div></div>
            <div className="row"><button className="btn primary" type="submit">Save details</button><button className="btn ghost" type="button" onClick={() => setEdit(false)}>Cancel</button></div>
          </form>
        ) : (
          <section className="card card-b lp">
            <div className="row" style={{ alignItems: 'flex-start' }}><div style={{ minWidth: 0 }}>
              <div className="muted sm">Guest-facing title</div><h2 style={{ fontSize: 22, marginTop: 2 }}>{prof.effective_title}</h2></div><span className="spacer" />
              <button className="btn small" type="button" onClick={startEdit}>Edit details</button></div>
            <div className="lp-highlights" style={{ marginTop: 14 }}>
              <span><Icon name="home" small />Entire apartment</span><span><Icon name="bed" small />{p.bedrooms} bedroom{p.bedrooms === 1 ? '' : 's'}</span>
              <span><Icon name="users" small />Sleeps {prof.effective_accommodates}</span><span><Icon name="layers" small />{p.bathrooms} bath{p.bathrooms === 1 ? '' : 's'}</span>
            </div>
            <h2 style={{ marginTop: 10 }}>About this place</h2>
            <p className="lp-text">{prof.description || <span className="muted">No description yet. Angel Host writes it in step 10, or add a starting draft with Edit details.</span>}</p>
            <h2 style={{ marginTop: 22 }}>Most popular facilities</h2>
            <div className="amen">{prof.amenities.slice(0, 12).map(a => <span key={a}><Icon name={AMENITY_ICON[a] || 'check'} />{a}</span>)}</div>
            <h2 style={{ marginTop: 22 }}>Where you'll sleep</h2>
            <div className="sleeps">{[...Array(bedrooms)].map((_, i) => {
              const n = i === 0 ? Math.max(1, p.beds - (bedrooms - 1)) : 1
              return <div className="sleep" key={i}><div className="kpi-ic ic-acc"><Icon name="bed" small /></div><b>{p.bedrooms ? `Bedroom ${i + 1}` : 'Studio'}</b><span>{n} bed{n > 1 ? 's' : ''}</span></div>
            })}</div>
            <h2 style={{ marginTop: 22 }}>House rules</h2>
            <table className="rules"><tbody>
              <tr><td><Icon name="clock" small />Check-in</td><td>From 3:00 pm · self check-in</td></tr>
              <tr><td><Icon name="clock" small />Check-out</td><td>Until 11:00 am</td></tr>
              <tr><td><Icon name="users" small />Guests</td><td>Up to {prof.effective_accommodates}. No parties or events</td></tr>
              <tr><td><Icon name="shield" small />Licence</td><td className="mono">{p.licence?.number || 'Shown here once the City approves the licence'}</td></tr>
            </tbody></table>
          </section>
        )}
      </div>
      <div className="sticky">
        <section className="card book">
          <div className="book-h"><div><b className="book-price">${price}</b> <span className="muted">/ night</span></div><span className="pill p-acc nodot">Target rate</span></div>
          <div className="book-b">
            <div className="sum-row"><span className="muted">${price} × 3 nights</span><span className="num">${price * 3}</span></div>
            {prof.cleaning_fee ? <div className="sum-row"><span className="muted">Cleaning fee</span><span className="num">${prof.cleaning_fee}</span></div> : null}
            <div className="sum-row total"><span>3-night stay</span><span className="num">${price * 3 + (prof.cleaning_fee || 0)}</span></div>
            <div className="muted sm">Angel Host sets final pricing, discounts and markups.</div>
          </div>
        </section>
        <section className="card">
          <div className="card-h"><h2>Guesty</h2><span className="spacer" /><span className={`pill ${prof.guesty_status === 'not_created' ? 'p-info' : 'p-ok'}`}>{prof.guesty_status_label}</span></div>
          <div className="card-b" style={{ display: 'grid', gap: 10 }}>
            <div className="sum-row" style={{ padding: 0 }}><span className="muted">Listing ID</span><span className="mono sm">{listing.guesty_listing_id || '—'}{prof.guesty_dry_run && <span className="dry">Dry run</span>}</span></div>
            <div className="sum-row" style={{ padding: 0 }}><span className="muted">Photos</span><span className="sm">{listing.photo_set?.uploaded_to_guesty_at ? `Uploaded ${new Date(listing.photo_set.uploaded_to_guesty_at).toLocaleDateString('en-CA')}` : 'Not uploaded'}</span></div>
            <button className="btn primary" type="button" disabled={running} onClick={onRunAgent} style={{ justifyContent: 'center' }}>{running ? <span className="spin" /> : <Icon name="bot" small />}Run Listing agent</button>
            <span className="muted sm">Creates the listing (hidden from marketplaces), uploads the photos cover-first and drafts the Angel Host email.</span>
          </div>
        </section>
        <section className="card">
          <div className="card-h"><h2>Go-live readiness</h2><span className="spacer" /><b className="num">{listing.readiness.pct}%</b></div>
          <div className="card-b" style={{ display: 'grid', gap: 9 }}>{listing.readiness.checks.map(c =>
            <div key={c.label} className={`rcheck ${c.ok ? 'ok' : ''}`}><Icon name={c.ok ? 'checkc' : 'clock'} small /><span>{c.label}</span></div>)}</div>
        </section>
        <section className="card">
          <div className="card-h"><h2>Channels</h2><span className="sub">Through Guesty at go-live</span></div>
          <div className="card-b" style={{ display: 'grid', gap: 10 }}>{listing.channels.map(c =>
            <div className="sum-row" style={{ padding: 0 }} key={c.name}><span>{c.name}</span><span className={`pill ${c.live ? 'p-ok' : 'p-info'}`}>{c.live ? 'Live' : 'Not live'}</span></div>)}</div>
        </section>
      </div>
    </div>
  )
}
