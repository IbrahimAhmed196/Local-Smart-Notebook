// One stored message. Messages come from the backend: sender "user" is the person; any other
// sender (a future AI answer) would be shown on the left.

export default function MessageBubble({ message }) {
  const mine = message.sender === 'user'

  const imageUrl =
    message.image_url ||
    message.imageUrl ||
    null

  const featureNames = {
    infographic: 'Infographic',
    presentation: 'Presentation',
    analysis: 'Analysis',
    chat: 'Normal Chat',
  }

  const featureName = message.feature
    ? featureNames[message.feature] || message.feature
    : null

  return (
    <div className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
          mine
            ? 'bg-mauve-600 text-white rounded-br-sm'
            : 'bg-mauve-950 border border-mauve-800 text-white rounded-bl-sm'
        }`}
      >
        {mine && featureName && (
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-mauve-200">
            <span aria-hidden="true">✧</span>
            <span>{featureName}</span>
          </div>
        )}

        <p className="whitespace-pre-wrap break-words">
          {message.content}
        </p>
        {imageUrl && (
  <div className="mt-3 space-y-2">
    <a
      href={imageUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="block"
    >
      <img
        src={imageUrl}
        alt="Chat attachment"
        loading="lazy"
        className="max-h-[420px] max-w-full rounded-xl
          border border-mauve-700 object-contain"
      />
    </a>

    <a
      href={imageUrl}
      download
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-2 rounded-lg
        border border-mauve-400/40 px-3 py-2 text-xs
        font-medium text-white transition hover:bg-mauve-800"
    >
      ↓ Download image
    </a>
  </div>
)}
        <p className="mt-1 text-[11px] text-mauve-200">
          #{message.id} ·{' '}
          {new Date(message.timestamp).toLocaleTimeString()}
        </p>
      </div>
    </div>
  )
}
