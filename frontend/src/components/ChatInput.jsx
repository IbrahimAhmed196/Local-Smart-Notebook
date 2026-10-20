import { useRef, useState } from 'react'
import { btnPrimary } from '../ui.js'

// onSend(text) must return a promise resolving to true when the backend accepted the message.
// The text is only cleared on success, so a failed request does not lose what you typed.
export default function ChatInput({ disabled, sending, placeholder, onSend, onUpload, uploading, accept }) {
  const [text, setText] = useState('')
  const fileRef = useRef(null)
  const blocked = disabled || sending

  const submit = async (e) => {
    e.preventDefault()
    const value = text.trim()
    if (!value || blocked) return
    const ok = await onSend(value)
    if (ok) setText('')
  }

  return (
    <form onSubmit={submit} className="flex gap-2 items-end">
      {onUpload && (
        <>
          <input ref={fileRef} type="file" multiple accept={accept} className="hidden"
            onChange={(e) => { onUpload(Array.from(e.target.files)); e.target.value = '' }} />
          <button type="button" onClick={() => fileRef.current?.click()} disabled={disabled || uploading}
            aria-label="Upload files" title="Upload files"
            className="h-11 w-11 shrink-0 rounded-full border-2 border-white bg-black text-2xl font-bold leading-none text-white flex items-center justify-center hover:bg-mauve-600 hover:border-mauve-300 disabled:opacity-40 disabled:cursor-not-allowed">
            {uploading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" /> : '+'}
          </button>
        </>
      )}
      <textarea rows={1} value={text} disabled={blocked} placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e) }}
        className="flex-1 resize-none rounded-xl border border-mauve-600 bg-black px-4 py-3 text-sm text-white placeholder-mauve-300 outline-none focus:border-mauve-300 focus:ring-2 focus:ring-mauve-700 disabled:opacity-50 disabled:cursor-not-allowed" />
      <button type="submit" disabled={blocked || !text.trim()} className={`${btnPrimary} rounded-xl px-5 py-3`}>
        {sending ? 'Sending…' : 'Send'}
      </button>
    </form>
  )
}
