import { useState } from 'react'
import { btnPrimary, errorBox, inputCls } from '../ui.js'

// The backend protects every endpoint except register/login, so a minimal sign-in is unavoidable.
export default function AuthForm({ onLogin, onRegister, busy, error }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const submit = (e) => {
    e.preventDefault()
    if (mode === 'login') onLogin(email.trim(), password)
    else onRegister(email.trim(), password)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-black px-4">
      <form onSubmit={submit} className="w-full max-w-sm bg-mauve-950 border border-mauve-800 rounded-xl p-6 space-y-4">
        <div>
          <h1 className="text-lg font-semibold"><span className="text-mauve-300">●</span> Local Smart Notebook</h1>
          <p className="text-sm text-mauve-200">API test UI. {mode === 'login' ? 'Sign in' : 'Create an account'} to continue.</p>
        </div>
        <label className="block text-sm">
          <span className="text-mauve-200">Email</span>
          <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={`${inputCls} mt-1`} />
        </label>
        <label className="block text-sm">
          <span className="text-mauve-200">Password {mode === 'register' && <span className="text-mauve-200">(8+ characters)</span>}</span>
          <input type="password" required minLength={mode === 'register' ? 8 : undefined}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            value={password} onChange={(e) => setPassword(e.target.value)} className={`${inputCls} mt-1`} />
        </label>
        {error && <p className={errorBox}>✕ {error}</p>}
        <button type="submit" disabled={busy} className={`${btnPrimary} w-full`}>
          {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Register and sign in'}
        </button>
        <button type="button" onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          className="w-full text-sm text-mauve-200 hover:text-white">
          {mode === 'login' ? 'No account? Register' : 'Have an account? Sign in'}
        </button>
      </form>
    </div>
  )
}
