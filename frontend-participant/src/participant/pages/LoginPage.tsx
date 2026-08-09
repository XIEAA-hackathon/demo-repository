import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'

export default function LoginPage() {
  const { authenticated, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)

  if (authenticated) return <Navigate to="/participant" replace />

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setWorking(true)
    setError('')
    try {
      await login(email, password)
      const from = (location.state as { from?: string } | null)?.from
      navigate(from && from !== '/login' ? from : '/participant', { replace: true })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Sign in failed.')
    } finally {
      setWorking(false)
    }
  }

  return (
    <main className="participant-login">
      <section className="participant-login__card">
        <div className="brand participant-login__brand"><span className="brand__mark">X</span><span><strong>Bid to Build</strong><small>Participant portal</small></span></div>
        <p className="eyebrow">Team access</p>
        <h1>Welcome back</h1>
        <p className="muted">Use the credentials issued by the event administrator.</p>
        <form className="form" onSubmit={submit}>
          <label><span>Email</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required /></label>
          <label><span>Password</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="button button--primary" disabled={working} type="submit">{working ? 'Signing in…' : 'Sign in'}</button>
        </form>
      </section>
    </main>
  )
}
