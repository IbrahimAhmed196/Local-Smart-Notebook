import { useEffect, useRef, useState } from 'react'
import ChatInput from './ChatInput.jsx'
import MessageBubble from './MessageBubble.jsx'
import { btnGhost, errorBox } from '../ui.js'

// Messages are stored through the backend API (POST /conversations/{id}/messages).
// There is no AI yet, so nothing replies: this view exists to verify the chat API.
export default function ChatWindow({ notebook, conversation, messages, loading, error, sending, onSend, onRefresh, onUpload, uploading, accept, docCount, documents }) {
  const endRef = useRef(null)
  const [panelOpen, setPanelOpen] = useState(false)
  useEffect(() => { setPanelOpen(false) }, [notebook?.id])
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [messages, conversation?.id])

  return (
    <section className="flex-1 min-w-0 flex flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto max-w-2xl space-y-3">
          {!notebook && <p className="text-mauve-200">Select or create a notebook in the sidebar.</p>}

          {notebook && (
            <div className="flex items-start justify-between gap-3 pb-2">
              <div className="min-w-0">
                <h2 className="text-xl font-semibold truncate">{conversation ? conversation.title : notebook.title}</h2>
                <p className="text-xs text-mauve-200">
                  {conversation
                    ? `Chat #${conversation.id} · ${messages.length} message${messages.length === 1 ? '' : 's'} stored on the server`
                    : `Notebook: ${notebook.title}`}
                </p>
              </div>
              {conversation && (
                <button onClick={onRefresh} disabled={loading} className={`${btnGhost} shrink-0 py-1 text-xs`}>
                  {loading ? 'Loading…' : 'Reload'}
                </button>
              )}
            </div>
          )}

          {error && <p className={errorBox}>✕ {error}</p>}

          {notebook && !conversation && (
            <p className="text-sm text-mauve-200 border border-dashed border-mauve-700 rounded-xl px-4 py-6 text-center">
              Type a message below to start a new chat (it is created through the API), or pick a chat in the sidebar.
            </p>
          )}

          {conversation && messages.length === 0 && !loading && (
            <p className="text-sm text-mauve-200 text-center py-6">No messages yet.</p>
          )}

          {messages.map((m) => <MessageBubble key={m.id} message={m} />)}
          <div ref={endRef} />
        </div>
      </div>

      <div className="relative border-t border-mauve-800 bg-black px-4 py-3">
        {panelOpen && documents && (
          <div className="absolute inset-x-4 bottom-full mb-2 mx-auto max-w-2xl max-h-[60vh] overflow-y-auto rounded-2xl border border-mauve-700 bg-black p-4 shadow-lg shadow-black">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-semibold text-white"><span className="text-mauve-300">▍</span>Documents</h2>
              <button type="button" onClick={() => setPanelOpen(false)} aria-label="Close" className="text-mauve-300 hover:text-white">✕</button>
            </div>
            {documents}
          </div>
        )}
        <div className="mx-auto max-w-2xl space-y-1.5">
          <ChatInput disabled={!notebook} sending={sending} onSend={onSend}
            onUpload={onUpload} uploading={uploading} accept={accept}
            placeholder={notebook ? 'Write a message… (Enter to send)' : 'Select a notebook first'} />
          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] text-mauve-200">
              Messages are saved by the backend. No AI answer is generated: this chat only tests the API.
            </p>
            {notebook && (
              <button type="button" onClick={() => setPanelOpen((o) => !o)} aria-expanded={panelOpen}
                className="shrink-0 rounded-md border border-mauve-700 px-2 py-1 text-xs font-medium text-mauve-100 hover:border-mauve-300 hover:bg-mauve-800">
                Documents{docCount != null ? ` (${docCount})` : ''}
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
