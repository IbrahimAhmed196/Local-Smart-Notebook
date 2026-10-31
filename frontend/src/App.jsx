import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from './services/api.js'
import AuthForm from './components/AuthForm.jsx'
import Sidebar from './components/Sidebar.jsx'
import ChatWindow from './components/ChatWindow.jsx'
import DocumentList from './components/DocumentList.jsx'
import { btnGhost } from './ui.js'

const DEFAULT_FILTERS = { search: '', sort_by: 'uploaded_at', order: 'desc' }

export default function App() {
  const [authed, setAuthed] = useState(!!api.getToken())
  const [user, setUser] = useState(null)
  const [authBusy, setAuthBusy] = useState(false)
  const [authError, setAuthError] = useState('')
  const [health, setHealth] = useState('checking')

  const [notebooks, setNotebooks] = useState([])
  const [nbLoading, setNbLoading] = useState(false)
  const [activeId, setActiveId] = useState(null)

  const [docs, setDocs] = useState(null)
  const [docTotal, setDocTotal] = useState(0)
  const [docsLoading, setDocsLoading] = useState(false)
  const [docsError, setDocsError] = useState('')
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [types, setTypes] = useState(null)

  const [conversations, setConversations] = useState([])
  const [convLoading, setConvLoading] = useState(false)
  const [activeConv, setActiveConv] = useState(null)
  const [messages, setMessages] = useState([])
  const [msgLoading, setMsgLoading] = useState(false)
  const [chatError, setChatError] = useState('')
  const [sending, setSending] = useState(false)
  const openSeq = useRef(0) // ignores out-of-date responses when you click quickly

  const [notice, setNotice] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [uploading, setUploading] = useState(false)

  const notify = useCallback((type, text) => {
    setNotice({ type, text })
    setTimeout(() => setNotice((n) => (n && n.text === text ? null : n)), 5000)
  }, [])

  const checkHealth = useCallback(async () => {
    setHealth('checking')
    try { await api.health(); setHealth('online') } catch { setHealth('offline') }
  }, [])
  useEffect(() => { checkHealth() }, [checkHealth])

  const logout = useCallback(() => {
    api.clearToken()
    setAuthed(false)
    setUser(null)
    setNotebooks([])
    setActiveId(null)
    setDocs(null)
    setConversations([])
    setActiveConv(null)
    setMessages([])
  }, [])

  useEffect(() => { api.setUnauthorizedHandler(() => { logout(); setAuthError('Session expired. Please sign in again.') }) }, [logout])

  // ---- load user, notebooks and supported types once signed in ----
  useEffect(() => {
    if (!authed) return
    let cancelled = false
    ;(async () => {
      setNbLoading(true)
      try {
        const [me, list, t] = await Promise.all([api.getMe(), api.listNotebooks(), api.getSupportedTypes()])
        if (cancelled) return
        setUser(me)
        setNotebooks(list)
        setTypes(t)
        setActiveId((cur) => cur ?? list[0]?.id ?? null)
      } catch (err) {
        if (!cancelled) notify('error', err.message)
      } finally {
        if (!cancelled) setNbLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [authed, notify])

  // ---- documents ----
  const loadDocs = useCallback(async () => {
    if (activeId == null) { setDocs(null); return }
    setDocsLoading(true)
    setDocsError('')
    try {
      const res = await api.listDocuments(activeId, filters)
      setDocs(res.items)
      setDocTotal(res.total)
    } catch (err) {
      setDocsError(err.message)
    } finally {
      setDocsLoading(false)
    }
  }, [activeId, filters])
  useEffect(() => { loadDocs() }, [loadDocs])

  // ---- conversations of the active notebook ----
  useEffect(() => {
    openSeq.current++
    setActiveConv(null)
    setMessages([])
    setChatError('')
    setConversations([])
    if (activeId == null) return
    let cancelled = false
    ;(async () => {
      setConvLoading(true)
      try {
        const list = await api.listConversations(activeId)
        if (!cancelled) setConversations(list)
      } catch (err) {
        if (!cancelled) setChatError(err.message)
      } finally {
        if (!cancelled) setConvLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [activeId])

  const openConversation = async (id) => {
    const seq = ++openSeq.current
    setSidebarOpen(false)
    setMsgLoading(true)
    setChatError('')
    try {
      const h = await api.getConversationHistory(id) // {conversation, messages}
      if (seq !== openSeq.current) return
      setActiveConv(h.conversation)
      setMessages(h.messages)
      
    } catch (err) {
      if (seq === openSeq.current) setChatError(err.message)
    } finally {
      if (seq === openSeq.current) setMsgLoading(false)
    }
  }

  const reloadMessages = async () => {
    if (!activeConv) return
    const id = activeConv.id
    setMsgLoading(true)
    setChatError('')
    try {
      const list = await api.listMessages(id)
      if (activeConv && id === activeConv.id) setMessages(list)
    } catch (err) {
      setChatError(err.message)
    } finally {
      setMsgLoading(false)
    }
  }

  const newChat = () => {
    openSeq.current++
    setActiveConv(null)
    setMessages([])
    setChatError('')
    setSidebarOpen(false)
  }

  // Sends the question to the AI and shows its answer in the chat.
  // Resolves to true if the backend stored the question (the input is restored otherwise).

  // Sends the question and keeps the selected feature with the message.
  const send = async (text, feature = null) => {
    if (sending || activeId == null) return false

    setSending(true)
    setChatError('')

    const tempId = `pending-${Date.now()}`
    let shown = false

    try {
      let conv = activeConv

      if (!conv) {
        conv = await api.createConversation(activeId, text.slice(0, 40))
        setConversations((l) => [conv, ...l])
        setActiveConv(conv)
      }

      // Keep the original text and selected feature in the frontend state.
      setMessages((m) => [
        ...m,
        {
          id: tempId,
          sender: 'user',
          content: text,
          feature,
          timestamp: new Date().toISOString(),
          pending: true,
        },
      ])
      shown = true

      // The API still receives the original text in this frontend-only step.
      const res = await api.askAi(conv.id, text, feature);
      setMessages((m) => {
        return m.map((x) => {
          if (x.id === tempId) {
            return {
              ...res.user_message,
              feature: res.user_message.feature ?? feature,
            };
          }
          return x;
        }).concat(
          res.assistant_message
            ? [{
                ...res.assistant_message,
                sources: res.sources,
              }]
            : []
        );
      });      
      

      if (res.error) setChatError(res.error)

      return true
    } catch (err) {
      if (shown) {
        setMessages((m) => m.filter((x) => x.id !== tempId))
      }

      setChatError(err.message)
      return false
    } finally {
      setSending(false)
    }
  }


  const renameConv = async (c) => {
    const title = window.prompt('Rename chat', c.title)?.trim()
    if (!title || title === c.title) return
    try {
      const updated = await api.renameConversation(c.id, title)
      setConversations((l) => l.map((x) => (x.id === c.id ? updated : x)))
      if (activeConv?.id === c.id) setActiveConv(updated)
      notify('success', 'Chat renamed.')
    } catch (err) {
      notify('error', err.message)
    }
  }

  const deleteConv = async (c) => {
    if (!window.confirm(`Delete chat "${c.title}" and its messages?`)) return
    try {
      await api.deleteConversation(c.id)
      setConversations((l) => l.filter((x) => x.id !== c.id))
      if (activeConv?.id === c.id) newChat()
      notify('success', 'Chat deleted.')
    } catch (err) {
      notify('error', err.message)
    }
  }

  // ---- auth ----
  const handleAuth = async (fn, email, password) => {
    setAuthBusy(true)
    setAuthError('')
    try {
      if (fn === 'register') await api.register(email, password)
      api.setToken(await api.login(email, password))
      setAuthed(true)
    } catch (err) {
      setAuthError(err.message)
    } finally {
      setAuthBusy(false)
    }
  }

  // ---- notebooks ----
  const createNotebook = async (title) => {
    try {
      const nb = await api.createNotebook(title)
      setNotebooks((l) => [...l, nb])
      setActiveId(nb.id)
      notify('success', `Notebook "${nb.title}" created.`)
      return true
    } catch (err) {
      notify('error', err.message)
      return false
    }
  }

  const renameNotebook = async (nb) => {
    const title = window.prompt('Rename notebook', nb.title)?.trim()
    if (!title || title === nb.title) return
    try {
      const updated = await api.updateNotebook(nb.id, title, nb.description)
      setNotebooks((l) => l.map((n) => (n.id === nb.id ? updated : n)))
      notify('success', 'Notebook renamed.')
    } catch (err) {
      notify('error', err.message)
    }
  }

  const deleteNotebook = async (nb) => {
    if (!window.confirm(`Delete notebook "${nb.title}", its documents and its chats?`)) return
    try {
      await api.deleteNotebook(nb.id)
      const rest = notebooks.filter((n) => n.id !== nb.id)
      setNotebooks(rest)
      if (activeId === nb.id) setActiveId(rest[0]?.id ?? null)
      notify('success', 'Notebook deleted.')
    } catch (err) {
      notify('error', err.message)
    }
  }

  // ---- documents actions ----
  const replaceDoc = (updated) => setDocs((l) => (l ? l.map((d) => (d.id === updated.id ? updated : d)) : l))

  const deleteDoc = async (d) => {
    if (!window.confirm(`Delete "${d.filename}"?`)) return
    try {
      await api.deleteDocument(d.id)
      notify('success', 'Document deleted.')
      loadDocs()
    } catch (err) {
      notify('error', err.message)
    }
  }

  const saveDoc = async (d, patch) => {
    try {
      replaceDoc(await api.updateDocument(d.id, patch))
      notify('success', 'Document updated.')
      return true
    } catch (err) {
      notify('error', err.message)
      return false
    }
  }

  const checkDoc = async (d) => {
    try {
      const fresh = await api.getDocument(d.id)
      replaceDoc(fresh)
      notify('success', `"${fresh.filename}" status: ${fresh.status}.`)
    } catch (err) {
      notify('error', err.message)
    }
  }

  // Called by the + button as soon as the user picks file(s) in the system file window.
  const uploadFiles = async (files) => {
    if (!active || uploading || !files.length) return
    setUploading(true)
    let ok = 0
    for (const file of files) {
      try {
        const doc = await api.uploadDocument(active.id, file, '')
        ok++
        notify('success', `Uploaded "${doc.filename}". Status: ${doc.status}.`)
      } catch (err) {
        notify('error', `${file.name}: ${err.message}`)
      }
    }
    setUploading(false)
    if (ok) loadDocs()
  }

  const downloadDoc = async (d) => {
    try { await api.downloadDocument(d) } catch (err) { notify('error', err.message) }
  }

  if (!authed) {
    return <AuthForm busy={authBusy} error={authError}
      onLogin={(e, p) => handleAuth('login', e, p)} onRegister={(e, p) => handleAuth('register', e, p)} />
  }

  const active = notebooks.find((n) => n.id === activeId) || null
  
  return (
    <div className="h-screen flex bg-black text-white">
      <Sidebar health={health} onCheckHealth={checkHealth}
        notebooks={notebooks} activeId={activeId} loading={nbLoading} user={user}
        open={sidebarOpen} onClose={() => setSidebarOpen(false)}
        onSelect={(id) => { setActiveId(id); setSidebarOpen(false) }}
        onCreate={createNotebook} onRename={renameNotebook} onDelete={deleteNotebook}
        conversations={conversations} activeConvId={activeConv?.id ?? null} convLoading={convLoading}
        onNewChat={newChat} onSelectConv={openConversation} onRenameConv={renameConv} onDeleteConv={deleteConv}
        onLogout={logout} />

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="flex items-center justify-between gap-2 border-b border-mauve-800 bg-black px-3 py-2">
          <button onClick={() => setSidebarOpen(true)} className={`${btnGhost} md:hidden py-1`}>☰ Menu</button>
          <span className="hidden md:block text-sm text-mauve-200 truncate">{active ? active.title : 'No notebook selected'}</span>
        </header>

        {notice && (
          <div role="status" onClick={() => setNotice(null)}
            className={`mx-4 mt-3 rounded-lg border px-3 py-2 text-sm cursor-pointer ${notice.type === 'error' ? 'border-rose-400 bg-rose-950 text-rose-100' : 'border-mauve-700 bg-mauve-950 text-white'}`}>
            {notice.type === 'error' ? '✕ ' : '✓ '}{notice.text}
          </div>
        )}

        <div className="flex-1 min-h-0 flex">
          <ChatWindow notebook={active} conversation={activeConv} messages={messages}
            loading={msgLoading} error={chatError} sending={sending} onSend={send} onRefresh={reloadMessages}
            onUpload={uploadFiles} uploading={uploading}
            accept={types ? types.extensions.map((e) => `.${e}`).join(',') : undefined}
            docCount={docs ? docTotal : null}
            documents={active && (
              <DocumentList docs={docs} total={docTotal} loading={docsLoading} error={docsError}
                filters={filters} onFilters={setFilters}
                onRefresh={loadDocs} onDownload={downloadDoc} onDelete={deleteDoc} onCheck={checkDoc} onSave={saveDoc} />
            )} />
        </div>
      </div>
    </div>
  )
}
