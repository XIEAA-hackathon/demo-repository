import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import posterImage from "../assets/poster.png";
import { login } from "../services/api";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async (event) => {
    event.preventDefault(); setLoading(true); setError("");
    try { await login(email, password); onLogin(); }
    catch (cause) { setError(cause.message || "Authentication failed."); }
    finally { setLoading(false); }
  };
  return (
    <main className="login-page" style={{ backgroundImage: `url(${posterImage})` }}>
      <div className="login-overlay" />
      <div className="login-content">
        <div className="brand-header"><div className="brand-icon">♠</div><div><h1>BID TO BUILD</h1><span>ADMIN CONTROL CENTER</span></div></div>
        <section className="login-card">
          <span className="eyebrow">Authorized access</span><h2>Welcome, Admin</h2>
          <p className="login-description">Authenticate through the event server to control the live auction.</p>
          <form onSubmit={submit}>
            <label htmlFor="admin-email">Email / Username</label><input id="admin-email" type="text" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required />
            <label htmlFor="admin-password">Password</label><div className="password-wrapper"><input id="admin-password" type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /><button className="show-password" type="button" aria-label={showPassword ? "Hide password" : "Show password"} title={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword((value) => !value)}>{showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}</button></div>
            {error && <div className="login-error" role="alert">{error}</div>}
            <button className="login-button" disabled={loading} type="submit">{loading ? "AUTHENTICATING…" : "ENTER CONTROL CENTER"}<span>→</span></button>
          </form>
          <div className="system-status"><span className="status-dot online" />Backend authentication required</div>
        </section>
        <p className="login-footer">XIE · ALUMNI COMMITTEE · BID TO BUILD</p>
      </div>
    </main>
  );
}
