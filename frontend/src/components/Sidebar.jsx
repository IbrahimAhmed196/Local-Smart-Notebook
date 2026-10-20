import { useState } from 'react'
import { btnPrimary, inputCls } from '../ui.js'

const rowCls = (active) =>
  `group flex items-center rounded-lg ${active ? 'bg-mauve-800 border-l-2 border-mauve-300' : 'hover:bg-mauve-800 border-l-2 border-transparent'}`
const iconBtn = 'px-1.5 text-mauve-200 hover:text-white md:opacity-0 group-hover:opacity-100'

export default function Sidebar({
  health, notebooks, activeId, loading, user, open, onClose,
  onCheckHealth, onSelect, onCreate, onRename, onDelete,
  conversations, activeConvId, convLoading, onNewChat, onSelectConv, onRenameConv, onDeleteConv,
  onLogout,
}) {
  const [title, setTitle] = useState('')
  const [creating, setCreating] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (!title.trim() || creating) return
    setCreating(true)
    const ok = await onCreate(title.trim())
    setCreating(false)
    if (ok) setTitle('')
  }

  const dot = health === 'online' ? 'bg-mauve-300' : health === 'offline' ? 'bg-mauve-700' : 'bg-mauve-500 animate-pulse'

  return (
    <>
      {open && <div className="fixed inset-0 bg-black/70 z-20 md:hidden" onClick={onClose} />}
      <aside className={`fixed md:static inset-y-0 left-0 z-30 w-72 shrink-0 bg-mauve-950 border-r border-mauve-800 flex flex-col transition-transform md:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="px-4 py-4 border-b border-mauve-800 flex items-center justify-between">
          <div>
            <h1 className="font-semibold"><span className="text-mauve-300">●</span> Local Smart Notebook</h1>
            
          </div>
          <button onClick={onCheckHealth} title="Check backend (GET /)" className="flex items-center gap-1.5 text-xs text-mauve-200 hover:text-white">
            <span className={`h-2 w-2 rounded-full ${dot}`} />{health === 'online' ? 'online' : health === 'offline' ? 'offline' : '…'}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          <form onSubmit={submit} className="p-3 flex gap-2">
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="New notebook title" className={`${inputCls} min-w-0 flex-1`} />
            <button disabled={!title.trim() || creating} className={btnPrimary}>Add</button>
          </form>

          <nav className="px-2 pb-3">
            <p className="px-2 py-1 text-xs uppercase tracking-wide text-mauve-200">Notebooks</p>
            {loading && <p className="px-2 py-2 text-sm text-mauve-200">Loading…</p>}
            {!loading && notebooks.length === 0 && <p className="px-2 py-2 text-sm text-mauve-200">No notebooks yet. Create one above.</p>}
            <ul className="space-y-0.5">
              {notebooks.map((n) => (
                <li key={n.id} className={rowCls(n.id === activeId)}>
                  <button onClick={() => onSelect(n.id)} className="flex-1 min-w-0 text-left px-3 py-2 text-sm truncate">{n.title}</button>
                  <button onClick={() => onRename(n)} title="Rename notebook" className={iconBtn}>✎</button>
                  <button onClick={() => onDelete(n)} title="Delete notebook" className={`${iconBtn} pr-2`}>✕</button>
                </li>
              ))}
            </ul>
          </nav>

          {activeId != null && (
            <nav className="px-2 pb-3 border-t border-mauve-800 pt-2">
              <div className="flex items-center justify-between px-2 py-1">
                <p className="text-xs uppercase tracking-wide text-mauve-200">Chats</p>
                <button onClick={onNewChat} className="text-xs text-mauve-300 hover:text-white">+ New chat</button>
              </div>
              {convLoading && <p className="px-2 py-2 text-sm text-mauve-200">Loading…</p>}
              {!convLoading && conversations.length === 0 && <p className="px-2 py-2 text-sm text-mauve-200">No chats in this notebook.</p>}
              <ul className="space-y-0.5">
                {conversations.map((c) => (
                  <li key={c.id} className={rowCls(c.id === activeConvId)}>
                    <button onClick={() => onSelectConv(c.id)} className="flex-1 min-w-0 text-left px-3 py-2 text-sm truncate">{c.title}</button>
                    <button onClick={() => onRenameConv(c)} title="Rename chat" className={iconBtn}>✎</button>
                    <button onClick={() => onDeleteConv(c)} title="Delete chat" className={`${iconBtn} pr-2`}>✕</button>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </div>

        <div className="border-t border-mauve-800 p-3 text-sm flex items-center justify-between gap-2">
          <span className="truncate text-mauve-200" title={user?.email}>{user?.email}</span>
          <button onClick={onLogout} className="text-mauve-200 hover:text-white shrink-0">Sign out</button>
        </div>
      </aside>
    </>
  )
}
