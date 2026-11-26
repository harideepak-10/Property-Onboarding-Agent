// Local dev: '/api' (proxied by Vite). Deployed: the API's full address, e.g. https://…onrender.com/api
const BASE = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

export function getToken() {
  try { return localStorage.getItem('token') } catch { return null }
}
export function setToken(t) {
  cache.clear()
  try { t ? localStorage.setItem('token', t) : localStorage.removeItem('token') } catch { /* storage blocked */ }
}

export class ApiError extends Error {}

// Page data is kept for a short time so moving between sections is instant.
// Any change (POST/PUT/PATCH/DELETE) clears it, so nothing shown is out of date after an edit.
const CACHE_MS = 60_000
const cache = new Map()      // path -> { at, data }
const inflight = new Map()   // path -> promise (two components asking at once share one request)
export function clearCache() { cache.clear() }

function request(method, path, body, opts = {}) {
  if (method !== 'GET' || opts.raw) {
    if (method !== 'GET') cache.clear()
    return send(method, path, body, opts)
  }
  const hit = cache.get(path)
  if (hit && Date.now() - hit.at < CACHE_MS) return Promise.resolve(structuredClone(hit.data))
  if (!inflight.has(path)) {
    inflight.set(path, send('GET', path).then(data => { cache.set(path, { at: Date.now(), data }); return data })
      .finally(() => inflight.delete(path)))
  }
  return inflight.get(path).then(d => structuredClone(d))
}

async function send(method, path, body, { raw = false } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Token ${token}`
  let payload
  if (body instanceof FormData) payload = body
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  const res = await fetch(BASE + path, { method, headers, body: payload })
  if (res.status === 401) {
    setToken(null)
    window.dispatchEvent(new Event('auth:logout'))
    throw new ApiError('Your session ended. Sign in again.')
  }
  if (raw) return res
  const data = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) {
    let msg = data?.detail
    if (!msg && data && typeof data === 'object') {
      msg = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : v}`).join(' · ')
    }
    if (data?.errors?.length) msg = data.errors.join('\n')
    throw new ApiError(msg || `Request failed (${res.status})`)
  }
  return data
}

