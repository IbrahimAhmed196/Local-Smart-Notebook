// All communication with the FastAPI backend lives here.
// Every endpoint below exists and is mounted in backend/app/main.py:
//   GET  /                                   health check
//   POST /auth/register, POST /auth/login, GET /auth/me
//   POST/GET /notebooks/, PUT/DELETE /notebooks/{id}
//   POST/GET /documents, GET /documents/supported-types,
//   GET/PATCH/DELETE /documents/{id}, GET /documents/{id}/download
//   POST/GET /conversations, GET/PATCH/DELETE /conversations/{id},
//   POST/GET /conversations/{id}/messages, POST /conversations/{id}/ask (AI answer)

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const TOKEN_KEY = 'lsn_token'

export const getBaseUrl = () => BASE_URL
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

let onUnauthorized = () => {}
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

// ---- request log (method, path, status, time only: never bodies or tokens) ----
const logEntries = []
const logListeners = new Set()
let logId = 0
function pushLog(entry) {
  logEntries.unshift({ id: ++logId, at: new Date(), ...entry })
  if (logEntries.length > 40) logEntries.pop()
  logListeners.forEach((fn) => fn([...logEntries]))
}
export function subscribeLog(fn) {
  logListeners.add(fn)
  fn([...logEntries])
  return () => logListeners.delete(fn)
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

// FastAPI returns {"detail": "text"} for our errors and {"detail": [{loc, msg}, ...]} for 422.
function detailToText(detail, fallback) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc || []).slice(1).join('.') || 'field'}: ${d.msg}`).join('; ')
  }
  return fallback
}

async function request(path, { method = 'GET', json, form, urlencoded, auth = true, raw = false } = {}) {
  const headers = {}
  let body
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  } else if (urlencoded) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    body = new URLSearchParams(urlencoded)
  } else if (form) {
    body = form // the browser sets the multipart boundary itself
  }
  if (auth && getToken()) headers.Authorization = `Bearer ${getToken()}`

  const started = performance.now()
  const ms = () => Math.round(performance.now() - started)
  const logPath = path.split('?')[0]

  let res
  try {
    res = await fetch(`${BASE_URL}${path}`, { method, headers, body })
  } catch {
    pushLog({ method, path: logPath, status: 'network error', ok: false, ms: ms() })
    throw new ApiError(
      `Cannot reach the backend at ${BASE_URL}. Is it running? (If it is, check CORS_ORIGINS / the browser console.)`,
      0,
    )
  }

  pushLog({ method, path: logPath, status: res.status, ok: res.ok, ms: ms() })

  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try {
      const data = await res.json()
      message = detailToText(data.detail, message)
    } catch { /* body was not JSON */ }
    if (res.status === 401 && auth && getToken()) onUnauthorized()
    throw new ApiError(message, res.status)
  }

  if (res.status === 204) return null
  return raw ? res : res.json()
}

// ---- Health ----
export const health = () => request('/', { auth: false })

// ---- Auth ----
export const register = (email, password) =>
  request('/auth/register', { method: 'POST', json: { email, password }, auth: false })

export async function login(email, password) {
  // OAuth2 password form: the "username" field carries the e-mail address.
  const data = await request('/auth/login', {
    method: 'POST',
    urlencoded: { username: email, password },
    auth: false,
  })
  return data.access_token
}

export const getMe = () => request('/auth/me')

// ---- Notebooks (trailing slash matters: the routes are defined as "/notebooks/") ----
export const listNotebooks = () => request('/notebooks/')
export const createNotebook = (title, description) =>
  request('/notebooks/', { method: 'POST', json: { title, description: description || null } })
export const updateNotebook = (id, title, description) =>
  request(`/notebooks/${id}`, { method: 'PUT', json: { title, description: description || null } })
export const deleteNotebook = (id) => request(`/notebooks/${id}`, { method: 'DELETE' })

// ---- Documents ----
export const getSupportedTypes = () => request('/documents/supported-types')

export function listDocuments(notebookId, { search, sort_by, order, limit = 200, offset = 0 } = {}) {
  const q = new URLSearchParams({ notebook_id: String(notebookId), limit: String(limit), offset: String(offset) })
  if (search) q.set('search', search)
  if (sort_by) q.set('sort_by', sort_by)
  if (order) q.set('order', order)
  return request(`/documents?${q}`)
}

export const getDocument = (id) => request(`/documents/${id}`)

export function uploadDocument(notebookId, file, description) {
  const form = new FormData()
  form.append('notebook_id', String(notebookId))
  form.append('file', file)
  if (description) form.append('description', description)
  return request('/documents', { method: 'POST', form })
}

// Only send the fields you want to change. An explicit description (even null) clears/sets it.
export const updateDocument = (id, patch) => request(`/documents/${id}`, { method: 'PATCH', json: patch })

export const deleteDocument = (id) => request(`/documents/${id}`, { method: 'DELETE' })

// The download endpoint needs the Authorization header, so a plain <a href> would not work.
export async function downloadDocument(doc) {
  const res = await request(`/documents/${doc.id}/download`, { raw: true })
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = doc.filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// ---- Conversations & messages ----
export const createConversation = (notebookId, title) =>
  request('/conversations', { method: 'POST', json: { notebook_id: notebookId, title } })
export const listConversations = (notebookId) =>
  request(`/conversations?notebook_id=${encodeURIComponent(notebookId)}&limit=100`)
export const getConversationHistory = (id) => request(`/conversations/${id}?limit=200`) // {conversation, messages}
export const renameConversation = (id, title) =>
  request(`/conversations/${id}`, { method: 'PATCH', json: { title } })
export const deleteConversation = (id) => request(`/conversations/${id}`, { method: 'DELETE' })
export const listMessages = (id) => request(`/conversations/${id}/messages?limit=200`)
export const sendMessage = (id, content) =>
  request(`/conversations/${id}/messages`, { method: 'POST', json: { content } })
// Stores the question AND asks the AI model (it sees this chat's history and the notebook's
// uploaded files). Resolves to {user_message, assistant_message | null, error | null, sources: [filenames]}.
// If the model is down, the question is still stored and `error` explains why.
export const askAi = (id, content) =>
  request(`/conversations/${id}/ask`, { method: 'POST', json: { content } })
