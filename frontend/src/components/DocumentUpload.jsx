import { useRef, useState } from 'react'
import { uploadDocument } from '../services/api.js'
import { btnPrimary, errorBox, inputCls } from '../ui.js'

// The file is sent to the backend (POST /documents) and stored there under data/uploads.
// The frontend keeps nothing after the upload: the list below is always read from the API.
export default function DocumentUpload({ notebookId, types, onUploaded, notify }) {
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [description, setDescription] = useState('')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  const accept = types ? types.extensions.map((e) => `.${e}`).join(',') : undefined

  const submit = async (e) => {
    e.preventDefault()
    if (!file || uploading) return
    setUploading(true)
    setError('')
    try {
      const doc = await uploadDocument(notebookId, file, description.trim())
      notify('success', `Uploaded "${doc.filename}" to the backend. Status: ${doc.status}.`)
      setFile(null)
      setDescription('')
      if (inputRef.current) inputRef.current.value = ''
      onUploaded()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <input ref={inputRef} type="file" accept={accept} disabled={uploading}
        onChange={(e) => { setFile(e.target.files[0] || null); setError('') }}
        className="block w-full text-sm text-neutral-400 file:mr-3 file:rounded-lg file:border-0 file:bg-red-600 file:px-3 file:py-2 file:text-sm file:text-white hover:file:bg-red-500" />
      {types && <p className="text-xs text-neutral-500">Allowed: {types.extensions.join(', ')} · max {types.max_upload_mb} MB</p>}
      {file && <p className="text-sm text-neutral-300 truncate">Selected: {file.name} ({(file.size / 1024).toFixed(1)} KB)</p>}
      <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={1000}
        placeholder="Description (optional)" disabled={uploading} className={inputCls} />
      <button disabled={!file || uploading} className={`${btnPrimary} w-full`}>{uploading ? 'Uploading…' : 'Upload to backend'}</button>
      {error && <p className={errorBox}>✕ {error}</p>}
    </form>
  )
}
