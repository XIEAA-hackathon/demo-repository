import { useRef, useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { LOGIN_PENDING_LABEL } from '../services/loginMessages'

export default function LoginPage() {
  const { authenticated, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const submitInFlight = useRef(false)
  if (authenticated) return <Navigate to="/participant" replace />

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (submitInFlight.current) return
    submitInFlight.current = true
    setWorking(true)
    setError('')
    try {
      await login(email, password)
      const from = (location.state as { from?: string } | null)?.from
      navigate(from && from !== '/participant/login' ? from : '/participant', { replace: true })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Sign in failed.')
    } finally {
      submitInFlight.current = false
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
          <label><span>Email or participant ID</span><input type="text" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required /></label>
          <label><span>Password</span><div className="participant-password-field"><input type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /><button type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} title={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}</button></div></label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="button button--primary" disabled={working} type="submit">{working ? LOGIN_PENDING_LABEL : 'Sign in'}</button>
        </form>
      </section>
    </main>
  )
}
