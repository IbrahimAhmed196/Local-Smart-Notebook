import { useState } from 'react'
import { btnGhost, btnPrimary, errorBox, inputCls } from '../ui.js'

const BADGE = {
  UPLOADED: 'bg-neutral-800 text-neutral-200',
  QUEUED: 'bg-neutral-800 text-red-300',
  PROCESSING: 'bg-red-950 text-red-300',
  COMPLETED: 'bg-red-600 text-white',
  FAILED: 'bg-red-950 text-red-400 border border-red-700',
}

const fmtSize = (b) => (b < 1024 * 1024 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1024 / 1024).toFixed(1)} MB`)

function DocItem({ d, onDownload, onDelete, onCheck, onSave }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(d.filename)
  const [desc, setDesc] = useState(d.description || '')
  const [saving, setSaving] = useState(false)

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    const patch = { description: desc.trim() || null }
    if (name.trim() && name.trim() !== d.filename) patch.filename = name.trim()
    const ok = await onSave(d, patch)
    setSaving(false)
    if (ok) setEditing(false)
  }

  return (
    <li className="rounded-lg border border-neutral-800 bg-neutral-950 p-3 text-sm">
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium break-all">{d.filename}</p>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${BADGE[d.status] || BADGE.UPLOADED}`}>{d.status}</span>
      </div>
      <p className="text-xs text-neutral-500 mt-0.5">
        #{d.id} · {d.file_type.toUpperCase()} · {fmtSize(d.file_size)} · {new Date(d.uploaded_at).toLocaleString()}
      </p>
      {d.description && !editing && <p className="text-xs text-neutral-400 mt-1">{d.description}</p>}
      {d.error && <p className="text-xs text-red-400 mt-1">{d.error}</p>}

      {editing ? (
        <form onSubmit={save} className="mt-2 space-y-2">
          <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} aria-label="File name" />
          <input value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={1000} placeholder="Description" className={inputCls} />
          <div className="flex gap-2">
            <button disabled={saving} className={`${btnPrimary} py-1 text-xs`}>{saving ? 'Saving…' : 'Save'}</button>
            <button type="button" onClick={() => { setEditing(false); setName(d.filename); setDesc(d.description || '') }} className={`${btnGhost} py-1 text-xs`}>Cancel</button>
          </div>
        </form>
      ) : (
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
          <button onClick={() => onDownload(d)} className="text-neutral-300 hover:text-red-400">Download</button>
          <button onClick={() => setEditing(true)} className="text-neutral-300 hover:text-red-400">Edit</button>
          <button onClick={() => onCheck(d)} className="text-neutral-300 hover:text-red-400">Check status</button>
          <button onClick={() => onDelete(d)} className="text-neutral-500 hover:text-red-500">Delete</button>
        </div>
      )}
    </li>
  )
}

export default function DocumentList({ docs, total, loading, error, filters, onFilters, onRefresh, onDownload, onDelete, onCheck, onSave }) {
  const [search, setSearch] = useState(filters.search || '')

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium">Documents{docs ? ` (${total})` : ''}</h3>
        <button onClick={onRefresh} disabled={loading} className="text-xs text-neutral-400 hover:text-red-400 disabled:opacity-40">
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); onFilters({ ...filters, search: search.trim() }) }} className="flex gap-2 mb-2">
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by file name" className={`${inputCls} min-w-0 flex-1 py-1.5`} />
        <button className={`${btnGhost} py-1.5 text-xs`}>Search</button>
      </form>
      <div className="flex gap-2 mb-3">
        <select value={filters.sort_by} onChange={(e) => onFilters({ ...filters, sort_by: e.target.value })} className={`${inputCls} py-1.5`} aria-label="Sort by">
          <option value="uploaded_at">Date</option>
          <option value="filename">Name</option>
          <option value="file_size">Size</option>
          <option value="file_type">Type</option>
        </select>
        <select value={filters.order} onChange={(e) => onFilters({ ...filters, order: e.target.value })} className={`${inputCls} py-1.5`} aria-label="Order">
          <option value="desc">Newest / largest first</option>
          <option value="asc">Oldest / smallest first</option>
        </select>
      </div>

      {error && <p className={`${errorBox} mb-2`}>✕ {error}</p>}
      {docs && docs.length === 0 && !loading && !error && (
        <p className="text-sm text-neutral-500 border border-dashed border-neutral-700 rounded-lg px-3 py-4 text-center">
          {filters.search ? 'No documents match this search.' : 'No documents in this notebook yet.'}
        </p>
      )}
      <ul className="space-y-2">
        {(docs || []).map((d) => (
          <DocItem key={`${d.id}-${d.filename}-${d.description}-${d.status}`} d={d}
            onDownload={onDownload} onDelete={onDelete} onCheck={onCheck} onSave={onSave} />
        ))}
      </ul>
      {docs && docs.length > 0 && (
        <p className="text-xs text-neutral-500 mt-3">
          UPLOADED = stored on the backend. Ingestion/indexing is not implemented yet, so documents stay in this status.
        </p>
      )}
    </div>
  )
}