export const api = {
  login: (username, password) => request('POST', '/auth/login/', { username, password }),
  me: () => request('GET', '/auth/me/'),
  dashboard: () => request('GET', '/dashboard/'),
  properties: (q = '') => request('GET', '/properties/' + (q ? `?q=${encodeURIComponent(q)}` : '')),
  property: (id) => request('GET', `/properties/${id}/`),
  createProperty: (data) => request('POST', '/properties/', data),
  updateLicence: (id, data) => request('PATCH', `/properties/${id}/licence/`, data),
  setTask: (id, data) => request('POST', `/tasks/${id}/set/`, data),
  blockStep: (id, reason) => request('POST', `/steps/${id}/block/`, { reason }),
  waitStep: (id, note) => request('POST', `/steps/${id}/wait/`, { note }),
  stores: () => request('GET', '/stores/'),
  masterItems: () => request('GET', '/master-items/'),
  saveMasterItem: (item) => item.id
    ? request('PATCH', `/master-items/${item.id}/`, item)
    : request('POST', '/master-items/', item),
  importMasterList: (file) => { const f = new FormData(); f.append('file', file); return request('POST', '/master-items/import/', f) },
  orders: (propertyId) => request('GET', `/orders/?property=${propertyId}`),
  order: (id) => request('GET', `/orders/${id}/`),
  createOrder: (data) => request('POST', '/orders/', data),
  checkOrder: (id) => request('POST', `/orders/${id}/check/`),
  buildCarts: (id) => request('POST', `/orders/${id}/build-carts/`),
  approveOrder: (id) => request('POST', `/orders/${id}/approve/`),
  resolveLine: (id, resolution) => request('POST', `/order-lines/${id}/resolve/`, { resolution }),
  deleteLine: (id) => request('DELETE', `/order-lines/${id}/`),
  addManualLine: (id, data) => request('POST', `/orders/${id}/manual-lines/`, data),
  addDecor: (id, data) => request('POST', `/orders/${id}/decor/`, data),
  deleteDecor: (id) => request('DELETE', `/decor/${id}/`),
  integrations: () => request('GET', '/integrations/'),
  uploadAgreement: (file) => { const f = new FormData(); f.append('file', file); return request('POST', '/agreements/', f) },
  createFromAgreement: (id, fields) => request('POST', `/agreements/${id}/create-property/`, { fields }),
  runAgent: (propertyId, agent) => request('POST', `/properties/${propertyId}/agents/${agent}/`),
  agentRuns: (propertyId) => request('GET', `/agent-runs/?property=${propertyId}`),
  runSweeps: () => request('POST', '/agents/sweeps/'),
  emails: (params = {}) => request('GET', '/emails/?' + new URLSearchParams(params)),
  updateEmail: (id, data) => request('PATCH', `/emails/${id}/`, data),
  sendEmail: (id) => request('POST', `/emails/${id}/send/`),
  discardEmail: (id) => request('POST', `/emails/${id}/discard/`),
  buildings: () => request('GET', '/buildings/'),
  saveBuilding: (b) => b.id ? request('PATCH', `/buildings/${b.id}/`, b) : request('POST', '/buildings/', b),
  licences: () => request('GET', '/licences/'),
  complianceItems: (propertyId) => request('GET', `/compliance-items/?property=${propertyId}`),
  updateComplianceItem: (id, data) => request('PATCH', `/compliance-items/${id}/`, data),
  listing: (id) => request('GET', `/properties/${id}/listing/`),
  updateListing: (id, data) => request('PATCH', `/properties/${id}/listing/`, data),
  uploadPhotos: (id, files, { kind = 'shoot', newSet = false } = {}) => {
    const f = new FormData(); [...files].forEach(x => f.append('files', x)); f.append('kind', kind); f.append('new_set', newSet ? '1' : '0')
    return request('POST', `/properties/${id}/photos/`, f)
  },
  importDrive: (id, url, kind) => request('POST', `/properties/${id}/photos/import-drive/`, { url, kind }),
  updatePhoto: (id, data) => request('PATCH', `/photos/${id}/`, data),
  deletePhoto: (id) => request('DELETE', `/photos/${id}/`),
  reorderPhotos: (id, ids) => request('POST', `/properties/${id}/photos/reorder/`, { ids }),
  guestGuide: (id) => request('GET', `/properties/${id}/guest-guide/`),
  updateGuestGuide: (id, data) => request('PATCH', `/properties/${id}/guest-guide/`, data),
  revealGuide: (id) => request('POST', `/properties/${id}/guest-guide/reveal/`),
  goLive: (id) => request('GET', `/properties/${id}/go-live/`),
  approveGoLive: (id) => request('POST', `/properties/${id}/go-live/approve/`),
  confirmChannel: (id, ch) => request('POST', `/properties/${id}/go-live/channels/${ch}/`),
  unlist: (id, reason) => request('POST', `/properties/${id}/go-live/unlist/`, { reason }),
  // unit details (step 2)
  unit: (id) => request('GET', `/properties/${id}/unit/`),
  saveUnit: (id, data) => request('PUT', `/properties/${id}/unit/`, data),
  // purchasing tracker
  trackLine: (id, data) => request('PATCH', `/order-lines/${id}/track/`, data),
  uploadReceipt: (id, file) => { const f = new FormData(); f.append('receipt', file); return request('PATCH', `/order-lines/${id}/track/`, f) },
  markStore: (orderId, data) => request('POST', `/orders/${orderId}/mark-store/`, data),
  purchasing: (params = {}) => request('GET', '/purchasing/?' + new URLSearchParams(params)),
  purchasingCsv: async (params = {}) => (await request('GET', '/purchasing/?' + new URLSearchParams({ ...params, export: 'csv' }), undefined, { raw: true })).text(),
  // visits, inspections, expenses
  visits: (params = {}) => request('GET', '/visits/?' + new URLSearchParams(params)),
  bookVisit: (data) => request('POST', '/visits/', data),
  updateVisit: (id, data) => request('PATCH', `/visits/${id}/`, data),
  inspections: (propertyId) => request('GET', `/inspections/?property=${propertyId}`),
  startInspection: (data) => request('POST', '/inspections/', data),
  saveInspection: (id, data) => request('PATCH', `/inspections/${id}/`, data),
  completeInspection: (id) => request('POST', `/inspections/${id}/complete/`),
  inspectionPhoto: (id, itemId, file) => { const f = new FormData(); f.append('photo', file); return request('POST', `/inspections/${id}/items/${itemId}/photo/`, f) },
  inspectionReport: async (id) => (await request('GET', `/inspections/${id}/report/`, undefined, { raw: true })).text(),
  expenses: (propertyId) => request('GET', `/expenses/?property=${propertyId}`),
  addExpense: (data) => request('POST', '/expenses/', data),
  deleteExpense: (id) => request('DELETE', `/expenses/${id}/`),
  costs: (id) => request('GET', `/properties/${id}/costs/`),
  // reports, users, digest
  reports: () => request('GET', '/reports/'),
  report: (key, params = {}) => request('GET', `/reports/${key}/?` + new URLSearchParams(params)),
  reportFile: async (key, params, kind) => {
    const res = await request('GET', `/reports/${key}/?` + new URLSearchParams({ ...params, export: kind }), undefined, { raw: true })
    if (!res.ok) throw new ApiError((await res.json().catch(() => null))?.detail || 'Could not create the file.')
    const name = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || `${key}.${kind}`
    const a = document.createElement('a')
    a.href = URL.createObjectURL(await res.blob()); a.download = name; a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  },
  digest: () => request('GET', '/digest/'),
  sendDigest: () => request('POST', '/digest/'),
  users: () => request('GET', '/auth/users/'),
  addUser: (data) => request('POST', '/auth/users/', data),
  updateUser: (id, data) => request('PATCH', `/auth/users/${id}/`, data),
  orderDocument: async (id) => (await request('GET', `/orders/${id}/document/`, undefined, { raw: true })).text(),
}

export const money = (n) => '$' + Number(n || 0).toLocaleString('en-CA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const fmtDate = (d) => d ? new Date(d + (String(d).length === 10 ? 'T12:00:00' : '')).toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'

export function downloadText(text, name, type = 'text/csv') {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type }))
  a.download = name
  a.click(); URL.revokeObjectURL(a.href)
}

export function openHtml(html) {
  const w = window.open('', '_blank')
  if (w) { w.document.open(); w.document.write(html); w.document.close() }
  return !!w
}
