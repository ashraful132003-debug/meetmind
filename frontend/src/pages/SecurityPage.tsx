import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type HealthResponse, type SessionInfo } from '../lib/api'
import { formatDateTime, formatRelativeTime } from '../lib/format'
import { IconAlert, IconCheckCircle, IconGlobe, IconLock, IconShield } from '../components/Icons'

/** Turns a raw UA string into something a human recognises. Best-effort by
 *  design - the point is "is this me?", not forensic accuracy. */
function describeDevice(ua: string): string {
  if (!ua || ua === 'Unknown device') return 'Unknown device'

  const browser = /Edg\//.test(ua)
    ? 'Edge'
    : /OPR\//.test(ua)
      ? 'Opera'
      : /Chrome\//.test(ua)
        ? 'Chrome'
        : /Firefox\//.test(ua)
          ? 'Firefox'
          : /Safari\//.test(ua)
            ? 'Safari'
            : /python-httpx|curl/i.test(ua)
              ? 'API client'
              : 'Browser'

  const os = /Windows NT 10/.test(ua)
    ? 'Windows'
    : /Windows/.test(ua)
      ? 'Windows'
      : /Android/.test(ua)
        ? 'Android'
        : /iPhone|iPad/.test(ua)
          ? 'iOS'
          : /Mac OS X/.test(ua)
            ? 'macOS'
            : /Linux/.test(ua)
              ? 'Linux'
              : ''

  return os ? `${browser} on ${os}` : browser
}

const GUARANTEES = [
  {
    icon: IconLock,
    title: 'Your audio never leaves this machine',
    body: 'Whisper transcribes locally and Llama summarises locally. There is no cloud API in the request path — you can unplug the internet and the app still works.',
  },
  {
    icon: IconShield,
    title: 'Transcripts are encrypted at rest',
    body: 'Every transcript, summary, action item and chat message is encrypted in the database with AES. Someone who copied the database files could not read a word without the key in your .env.',
  },
  {
    icon: IconCheckCircle,
    title: 'Meetings are yours alone',
    body: 'Ownership is enforced in the SQL query, not checked afterwards. Another account asking for your meeting gets the same 404 as a meeting that never existed — the API will not even confirm it exists.',
  },
  {
    icon: IconGlobe,
    title: 'Passwords use Argon2id',
    body: 'The winner of the Password Hashing Competition, and the current OWASP recommendation. Repeated failed logins lock the account temporarily.',
  },
]

export default function SecurityPage() {
  const { user, logout } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()

  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [revoking, setRevoking] = useState(false)

  const load = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([api.sessions(), api.health().catch(() => null)])
      setSessions(s)
      setHealth(h)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not load your security settings.')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
  }, [load])

  const revokeAll = async () => {
    if (
      !window.confirm(
        'Sign out of every device, including this one?\n\nYou will need to sign in again. Do this if you think someone else has access to your account.',
      )
    )
      return

    setRevoking(true)
    try {
      await api.revokeAllSessions()
      toast.success('All sessions ended.')
      await logout()
      navigate('/login', { replace: true })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not end your sessions.')
      setRevoking(false)
    }
  }

  return (
    <div className="page stack gap-5">
      <div className="stack gap-1">
        <span className="eyebrow">Account</span>
        <h1>Security &amp; privacy</h1>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13.5 }}>
          What protects your meetings, and where you're signed in.
        </p>
      </div>

      <div className="card card-pad stack gap-3">
        <span className="eyebrow">Account</span>
        <div className="row gap-4 wrap">
          <div className="stack gap-1">
            <span style={{ fontSize: 11.5, color: 'var(--text-quaternary)' }}>Name</span>
            <span style={{ fontSize: 13.5 }}>{user?.full_name}</span>
          </div>
          <div className="stack gap-1">
            <span style={{ fontSize: 11.5, color: 'var(--text-quaternary)' }}>Email</span>
            <span style={{ fontSize: 13.5 }}>{user?.email}</span>
          </div>
          <div className="stack gap-1">
            <span style={{ fontSize: 11.5, color: 'var(--text-quaternary)' }}>Member since</span>
            <span style={{ fontSize: 13.5 }}>{user ? formatDateTime(user.created_at) : '-'}</span>
          </div>
        </div>
      </div>

      <div className="card card-pad stack gap-4">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div className="stack gap-1">
            <span className="eyebrow">Active sessions</span>
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
              Every device currently signed in to your account.
            </span>
          </div>
          {sessions.length > 0 && (
            <button className="btn btn-danger btn-sm" onClick={revokeAll} disabled={revoking}>
              {revoking && <span className="spinner" />}
              Sign out everywhere
            </button>
          )}
        </div>

        {loading ? (
          <div className="skeleton" style={{ height: 56 }} />
        ) : sessions.length === 0 ? (
          <p style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>No active sessions found.</p>
        ) : (
          <div className="stack gap-2">
            {sessions.map((s) => (
              <div
                key={s.id}
                className="row gap-3"
                style={{
                  padding: '11px 12px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--surface-1)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <span style={{ color: 'var(--text-quaternary)', flexShrink: 0, display: 'flex' }}>
                  <IconGlobe size={14} />
                </span>
                <div className="stack gap-1 grow" style={{ minWidth: 0 }}>
                  <span className="truncate" style={{ fontSize: 13 }}>
                    {describeDevice(s.user_agent)}
                  </span>
                  <span className="mono" style={{ fontSize: 10.5, color: 'var(--text-quaternary)' }}>
                    {s.ip_address} · last used {formatRelativeTime(s.last_used_at)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card card-pad stack gap-4">
        <span className="eyebrow">How your data is protected</span>
        <div className="stack gap-4">
          {GUARANTEES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="row gap-3" style={{ alignItems: 'flex-start' }}>
              <div className="feature-icon" style={{ marginTop: 1 }}>
                <Icon size={13} />
              </div>
              <div className="stack gap-1">
                <span style={{ fontSize: 13.5, fontWeight: 570 }}>{title}</span>
                <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>{body}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {health && (
        <div className="card card-pad stack gap-3">
          <span className="eyebrow">Where processing happens</span>
          <div className="stack gap-2">
            {[
              { label: 'Database', value: health.database ? 'PostgreSQL on localhost' : 'Unreachable', ok: health.database },
              {
                label: 'Language model',
                value: health.llm.reachable
                  ? `${health.llm.provider} on localhost`
                  : `${health.llm.provider} unreachable`,
                ok: health.llm.reachable,
              },
              { label: 'Speech-to-text', value: `Whisper "${health.whisper_model}" on this GPU`, ok: true },
              { label: 'Third-party services', value: 'None', ok: true },
            ].map((row) => (
              <div
                key={row.label}
                className="row gap-3"
                style={{ padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}
              >
                <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)', width: 132, flexShrink: 0 }}>
                  {row.label}
                </span>
                <span className="grow" style={{ fontSize: 12.5 }}>
                  {row.value}
                </span>
                <span style={{ color: row.ok ? 'var(--success)' : 'var(--danger)', display: 'flex', flexShrink: 0 }}>
                  {row.ok ? <IconCheckCircle size={13} /> : <IconAlert size={13} />}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
