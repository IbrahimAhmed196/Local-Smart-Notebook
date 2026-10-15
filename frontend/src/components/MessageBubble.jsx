// One stored message. Messages come from the backend: sender "user" is the person; any other
// sender (a future AI answer) would be shown on the left.
export default function MessageBubble({ message }) {
  const mine = message.sender === 'user'
  return (
    <div className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${mine ? 'bg-red-600 text-white rounded-br-sm' : 'bg-neutral-900 border border-neutral-800 text-neutral-100 rounded-bl-sm'}`}>
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
        <p className={`mt-1 text-[11px] ${mine ? 'text-red-200' : 'text-neutral-500'}`}>
          #{message.id} · {new Date(message.timestamp).toLocaleTimeString()}
        </p>
      </div>
    </div>
  )
}
