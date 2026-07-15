import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type MeetingListItem, type WorkspaceStats } from '../lib/api'
import { formatDuration, formatDurationLong, formatRelativeTime } from '../lib/format'
import { IconChart, IconCheckCircle, IconClock, IconSparkle } from '../components/Icons'

export default function AnalyticsPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [stats, setStats] = useState<WorkspaceStats | null>(null)
  const [meetings, setMeetings] = useState<MeetingListItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([api.getWorkspaceStats(), api.listMeetings()])
      setStats(s)
      setMeetings(m)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not load analytics.')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
  }, [load])

  const ready = meetings.filter((m) => m.status === 'ready')
  const maxDuration = Math.max(1, ...ready.map((m) => m.duration_seconds))
  const maxTopic = Math.max(1, ...(stats?.top_topics ?? []).map((t) => t.count))

  if (loading) {
    return (
      <div className="page stack gap-4">
        <div className="skeleton" style={{ height: 34, width: 220 }} />
        <div className="stat-grid">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton" style={{ height: 92 }} />
          ))}
        </div>
        <div className="skeleton" style={{ height: 260 }} />
      </div>
    )
  }

  return (
    <div className="page stack gap-5">
      <div className="stack gap-1">
        <span className="eyebrow">Insights</span>
        <h1>Analytics</h1>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13.5 }}>
          Across every meeting in your workspace.
        </p>
      </div>

      {ready.length === 0 ? (
        <div className="card empty">
          <div className="empty-icon">
            <IconChart size={19} />
          </div>
          <h3>Nothing to analyse yet</h3>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 340, lineHeight: 1.6 }}>
            Once you've processed a meeting, this page shows how long you spend in meetings, what you talk
            about, and what you commit to.
          </p>
          <button className="btn btn-primary" onClick={() => navigate('/meetings')} style={{ marginTop: 6 }}>
            Go to meetings
          </button>
        </div>
      ) : (
        <>
          <div className="stat-grid">
            <div className="card stat">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="stat-label">Total meeting time</span>
                <span style={{ color: 'var(--text-quaternary)' }}>
                  <IconClock size={14} />
                </span>
              </div>
              <span className="stat-value">{formatDurationLong(stats?.total_duration_seconds ?? 0)}</span>
              <span className="stat-sub">across {ready.length} meetings</span>
            </div>

            <div className="card stat">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="stat-label">Average length</span>
                <span style={{ color: 'var(--text-quaternary)' }}>
                  <IconChart size={14} />
                </span>
              </div>
              <span className="stat-value">
                {formatDurationLong((stats?.total_duration_seconds ?? 0) / Math.max(1, ready.length))}
              </span>
              <span className="stat-sub">per meeting</span>
            </div>

            <div className="card stat">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="stat-label">Action items</span>
                <span style={{ color: 'var(--text-quaternary)' }}>
                  <IconCheckCircle size={14} />
                </span>
              </div>
              <span className="stat-value">{stats?.total_action_items ?? 0}</span>
              <span className="stat-sub">
                {stats?.open_action_items ?? 0} open ·{' '}
                {(stats?.total_action_items ?? 0) - (stats?.open_action_items ?? 0)} done
              </span>
            </div>

            <div className="card stat">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="stat-label">Note-taking avoided</span>
                <span style={{ color: 'var(--text-quaternary)' }}>
                  <IconSparkle size={14} />
                </span>
              </div>
              <span className="stat-value">~{stats?.hours_saved_estimate ?? 0}h</span>
              <span className="stat-sub">est. 40% of meeting time</span>
            </div>
          </div>

          <div className="card card-pad stack gap-4">
            <div className="stack gap-1">
              <span className="eyebrow">Meeting length</span>
              <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                Click any bar to open that meeting.
              </span>
            </div>

            <div className="stack gap-3">
              {ready.slice(0, 10).map((m) => (
                <button
                  key={m.id}
                  className="stack gap-1"
                  onClick={() => navigate(`/meetings/${m.id}`)}
                  style={{ textAlign: 'left', width: '100%' }}
                >
                  <div className="row gap-3" style={{ justifyContent: 'space-between' }}>
                    <span className="truncate" style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
                      {m.title}
                    </span>
                    <span className="mono" style={{ fontSize: 11, color: 'var(--text-quaternary)', flexShrink: 0 }}>
                      {formatDuration(m.duration_seconds)}
                    </span>
                  </div>
                  <div className="share-bar">
                    <div
                      className="share-fill"
                      style={{
                        width: `${(m.duration_seconds / maxDuration) * 100}%`,
                        background: 'var(--accent-gradient)',
                      }}
                    />
                  </div>
                </button>
              ))}
            </div>
          </div>

          {stats && stats.top_topics.length > 0 && (
            <div className="card card-pad stack gap-4">
              <div className="stack gap-1">
                <span className="eyebrow">What you talk about most</span>
                <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                  Topics the AI identified across your meetings.
                </span>
              </div>

              <div className="stack gap-3">
                {stats.top_topics.map((t) => (
                  <div key={t.topic} className="stack gap-1">
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{t.topic}</span>
                      <span className="mono" style={{ fontSize: 11, color: 'var(--text-quaternary)' }}>
                        {t.count}
                      </span>
                    </div>
                    <div className="share-bar">
                      <div
                        className="share-fill"
                        style={{ width: `${(t.count / maxTopic) * 100}%`, background: 'var(--accent)' }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {stats && stats.recent_activity.length > 0 && (
            <div className="card card-pad stack gap-3">
              <span className="eyebrow">Recent activity</span>
              <div className="stack gap-2">
                {stats.recent_activity.map((a) => (
                  <button
                    key={a.id}
                    className="row gap-3"
                    onClick={() => navigate(`/meetings/${a.id}`)}
                    style={{
                      padding: '9px 11px',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--surface-1)',
                      border: '1px solid var(--border-subtle)',
                      textAlign: 'left',
                      width: '100%',
                    }}
                  >
                    <span className="truncate grow" style={{ fontSize: 12.5 }}>
                      {a.title}
                    </span>
                    <span className="mono" style={{ fontSize: 11, color: 'var(--text-quaternary)', flexShrink: 0 }}>
                      {formatDuration(a.duration_seconds)}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-quaternary)', flexShrink: 0 }}>
                      {formatRelativeTime(a.created_at)}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
