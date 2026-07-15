import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import NewMeetingModal from '../components/NewMeetingModal'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type MeetingListItem, type WorkspaceStats } from '../lib/api'
import { formatDurationLong, isProcessing } from '../lib/format'
import MeetingCard from '../components/MeetingCard'
import {
  IconCheckCircle,
  IconClock,
  IconLock,
  IconMic,
  IconRefresh,
  IconSparkle,
} from '../components/Icons'

function greeting(): string {
  const h = new Date().getHours()
  if (h < 5) return 'Still up'
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

function StatTile({
  label,
  value,
  sub,
  icon,
}: {
  label: string
  value: string
  sub?: string
  icon: React.ReactNode
}) {
  return (
    <div className="card stat">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="stat-label">{label}</span>
        <span style={{ color: 'var(--text-quaternary)' }}>{icon}</span>
      </div>
      <span className="stat-value">{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()

  const [stats, setStats] = useState<WorkspaceStats | null>(null)
  const [meetings, setMeetings] = useState<MeetingListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([api.getWorkspaceStats(), api.listMeetings()])
      setStats(s)
      setMeetings(m)
      setError('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load your workspace.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  /**
   * Poll only while something is actually processing, and stop the moment it
   * isn't. A permanent interval would hammer the API for no reason and keep the
   * laptop awake.
   */
  const anyProcessing = meetings.some((m) => isProcessing(m.status))

  useEffect(() => {
    if (!anyProcessing) return
    const timer = window.setInterval(load, 2500)
    return () => window.clearInterval(timer)
  }, [anyProcessing, load])

  const firstName = user?.full_name.trim().split(' ')[0] ?? ''
  const recent = meetings.slice(0, 6)

  return (
    <div className="page stack gap-6">
      <div className="page-header">
        <div className="stack gap-1">
          <span className="eyebrow">{greeting()}</span>
          <h1>{firstName ? `${firstName}'s workspace` : 'Your workspace'}</h1>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 13.5 }}>
            {loading
              ? 'Loading...'
              : stats?.total_meetings === 0
                ? 'Record your first meeting to see it transcribed and summarised.'
                : `${stats?.total_meetings} meeting${stats?.total_meetings === 1 ? '' : 's'} · everything processed on this machine`}
          </p>
        </div>

        <div className="row gap-2">
          <button className="btn btn-secondary" onClick={load} disabled={loading} title="Refresh">
            <IconRefresh size={14} />
          </button>
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            <IconMic size={14} /> New meeting
          </button>
        </div>
      </div>

      {error && (
        <div
          className="card card-pad"
          style={{ borderColor: 'rgba(239,68,68,0.3)', background: 'var(--danger-glow)' }}
          role="alert"
        >
          <span style={{ color: '#fca5a5', fontSize: 13 }}>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="stat-grid">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton" style={{ height: 92 }} />
          ))}
        </div>
      ) : (
        <div className="stat-grid">
          <StatTile
            label="Meetings"
            value={String(stats?.total_meetings ?? 0)}
            sub={
              stats?.processing_meetings
                ? `${stats.processing_meetings} processing now`
                : `${stats?.ready_meetings ?? 0} ready`
            }
            icon={<IconSparkle size={14} />}
          />
          <StatTile
            label="Time recorded"
            value={formatDurationLong(stats?.total_duration_seconds ?? 0)}
            sub={`~${stats?.hours_saved_estimate ?? 0}h of note-taking avoided`}
            icon={<IconClock size={14} />}
          />
          <StatTile
            label="Action items"
            value={String(stats?.total_action_items ?? 0)}
            sub={
              stats?.open_action_items
                ? `${stats.open_action_items} still open`
                : stats?.total_action_items
                  ? 'All done'
                  : 'None yet'
            }
            icon={<IconCheckCircle size={14} />}
          />
          <StatTile
            label="Data sent to cloud"
            value="0 bytes"
            sub="Whisper and Llama run locally"
            icon={<IconLock size={14} />}
          />
        </div>
      )}

      {!loading && stats && stats.top_topics.length > 0 && (
        <div className="card card-pad stack gap-3">
          <span className="eyebrow">What you've been discussing</span>
          <div className="topic-chips">
            {stats.top_topics.map((t) => (
              <span key={t.topic} className="chip" style={{ fontSize: 12, padding: '4px 10px' }}>
                {t.topic}
                {t.count > 1 && (
                  <span style={{ color: 'var(--text-quaternary)', marginLeft: 5 }}>×{t.count}</span>
                )}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="stack gap-3">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ fontSize: 15.5 }}>Recent meetings</h2>
          {meetings.length > 6 && (
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/meetings')}>
              View all {meetings.length}
            </button>
          )}
        </div>

        {loading ? (
          <div className="meeting-grid">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton" style={{ height: 152 }} />
            ))}
          </div>
        ) : recent.length === 0 ? (
          <div className="card empty">
            <div className="empty-icon">
              <IconMic size={19} />
            </div>
            <h3>No meetings yet</h3>
            <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 380, lineHeight: 1.6 }}>
              Record a meeting or upload an audio file. It'll be transcribed, summarised, and turned into
              action items — without leaving this laptop.
            </p>
            <button className="btn btn-primary" onClick={() => setShowModal(true)} style={{ marginTop: 6 }}>
              <IconMic size={14} /> Record your first meeting
            </button>
          </div>
        ) : (
          <div className="meeting-grid">
            {recent.map((m) => (
              <MeetingCard key={m.id} meeting={m} onClick={() => navigate(`/meetings/${m.id}`)} />
            ))}
          </div>
        )}
      </div>

      {showModal && (
        <NewMeetingModal
          onClose={() => setShowModal(false)}
          onCreated={(id) => {
            setShowModal(false)
            toast.info('Processing started. This takes a couple of minutes.')
            navigate(`/meetings/${id}`)
          }}
        />
      )}
    </div>
  )
}
