import { useEffect, useRef } from 'react'
import ChatInput from './ChatInput.jsx'
import MessageBubble from './MessageBubble.jsx'
import { btnGhost, errorBox } from '../ui.js'

// Messages are stored through the backend API (POST /conversations/{id}/messages).
// There is no AI yet, so nothing replies: this view exists to verify the chat API.
export default function ChatWindow({ notebook, conversation, messages, loading, error, sending, onSend, onRefresh }) {
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [messages, conversation?.id])

  return (
    <section className="flex-1 min-w-0 flex flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto max-w-2xl space-y-3">
          {!notebook && <p className="text-neutral-500">Select or create a notebook in the sidebar.</p>}

          {notebook && (
            <div className="flex items-start justify-between gap-3 pb-2">
              <div className="min-w-0">
                <h2 className="text-xl font-semibold truncate">{conversation ? conversation.title : notebook.title}</h2>
                <p className="text-xs text-neutral-500">
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
            <p className="text-sm text-neutral-400 border border-dashed border-neutral-700 rounded-xl px-4 py-6 text-center">
              Type a message below to start a new chat (it is created through the API), or pick a chat in the sidebar.
            </p>
          )}

          {conversation && messages.length === 0 && !loading && (
            <p className="text-sm text-neutral-500 text-center py-6">No messages yet.</p>
          )}

          {messages.map((m) => <MessageBubble key={m.id} message={m} />)}
          <div ref={endRef} />
        </div>
      </div>

      <div className="border-t border-neutral-800 px-4 py-3">
        <div className="mx-auto max-w-2xl space-y-1.5">
          <ChatInput disabled={!notebook} sending={sending} onSend={onSend}
            placeholder={notebook ? 'Write a message… (Enter to send)' : 'Select a notebook first'} />
          <p className="text-[11px] text-neutral-500">
            Messages are saved by the backend. No AI answer is generated: this chat only tests the API.
          </p>
        </div>
      </div>
    </section>
  )
}
