
import { useRef, useState } from 'react'
import { btnPrimary } from '../ui.js'

const FEATURES = [
  {
    id: 'infographic',
    label: 'Infographic',
    description: 'Turn information into a visual infographic.',
    icon: '▦',
  },
  {
    id: 'presentation',
    label: 'Presentation',
    description: 'Create structured presentation slides.',
    icon: '▤',
  },
  {
    id: 'analysis',
    label: 'Analysis',
    description: 'Analyze information and extract insights.',
    icon: '⌁',
  },
  {
    id: 'chat',
    label: 'Normal Chat',
    description: 'Chat with the AI normally.',
    icon: '✧',
  },
]

// onSend(text, feature) must return a promise resolving to true
// when the backend accepts the message.
// The second argument is optional for existing onSend handlers.
export default function ChatInput({
  disabled,
  sending,
  placeholder,
  onSend,
  onUpload,
  uploading,
  accept,
  onFeatureChange,
}) {
  const [text, setText] = useState('')
  const [selectedFeature, setSelectedFeature] = useState(null)
  const [featuresOpen, setFeaturesOpen] = useState(false)

  const fileRef = useRef(null)
  const blocked = disabled || sending

  const chooseFeature = (feature) => {
    setSelectedFeature(feature)
    setFeaturesOpen(false)
    onFeatureChange?.(feature)
  }

  const submit = async (e) => {
    e.preventDefault()

    const value = text.trim()
    if (!value || blocked) return

    const ok = await onSend(value, selectedFeature)

    if (ok) setText('')
  }

  const currentFeature = FEATURES.find(
    (feature) => feature.id === selectedFeature
  )

  return (
    <form onSubmit={submit} className="flex items-end gap-2">
      {/* Feature selector */}
      <div className="relative shrink-0">
        <button
          type="button"
          onClick={() => setFeaturesOpen((open) => !open)}
          disabled={blocked}
          aria-label="Choose AI feature"
          aria-expanded={featuresOpen}
          aria-haspopup="menu"
          title="Choose AI feature"
          className={`flex h-11 items-center justify-center gap-2 rounded-xl
            border px-3 text-sm font-medium transition-colors
            disabled:cursor-not-allowed disabled:opacity-40
            ${
              currentFeature
                ? 'border-mauve-300 bg-mauve-700 text-white'
                : 'border-mauve-600 bg-black text-white hover:bg-mauve-900'
            }`}
        >
          <span className="text-lg">✧</span>
          <span>Features</span>
          <span className="text-xs">
            {featuresOpen ? '▲' : '▼'}
          </span>
        </button>

        {featuresOpen && (
          <div
            role="menu"
            aria-label="AI features"
            className="absolute bottom-full left-0 z-50 mb-2
              w-72 max-w-[85vw] overflow-hidden rounded-xl
              border border-mauve-600 bg-black p-2 text-white shadow-xl"
          >
            <p className="px-3 py-2 text-xs text-mauve-300">
              Choose what the AI should do
            </p>

            {FEATURES.map((feature) => {
              const selected = selectedFeature === feature.id

              return (
                <button
                  key={feature.id}
                  type="button"
                  role="menuitemradio"
                  aria-checked={selected}
                  onClick={() => chooseFeature(feature.id)}
                  className={`flex w-full items-center gap-3 rounded-lg
                    px-3 py-3 text-left transition-colors
                    ${
                      selected
                        ? 'bg-mauve-800'
                        : 'hover:bg-mauve-900'
                    }`}
                >
                  <span className="flex h-9 w-9 shrink-0 items-center
                    justify-center rounded-lg bg-mauve-950 text-xl">
                    {feature.icon}
                  </span>

                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold">
                      {feature.label}
                    </span>
                    <span className="mt-1 block text-xs text-mauve-300">
                      {feature.description}
                    </span>
                  </span>

                  {selected && (
                    <span className="text-mauve-200">✓</span>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* File upload */}
      {onUpload && (
        <>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept={accept}
            className="hidden"
            onChange={(e) => {
              onUpload(Array.from(e.target.files))
              e.target.value = ''
            }}
          />

          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={disabled || uploading}
            aria-label="Upload files"
            title="Upload files"
            className="flex h-11 w-11 shrink-0 items-center
              justify-center rounded-full border-2 border-white
              bg-black text-2xl font-bold leading-none text-white
              hover:border-mauve-300 hover:bg-mauve-600
              disabled:cursor-not-allowed disabled:opacity-40"
          >
            {uploading ? (
              <span className="h-4 w-4 animate-spin rounded-full
                border-2 border-white border-t-transparent" />
            ) : (
              '+'
            )}
          </button>
        </>
      )}

      {/* Message input */}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {currentFeature && (
          <div className="flex items-center gap-2 px-1 text-xs text-mauve-200">
            <span>{currentFeature.icon}</span>
            <span>{currentFeature.label} selected</span>
            <button
              type="button"
              onClick={() => chooseFeature(null)}
              disabled={blocked}
              aria-label="Clear selected feature"
              className="rounded px-1 hover:bg-mauve-900
                disabled:opacity-40"
            >
              ✕
            </button>
          </div>
        )}

        <textarea
          rows={1}
          value={text}
          disabled={blocked}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
               e.preventDefault()
               e.currentTarget.form?.requestSubmit()
            }
          }}
          className="w-full resize-none rounded-xl border
            border-mauve-600 bg-black px-4 py-3 text-sm
            text-white outline-none placeholder:text-mauve-300
            focus:border-mauve-300 focus:ring-2 focus:ring-mauve-700
            disabled:cursor-not-allowed disabled:opacity-50"
        />
      </div>

      {/* Send */}
      <button
        type="submit"
        disabled={blocked || !text.trim()}
        className={`${btnPrimary} shrink-0 rounded-xl px-5 py-3`}
      >
        {sending ? 'Sending…' : 'Send'}
      </button>
    </form>
  )
}
