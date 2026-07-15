import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { api, type HealthResponse } from '../lib/api'
import { initials } from '../lib/format'
import {
  IconChart,
  IconHome,
  IconList,
  IconLogout,
  IconMenu,
  IconShield,
  IconX,
} from './Icons'

const NAV = [
  { to: '/', label: 'Dashboard', icon: IconHome, end: true },
  { to: '/meetings', label: 'Meetings', icon: IconList, end: false },
  { to: '/analytics', label: 'Analytics', icon: IconChart, end: false },
  { to: '/security', label: 'Security', icon: IconShield, end: false },
]

/**
 * Shows the real state of the local stack. If Ollama is down or a model isn't
 * pulled, this says so with the exact command to fix it, rather than letting the
 * user discover it as a mystery failure three clicks later.
 */
function HealthPill() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    let cancelled = false

    const check = async () => {
      try {
        const res = await api.health()
        if (!cancelled) setHealth(res)
      } catch {
        if (!cancelled) setHealth(null)
      }
    }

    check()
    const timer = window.setInterval(check, 30_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const healthy = health?.status === 'healthy'
  const color = !health ? 'var(--danger)' : healthy ? 'var(--success)' : 'var(--warning)'
  const label = !health ? 'Backend offline' : healthy ? 'All systems local' : 'Degraded'

  const detail = !health
    ? 'The API is not responding. Start it with: uvicorn app.main:app --reload'
    : !health.database
      ? 'PostgreSQL is unreachable. Start it with: .\\scripts\\pg.ps1 start'
      : !health.llm.reachable
        ? `Ollama is unreachable. Start it with: ollama serve`
        : health.llm.detail || 'Transcription and analysis are running on this machine.'

  return (
    <div className="stack gap-2">
      <button
        className="row gap-2"
        onClick={() => setExpanded((v) => !v)}
        style={{
          padding: '7px 9px',
          borderRadius: 7,
          background: 'var(--surface-1)',
          border: '1px solid var(--border-subtle)',
          width: '100%',
          textAlign: 'left',
        }}
        aria-expanded={expanded}
      >
        <span
          className="badge-dot"
          style={{ background: color, boxShadow: `0 0 7px ${color}`, flexShrink: 0 }}
        />
        <span style={{ fontSize: 11.5, fontWeight: 550, color: 'var(--text-secondary)' }} className="grow truncate">
          {label}
        </span>
      </button>

      {expanded && (
        <div
          style={{
            fontSize: 11,
            lineHeight: 1.6,
            color: 'var(--text-tertiary)',
            padding: '9px 10px',
            background: 'var(--surface-1)',
            borderRadius: 7,
            border: '1px solid var(--border-subtle)',
          }}
        >
          <p style={{ marginBottom: health ? 7 : 0 }}>{detail}</p>
          {health && (
            <div className="stack gap-1 mono" style={{ fontSize: 10, color: 'var(--text-quaternary)' }}>
              <span>db · {health.database ? 'connected' : 'down'}</span>
              <span>
                {health.llm.provider} · {health.llm.reachable ? 'ready' : 'down'}
              </span>
              <span>whisper · {health.whisper_model}</span>
              <span>v{health.version}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  // Close the drawer on navigation — leaving it open over the new page is a
  // classic mobile-nav bug.
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  const handleLogout = async () => {
    await logout()
    toast.info('Signed out.')
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar${mobileOpen ? ' open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.1" strokeLinecap="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            </svg>
          </div>
          <div className="stack">
            <span className="brand-name">MeetMind</span>
            <span style={{ fontSize: 9.5, color: 'var(--text-quaternary)', letterSpacing: '0.04em' }}>
              LOCAL-FIRST AI
            </span>
          </div>
          <button
            className="btn btn-icon btn-ghost"
            onClick={() => setMobileOpen(false)}
            style={{ marginLeft: 'auto', display: mobileOpen ? 'grid' : 'none' }}
            aria-label="Close menu"
          >
            <IconX size={15} />
          </button>
        </div>

        <nav className="stack gap-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
              <Icon size={15} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer stack gap-2">
          <HealthPill />

          <div className="row gap-2" style={{ padding: '2px 0' }}>
            <div className="avatar">{initials(user?.full_name ?? '')}</div>
            <div className="stack grow" style={{ minWidth: 0 }}>
              <span
                className="truncate"
                style={{ fontSize: 12.5, fontWeight: 550, letterSpacing: '-0.005em' }}
                title={user?.full_name}
              >
                {user?.full_name}
              </span>
              <span className="truncate" style={{ fontSize: 10.5, color: 'var(--text-quaternary)' }} title={user?.email}>
                {user?.email}
              </span>
            </div>
            <button className="btn btn-icon btn-ghost" onClick={handleLogout} title="Sign out" aria-label="Sign out">
              <IconLogout size={14} />
            </button>
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <div
          onClick={() => setMobileOpen(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 89 }}
          aria-hidden
        />
      )}

      <div className="main-area">
        <button
          className="btn btn-icon btn-secondary"
          onClick={() => setMobileOpen(true)}
          aria-label="Open menu"
          style={{ position: 'fixed', top: 12, left: 12, zIndex: 88 }}
          data-mobile-only
        >
          <IconMenu size={15} />
        </button>
        {children}
      </div>

      <style>{`
        [data-mobile-only] { display: none; }
        @media (max-width: 860px) { [data-mobile-only] { display: grid; } }
      `}</style>
    </div>
  )
}
