import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api, type PrepResponse } from '../lib/api'
import Markdown from './Markdown'
import { IconAlert, IconCalendar, IconRefresh, IconSparkle } from './Icons'

/**
 * "Context Before Every Meeting" — a pre-meeting briefing for the follow-up to
 * this one, built from this meeting plus earlier related meetings and their
 * still-open action items.
 *
 * It is generated on demand rather than cached, because it depends on the current
 * state of *other* meetings (an action ticked off elsewhere should change the
 * briefing), so we trigger it with a button instead of on every tab open.
 */
export default function PrepPanel({ meetingId, ready }: { meetingId: string; ready: boolean }) {
  const navigate = useNavigate()
  const [prep, setPrep] = useState<PrepResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const generate = async () => {
    setLoading(true)
    setError(null)
    try {
      setPrep(await api.getMeetingPrep(meetingId))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not prepare a briefing.')
    } finally {
      setLoading(false)
    }
  }

  if (!ready) {
    return (
      <div className="card empty">
        <div className="empty-icon">
          <IconCalendar size={19} />
        </div>
        <h3>Not ready yet</h3>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 360, lineHeight: 1.6 }}>
          A prep briefing can be generated once this meeting has finished processing.
        </p>
      </div>
    )
  }

  if (!prep && !loading) {
    return (
      <div className="card empty">
        <div className="empty-icon" style={{ color: 'var(--accent-bright)' }}>
          <IconSparkle size={19} />
        </div>
        <h3>Walk in prepared</h3>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 420, lineHeight: 1.65 }}>
          Generate a 30-second briefing for your next meeting on this thread — where things stand, what's
          still open, what to watch for, and sharp questions to ask. Built from this meeting and earlier
          related ones.
        </p>
        {error && (
          <p style={{ color: 'var(--danger)', fontSize: 12.5, marginTop: 8, maxWidth: 380 }}>{error}</p>
        )}
        <button className="btn btn-primary" onClick={generate} style={{ marginTop: 10 }}>
          <IconSparkle size={14} /> Prepare briefing
        </button>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="stack gap-3">
        <div className="row gap-2">
          <span className="spinner" style={{ color: 'var(--accent-bright)' }} />
          <span style={{ fontSize: 13.5, color: 'var(--text-secondary)' }}>Reading the thread and drafting your briefing…</span>
        </div>
        <div className="skeleton" style={{ height: 220 }} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="card empty">
        <div className="empty-icon" style={{ color: 'var(--danger)', borderColor: 'rgba(239,68,68,0.3)' }}>
          <IconAlert size={19} />
        </div>
        <h3>Couldn't prepare a briefing</h3>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 380, lineHeight: 1.6 }}>{error}</p>
        <button className="btn btn-secondary" onClick={generate} style={{ marginTop: 6 }}>
          <IconRefresh size={13} /> Try again
        </button>
      </div>
    )
  }

  if (!prep) return null

  return (
    <div className="stack gap-4">
      <div className="row gap-2" style={{ justifyContent: 'space-between' }}>
        <span className="eyebrow">Pre-meeting briefing</span>
        <button className="btn btn-ghost btn-sm" onClick={generate} title="Regenerate">
          <IconRefresh size={12} /> Regenerate
        </button>
      </div>

      <div className="card card-pad">
        <Markdown source={prep.briefing} />
      </div>

      {prep.related_meetings.length > 0 && (
        <div className="stack gap-2">
          <span style={{ fontSize: 11.5, color: 'var(--text-tertiary)', fontWeight: 550 }}>
            Drawn from related meetings
          </span>
          <div className="row gap-2 wrap">
            {prep.related_meetings.map((m) => (
              <button
                key={m.id}
                className="chip"
                onClick={() => navigate(`/meetings/${m.id}`)}
                style={{ cursor: 'pointer' }}
                title="Open this meeting"
              >
                {m.title}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
