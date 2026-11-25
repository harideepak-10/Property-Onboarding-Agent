// Local dev: '/api' (proxied by Vite). Deployed: the API's full address, e.g. https://…onrender.com/api
const BASE = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

export function getToken() {
  try { return localStorage.getItem('token') } catch { return null }
}
export function setToken(t) {
  try { t ? localStorage.setItem('token', t) : localStorage.removeItem('token') } catch { /* storage blocked */ }
}

export class ApiError extends Error {}

async function request(method, path, body, { raw = false } = {}) {
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
  orderDocument: async (id) => (await request('GET', `/orders/${id}/document/`, undefined, { raw: true })).text(),
}

export const money = (n) => '$' + Number(n || 0).toLocaleString('en-CA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
