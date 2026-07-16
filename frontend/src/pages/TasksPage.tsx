import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type ActionBoard } from '../lib/api'
import { formatRelativeTime } from '../lib/format'
import { IconCheck, IconCheckCircle, IconCircle, IconRefresh, IconSparkle } from '../components/Icons'

type Show = 'open' | 'done' | 'all'

const PRIORITY_STYLE: Record<string, { bg: string; fg: string }> = {
  high: { bg: 'rgba(239,68,68,0.12)', fg: '#f87171' },
  medium: { bg: 'rgba(245,158,11,0.12)', fg: '#fbbf24' },
  low: { bg: 'rgba(16,185,129,0.12)', fg: '#34d399' },
}

/**
 * Every action item from every meeting, in one place.
 *
 * The per-meeting list answers "what came out of this meeting". This answers
 * "what do I owe anyone" — which is the question that makes someone open the app
 * on a Monday morning.
 */
export default function TasksPage() {
  const toast = useToast()
  const navigate = useNavigate()

  const [board, setBoard] = useState<ActionBoard | null>(null)
  const [loading, setLoading] = useState(true)
  const [show, setShow] = useState<Show>('open')
  const [owner, setOwner] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setBoard(await api.getActionBoard(show, owner))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not load your tasks.')
    } finally {
      setLoading(false)
    }
  }, [show, owner, toast])

  useEffect(() => {
    load()
  }, [load])

  const toggle = async (meetingId: string, actionId: string, done: boolean) => {
    setBusy(actionId)

    // Optimistic — ticking a box should feel instant.
    setBoard((prev) =>
      prev
        ? {
            ...prev,
            items: prev.items.map((i) => (i.id === actionId ? { ...i, done } : i)),
            open_count: prev.open_count + (done ? -1 : 1),
            done_count: prev.done_count + (done ? 1 : -1),
          }
        : prev,
    )

    try {
      await api.toggleAction(meetingId, actionId, done)
      // Refetch when filtering by state: the item may no longer belong in view.
      if (show !== 'all') load()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not update that task.')
      load()
    } finally {
      setBusy(null)
    }
  }

  const FILTERS: { key: Show; label: string; count?: number }[] = [
    { key: 'open', label: 'Open', count: board?.open_count },
    { key: 'done', label: 'Done', count: board?.done_count },
    { key: 'all', label: 'All', count: board?.total },
  ]

  return (
    <div className="page stack gap-5">
      <div className="page-header" style={{ marginBottom: 0 }}>
        <div className="stack gap-1">
          <span className="eyebrow">Everything you owe</span>
          <h1>Tasks</h1>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 13.5 }}>
            Every action item the AI found, across every meeting.
          </p>
        </div>
        <button className="btn btn-secondary" onClick={load} disabled={loading} title="Refresh">
          <IconRefresh size={14} />
        </button>
      </div>

      <div className="row gap-3 wrap" style={{ justifyContent: 'space-between' }}>
        <div className="tabs" style={{ border: 'none' }}>
          {FILTERS.map(({ key, label, count }) => (
            <button
              key={key}
              className={`tab${show === key ? ' active' : ''}`}
              onClick={() => setShow(key)}
            >
              {label}
              {count !== undefined && count > 0 && <span className="tab-count">{count}</span>}
            </button>
          ))}
        </div>

        {board && board.owners.length > 0 && (
          <div className="row gap-2 wrap">
            <button
              className={`chip${!owner ? ' active' : ''}`}
              onClick={() => setOwner('')}
              style={{
                cursor: 'pointer',
                borderColor: !owner ? 'var(--accent)' : undefined,
                color: !owner ? 'var(--accent-bright)' : undefined,
              }}
            >
              Everyone
            </button>
            {board.owners.slice(0, 6).map((o) => (
              <button
                key={o.name}
                className="chip"
                onClick={() => setOwner(owner === o.name ? '' : o.name)}
                style={{
                  cursor: 'pointer',
                  borderColor: owner === o.name ? 'var(--accent)' : undefined,
                  color: owner === o.name ? 'var(--accent-bright)' : undefined,
                }}
              >
                {o.name} <span style={{ opacity: 0.6 }}>{o.open}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <div className="stack gap-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton" style={{ height: 68 }} />
          ))}
        </div>
      ) : !board || board.items.length === 0 ? (
        <div className="card empty">
          <div className="empty-icon">
            <IconCheckCircle size={19} />
          </div>
          <h3>
            {board?.total === 0
              ? 'No tasks yet'
              : show === 'open'
                ? 'Nothing open'
                : `No ${show} tasks`}
          </h3>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 360, lineHeight: 1.6 }}>
            {board?.total === 0
              ? 'Process a meeting and any commitments made in it will show up here automatically.'
              : owner
                ? `${owner} has nothing ${show}.`
                : 'Everything is done. Genuinely.'}
          </p>
          {board?.total === 0 && (
            <button className="btn btn-primary" onClick={() => navigate('/meetings')} style={{ marginTop: 6 }}>
              Go to meetings
            </button>
          )}
        </div>
      ) : (
        <div className="stack gap-2">
          {board.items.map((item) => {
            const style = PRIORITY_STYLE[item.priority] ?? PRIORITY_STYLE.medium!
            return (
              <div
                key={item.id}
                className="card card-hover row gap-3"
                style={{
                  padding: '13px 15px',
                  alignItems: 'flex-start',
                  opacity: item.done ? 0.55 : 1,
                  transition: 'opacity 200ms',
                }}
              >
                <button
                  onClick={() => toggle(item.meeting_id, item.id, !item.done)}
                  disabled={busy === item.id}
                  style={{
                    color: item.done ? 'var(--success)' : 'var(--text-quaternary)',
                    flexShrink: 0,
                    marginTop: 2,
                    display: 'flex',
                  }}
                  aria-label={item.done ? 'Mark as not done' : 'Mark as done'}
                >
                  {item.done ? <IconCheck size={16} /> : <IconCircle size={16} />}
                </button>

                <div className="stack gap-2 grow" style={{ minWidth: 0 }}>
                  <span
                    style={{
                      fontSize: 14,
                      lineHeight: 1.5,
                      textDecoration: item.done ? 'line-through' : 'none',
                    }}
                  >
                    {item.task}
                  </span>

                  <div className="row gap-2 wrap" style={{ fontSize: 11 }}>
                    <span className="badge badge-neutral" style={{ fontSize: 10.5 }}>
                      {item.owner_label}
                    </span>
                    {item.due_text && (
                      <span className="badge badge-warning" style={{ fontSize: 10.5 }}>
                        due {item.due_text}
                      </span>
                    )}
                    <span
                      className="badge"
                      style={{ background: style.bg, color: style.fg, fontSize: 10.5, borderColor: 'transparent' }}
                    >
                      {item.priority}
                    </span>
                    <button
                      onClick={() => navigate(`/meetings/${item.meeting_id}`)}
                      style={{
                        fontSize: 10.5,
                        color: 'var(--text-tertiary)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                      }}
                      title="Open the meeting this came from"
                    >
                      <IconSparkle size={9} />
                      <span
                        className="truncate"
                        style={{ maxWidth: 200, textDecoration: 'underline', textUnderlineOffset: 2 }}
                      >
                        {item.meeting_title}
                      </span>
                      <span style={{ color: 'var(--text-quaternary)' }}>
                        {formatRelativeTime(item.meeting_date)}
                      </span>
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
