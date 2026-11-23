import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { useI18n } from '../i18n'

export default function Login() {
  const { user, login } = useAuth()
  const { t } = useI18n()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) {
    const from = (location.state as { from?: string } | null)?.from ?? '/'
    return <Navigate to={from} replace />
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setError(t('login.invalid'))
      else if (err instanceof ApiError && err.status === 429) setError(t('login.locked'))
      else setError(t('login.error'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
    <main className="login">
      <span className="hanko vertical logo" aria-hidden>御朱印帳</span>
      <h1>Goshuinchō</h1>
      <p className="muted">{t('app.tagline')}</p>
      <form onSubmit={submit} className="card">
        <h2>{t('login.title')}</h2>
        <label>
          {t('login.email')}
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          {t('login.password')}
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {t('login.submit')}
        </button>
      </form>
    </main>
    </div>
  )
}
