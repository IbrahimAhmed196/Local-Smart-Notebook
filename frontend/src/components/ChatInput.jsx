import { useState } from 'react'
import { btnPrimary } from '../ui.js'

// onSend(text) must return a promise resolving to true when the backend accepted the message.
// The text is only cleared on success, so a failed request does not lose what you typed.
export default function ChatInput({ disabled, sending, placeholder, onSend }) {
  const [text, setText] = useState('')
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
      <textarea rows={1} value={text} disabled={blocked} placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e) }}
        className="flex-1 resize-none rounded-xl border border-neutral-700 bg-neutral-900 px-4 py-3 text-sm text-neutral-100 placeholder-neutral-500 outline-none focus:border-red-600 disabled:opacity-50 disabled:cursor-not-allowed" />
      <button type="submit" disabled={blocked || !text.trim()} className={`${btnPrimary} rounded-xl px-5 py-3`}>
        {sending ? 'Sending…' : 'Send'}
      </button>
    </form>
  )
}
