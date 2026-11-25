import { useRef, useState } from 'react'
import { api } from '../../api'
import { ErrorBox, Icon, useToast } from '../../components/ui'

const KINDS = [['shoot', 'Professional shoot'], ['reshoot', 'Re-shoot (replaces the current set)'], ['inspection', 'Inspection photos']]

export default function PhotosTab({ p, listing, setListing, onOpen }) {
  const toast = useToast()
  const fileRef = useRef()
  const [kind, setKind] = useState(listing.photo_set ? 'shoot' : 'shoot')
  const [drive, setDrive] = useState('')
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const [err, setErr] = useState(null)
  const ps = listing.photo_set
  const photos = ps?.photos || []

  const run = async (fn, msg) => {
    setBusy(true); setErr(null)
    try { setListing(await fn()); if (msg) toast(msg) } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const upload = (files) => files?.length && run(() => api.uploadPhotos(p.id, files, { kind, newSet: kind === 'reshoot' || (ps && ps.kind !== kind) }),
    `${files.length} photo${files.length > 1 ? 's' : ''} added.`)
  const move = (idx, d) => {
    const ids = photos.map(x => x.id); const j = idx + d
    if (j < 1 || j >= ids.length || idx < 1) return
    ;[ids[idx], ids[j]] = [ids[j], ids[idx]]
    run(() => api.reorderPhotos(p.id, ids.slice(1)))
  }

  return (
    <div style={{ display: 'grid', gap: 22 }}>
      <section className="card">
        <div className="card-h"><h2>Add photos</h2><span className="sub">The photographer shares a Google Drive link. Import it, or upload the files.</span></div>
        <div className="card-b" style={{ display: 'grid', gap: 14 }}>
          <ErrorBox error={err} />
          <div className="field" style={{ maxWidth: 360 }}><label htmlFor="ph-kind">This set is</label>
            <select id="ph-kind" value={kind} onChange={e => setKind(e.target.value)}>{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
          <div className={`upload-zone ${drag ? 'drag' : ''}`} role="button" tabIndex={0}
            onClick={() => fileRef.current.click()} onKeyDown={e => e.key === 'Enter' && fileRef.current.click()}
            onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files) }}>
            {busy ? <><span className="spin" /><b>Uploading…</b></> : <><div className="kpi-ic ic-acc"><Icon name="upload" /></div><b>Drop photos here or click to choose</b>
              <span className="muted sm">JPG, PNG or WebP. Rooms are guessed from file names (e.g. kitchen-1.jpg).</span></>}
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={e => { upload(e.target.files); e.target.value = '' }} />
          </div>
          <form className="inline-form" style={{ marginTop: 0 }} onSubmit={e => { e.preventDefault(); run(() => api.importDrive(p.id, drive, kind), 'Imported from Google Drive.') }}>
            <input className="input" type="url" placeholder="https://drive.google.com/drive/folders/…" value={drive} onChange={e => setDrive(e.target.value)} aria-label="Google Drive folder link" />
            <button className="btn" type="submit" disabled={busy || !drive}><Icon name="folder" small />Import from Drive</button>
          </form>
        </div>
      </section>

      <section className="card">
        <div className="card-h"><h2>{ps ? ps.kind_label : 'Photos'}</h2>
          {ps && <span className="sub">{photos.length} photos · {ps.source_label.toLowerCase()} · {new Date(ps.received_at).toLocaleDateString('en-CA')}</span>}
          <span className="spacer" />{ps && <span className={`pill ${ps.uploaded_to_guesty_at ? 'p-ok' : 'p-info'}`}>{ps.uploaded_to_guesty_at ? 'Uploaded to Guesty' : 'Not in Guesty yet'}</span>}</div>
        {!photos.length ? <div className="empty">No photos yet.</div> : (
          <div className="pgrid">{photos.map((x, i) => (
            <figure className={`pcell ${x.is_cover ? 'is-cover' : ''}`} key={x.id}>
              <button type="button" className="pbtn" onClick={() => onOpen(i)}><img src={x.url} alt={x.caption || x.room || x.original_name} loading="lazy" /></button>
              <figcaption style={{ display: 'grid', gap: 8 }}>
                <div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                  <select className="input" style={{ padding: '5px 8px', fontSize: 12.5 }} value={x.room} aria-label="Room"
                    onChange={e => run(() => api.updatePhoto(x.id, { room: e.target.value, caption: x.caption || e.target.value }))}>
                    <option value="">Room…</option>{listing.rooms.map(r => <option key={r}>{r}</option>)}</select>
                  {x.is_cover ? <span className="pill p-acc nodot">Cover</span> : <button className="btn small" type="button" disabled={busy} onClick={() => run(() => api.updatePhoto(x.id, { is_cover: true }), 'Cover photo updated.')}>Set cover</button>}
                </div>
                <input className="input" style={{ padding: '6px 10px', fontSize: 12.5 }} defaultValue={x.caption} placeholder="Caption" aria-label="Caption"
                  onBlur={e => e.target.value !== x.caption && run(() => api.updatePhoto(x.id, { caption: e.target.value }))} />
                <div className="row" style={{ gap: 4 }}>
                  <button className="btn ghost small" type="button" disabled={busy || i < 2} onClick={() => move(i, -1)} aria-label="Move earlier">←</button>
                  <button className="btn ghost small" type="button" disabled={busy || i < 1 || i === photos.length - 1} onClick={() => move(i, 1)} aria-label="Move later">→</button>
                  <span className="spacer" />
                  <button className="btn ghost small" type="button" disabled={busy} onClick={() => run(() => api.deletePhoto(x.id), 'Photo removed.')}>Delete</button>
                </div>
              </figcaption>
            </figure>))}</div>
        )}
        <div className="card-b" style={{ paddingTop: 0 }}><div className="note info"><Icon name="info" small /><span>The cover goes first and the rest follow this order when the Listing agent uploads to Guesty. Angel Host sets the final photo tour.</span></div></div>
      </section>

      {listing.previous_sets.length > 0 && <section className="card"><div className="card-h"><h2>Earlier photo sets</h2></div>
        <div className="card-b" style={{ display: 'grid', gap: 8 }}>{listing.previous_sets.map(s =>
          <div className="sum-row" style={{ padding: 0 }} key={s.id}><span className="sm">{s.kind_label} · {s.photos.length} photos</span><span className="muted sm">{new Date(s.received_at).toLocaleDateString('en-CA')}</span></div>)}</div></section>}
    </div>
  )
}
