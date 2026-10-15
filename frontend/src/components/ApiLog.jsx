import { useEffect, useState } from 'react'
import { getBaseUrl, subscribeLog } from '../services/api.js'

export default function ApiLog() {
  const [entries, setEntries] = useState([])
  useEffect(() => subscribeLog(setEntries), [])

  return (
    <div className="border-b border-neutral-800 bg-neutral-950 px-4 py-2 max-h-44 overflow-y-auto font-mono text-xs">
      <p className="text-neutral-500 mb-1">API log · {getBaseUrl()} · newest first</p>
      {entries.length === 0 && <p className="text-neutral-600">No requests yet.</p>}
      {entries.map((e) => (
        <p key={e.id} className="flex gap-3 whitespace-nowrap">
          <span className="text-neutral-600">{e.at.toLocaleTimeString()}</span>
          <span className="w-14 text-neutral-300">{e.method}</span>
          <span className="flex-1 min-w-0 truncate text-neutral-200">{e.path}</span>
          <span className={e.ok ? 'text-neutral-300' : 'text-red-500 font-semibold'}>{e.status}</span>
          <span className="text-neutral-600 w-14 text-right">{e.ms} ms</span>
        </p>
      ))}
    </div>
  )
}
