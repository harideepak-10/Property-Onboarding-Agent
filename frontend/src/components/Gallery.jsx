import { useEffect, useRef, useState } from 'react'
import { Icon } from './ui'

/** Booking-style photo grid: one large cover + four small, "+N photos" on the last tile. */
export function Mosaic({ photos, onOpen }) {
  if (!photos?.length) return null
  const small = photos.slice(1, 5)
  return (
    <div className="mosaic" style={photos.length === 1 ? { gridTemplateColumns: '1fr' } : undefined}>
      <button className="m-main" type="button" onClick={() => onOpen(0)}>
        <img src={photos[0].url} alt={photos[0].caption || photos[0].room || 'Cover photo'} />
        <span className="m-cover"><Icon name="sparkle" small />Cover photo</span>
      </button>
      {small.map((p, i) => (
        <button className="m-s" type="button" key={p.id} onClick={() => onOpen(i + 1)}>
          <img src={p.url} alt={p.caption || p.room || `Photo ${i + 2}`} loading="lazy" />
          {i === small.length - 1 && photos.length > 5 && <span className="m-more">+{photos.length - 5} photos</span>}
        </button>
      ))}
    </div>
  )
}

export function Lightbox({ photos, index, onClose }) {
  const ref = useRef()
  const [i, setI] = useState(index)
  useEffect(() => { setI(index); if (index !== null) ref.current?.showModal() }, [index])
  if (index === null || !photos?.length) return null
  const p = photos[i] || photos[0]
  const go = (d) => setI((i + d + photos.length) % photos.length)
  return (
    <dialog id="lightDlg" ref={ref} onClose={onClose} aria-label="Photo viewer"
      onKeyDown={e => { if (e.key === 'ArrowLeft') go(-1); if (e.key === 'ArrowRight') go(1) }}
      onClick={e => { if (e.target === ref.current) ref.current.close() }}>
      <div className="light-b">
        <img src={p.url} alt={p.caption || p.room || 'Photo'} />
        <button className="light-nav" type="button" style={{ left: 14 }} onClick={() => go(-1)} aria-label="Previous photo">‹</button>
        <button className="light-nav" type="button" style={{ right: 14 }} onClick={() => go(1)} aria-label="Next photo">›</button>
      </div>
      <div className="light-f"><span className="sm">{p.caption || p.room || 'Photo'} · {i + 1} of {photos.length}</span><span className="spacer" />
        <button className="btn small" type="button" onClick={() => ref.current.close()}>Close</button></div>
    </dialog>
  )
}
