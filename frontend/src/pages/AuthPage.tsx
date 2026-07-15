import { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { ApiError } from '../lib/api'
import { IconAlert, IconGlobe, IconLock, IconMic, IconShield, IconSparkle } from '../components/Icons'

/**
 * Password strength meter.
 *
 * Scores length first because length is what actually resists cracking. It is a
 * guide for the user, not a gate - the real rules are enforced server-side in
 * schemas.py, since anything checked only in the browser is not a rule at all.
 */
function scorePassword(pw: string): { score: number; label: string; color: string } {
  if (!pw) return { score: 0, label: '', color: 'var(--text-quaternary)' }

  let score = 0
  if (pw.length >= 10) score += 1
  if (pw.length >= 14) score += 1
  if (pw.length >= 18) score += 1
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score += 1
  if (/\d/.test(pw)) score += 0.5
  if (/[^A-Za-z0-9]/.test(pw)) score += 1
  if (new Set(pw).size >= 8) score += 0.5

  const capped = Math.min(4, Math.floor(score))
  const labels = ['Too weak', 'Weak', 'Fair', 'Strong', 'Excellent']
  const colors = ['var(--danger)', 'var(--danger)', 'var(--warning)', 'var(--success)', 'var(--success)']
  return { score: capped, label: labels[capped] ?? '', color: colors[capped] ?? 'var(--text-quaternary)' }
}

const FEATURES = [
  {
    icon: IconMic,
    title: 'Transcription that runs here',
    body: 'Whisper executes on your GPU. Your recordings never touch a third-party server.',
  },
  {
    icon: IconSparkle,
    title: 'Summaries and action items',
    body: 'A local Llama model reads the transcript and pulls out who committed to what, with timestamps.',
  },
  {
    icon: IconGlobe,
    title: 'Hindi and English, together',
    body: 'Built for how meetings actually sound, including code-switching mid-sentence.',
  },
  {
    icon: IconShield,
    title: 'Encrypted at rest',
    body: 'Transcripts are encrypted in the database. Nobody but you can open your meetings.',
  },
]

export default function AuthPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { login, register } = useAuth()
  const toast = useToast()

  const isRegister = location.pathname === '/register'

  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const strength = useMemo(() => scorePassword(password), [password])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return

    setError('')
    setSubmitting(true)
    try {
      if (isRegister) {
        await register(email.trim(), fullName.trim(), password)
        toast.success(`Welcome to MeetMind, ${fullName.trim().split(' ')[0]}.`)
      } else {
        await login(email.trim(), password)
        toast.success('Signed in.')
      }
      navigate('/', { replace: true })
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : 'Could not reach the server. Is the backend running on port 8000?'
      setError(message)
    } finally {
      setSubmitting(false)
    }
  }

  const switchMode = () => {
    setError('')
    setPassword('')
    navigate(isRegister ? '/login' : '/register', { replace: true })
  }

  return (
    <div className="auth-shell">
      <aside className="auth-aside">
        <div className="row gap-2">
          <div className="brand-mark" style={{ width: 30, height: 30 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.1" strokeLinecap="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            </svg>
          </div>
          <span style={{ fontSize: 15.5, fontWeight: 650, letterSpacing: '-0.028em' }}>MeetMind</span>
        </div>

        <div className="stack gap-5" style={{ maxWidth: 400 }}>
          <div className="stack gap-3">
            <h1 style={{ fontSize: 33, lineHeight: 1.15, letterSpacing: '-0.035em', fontWeight: 640 }}>
              Stop taking notes.
              <br />
              <span
                style={{
                  background: 'var(--accent-gradient)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                }}
              >
                Start paying attention.
              </span>
            </h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14.5, lineHeight: 1.65 }}>
              Record a meeting and get back a transcript, a summary, and the action items — with every
              claim traceable to the second it was said.
            </p>
          </div>

          <div className="stack">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <div key={title} className="feature-line">
                <div className="feature-icon">
                  <Icon size={13} />
                </div>
                <div className="stack" style={{ gap: 1 }}>
                  <span style={{ fontSize: 13, fontWeight: 570 }}>{title}</span>
                  <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)', lineHeight: 1.55 }}>{body}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="row gap-2" style={{ color: 'var(--text-quaternary)', fontSize: 11.5 }}>
          <IconLock size={12} />
          <span>Runs entirely on your machine. No cloud, no API keys, no data leaves this laptop.</span>
        </div>
      </aside>

      <main className="auth-form-side">
        <div className="auth-card stack gap-5">
          <div className="stack gap-1">
            <h2 style={{ fontSize: 22, letterSpacing: '-0.03em' }}>
              {isRegister ? 'Create your account' : 'Welcome back'}
            </h2>
            <p style={{ color: 'var(--text-tertiary)', fontSize: 13.5 }}>
              {isRegister ? 'Your meetings stay private to this account.' : 'Sign in to your meetings.'}
            </p>
          </div>

          <form className="stack gap-4" onSubmit={handleSubmit} noValidate>
            {isRegister && (
              <div className="field">
                <label className="label" htmlFor="fullName">
                  Full name
                </label>
                <input
                  id="fullName"
                  className="input"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Ashray Sharma"
                  autoComplete="name"
                  required
                  minLength={2}
                  disabled={submitting}
                />
              </div>
            )}

            <div className="field">
              <label className="label" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                className="input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                required
                disabled={submitting}
              />
            </div>

            <div className="field">
              <label className="label" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isRegister ? 'At least 10 characters' : 'Your password'}
                autoComplete={isRegister ? 'new-password' : 'current-password'}
                required
                disabled={submitting}
              />

              {isRegister && password.length > 0 && (
                <div className="stack gap-2" style={{ marginTop: 3 }}>
                  <div className="row gap-1">
                    {[0, 1, 2, 3].map((i) => (
                      <div
                        key={i}
                        style={{
                          height: 2.5,
                          flex: 1,
                          borderRadius: 99,
                          background: i < strength.score ? strength.color : 'var(--surface-3)',
                          transition: 'background 200ms',
                        }}
                      />
                    ))}
                  </div>
                  <span style={{ fontSize: 11.5, color: strength.color, fontWeight: 550 }}>{strength.label}</span>
                </div>
              )}

              {isRegister && (
                <span className="field-hint">
                  Length beats complexity. A short phrase you'll remember is stronger than P@ssw0rd1.
                </span>
              )}
            </div>

            {error && (
              <div
                className="row gap-2"
                style={{
                  padding: '10px 12px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--danger-glow)',
                  border: '1px solid rgba(239,68,68,0.28)',
                  color: '#fca5a5',
                  fontSize: 13,
                  alignItems: 'flex-start',
                  lineHeight: 1.5,
                }}
                role="alert"
              >
                <span style={{ flexShrink: 0, marginTop: 1.5 }}>
                  <IconAlert size={14} />
                </span>
                <span>{error}</span>
              </div>
            )}

            <button className="btn btn-primary btn-lg btn-block" type="submit" disabled={submitting}>
              {submitting ? <span className="spinner" /> : null}
              {submitting
                ? isRegister
                  ? 'Creating account...'
                  : 'Signing in...'
                : isRegister
                  ? 'Create account'
                  : 'Sign in'}
            </button>
          </form>

          <div className="divider" />

          <p style={{ textAlign: 'center', fontSize: 13, color: 'var(--text-tertiary)' }}>
            {isRegister ? 'Already have an account?' : "Don't have an account?"}{' '}
            <button
              onClick={switchMode}
              style={{ color: 'var(--accent-bright)', fontWeight: 550 }}
              type="button"
            >
              {isRegister ? 'Sign in' : 'Create one'}
            </button>
          </p>
        </div>
      </main>
    </div>
  )
}
