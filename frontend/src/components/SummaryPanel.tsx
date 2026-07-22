import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type MeetingDetail } from '../lib/api'
import { formatDuration } from '../lib/format'
import Markdown from './Markdown'
import { IconCheck, IconCircle, IconSparkle } from './Icons'

const PRIORITY_STYLE: Record<string, { bg: string; fg: string }> = {
  high: { bg: 'rgba(239,68,68,0.12)', fg: '#f87171' },
  medium: { bg: 'rgba(245,158,11,0.12)', fg: '#fbbf24' },
  low: { bg: 'rgba(16,185,129,0.12)', fg: '#34d399' },
}

interface Props {
  meeting: MeetingDetail
  onChange: (m: MeetingDetail) => void
  onSeek: (seconds: number) => void
}

export default function SummaryPanel({ meeting, onChange, onSeek }: Props) {
  const toast = useToast()
  const [busy, setBusy] = useState<string | null>(null)

  const toggle = async (actionId: string, done: boolean) => {
    setBusy(actionId)

    // Optimistic: ticking a checkbox should feel instant, not wait on a round-trip.
    const previous = meeting.action_items
    onChange({
      ...meeting,
      action_items: meeting.action_items.map((a) => (a.id === actionId ? { ...a, done } : a)),
    })

    try {
      await api.toggleAction(meeting.id, actionId, done)
    } catch (err) {
      onChange({ ...meeting, action_items: previous }) // roll back
      toast.error(err instanceof ApiError ? err.message : 'Could not update that action item.')
    } finally {
      setBusy(null)
    }
  }

  const open = meeting.action_items.filter((a) => !a.done)
  const done = meeting.action_items.filter((a) => a.done)

  return (
    <div className="stack gap-4">
      {meeting.topics && meeting.topics.length > 0 && (
        <div className="row gap-2 wrap">
          {meeting.topics.map((t) => (
            <span key={t} className="chip" style={{ fontSize: 12, padding: '4px 10px' }}>
              {t}
            </span>
          ))}
          {meeting.sentiment && (
            <span className="badge badge-neutral" style={{ textTransform: 'capitalize' }}>
              {meeting.sentiment} tone
            </span>
          )}
        </div>
      )}

      <div className="card card-pad">
        {meeting.summary ? (
          <Markdown source={meeting.summary} />
        ) : (
          <p style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>No summary was generated for this meeting.</p>
        )}
      </div>

      <div className="card card-pad stack gap-4">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div className="stack gap-1">
            <span className="eyebrow">Action items</span>
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
              {meeting.action_items.length === 0
                ? 'None were committed to in this meeting.'
                : `${open.length} open · ${done.length} done`}
            </span>
          </div>
          {meeting.action_items.length > 0 && (
            <span className="badge badge-accent">
              <IconSparkle size={10} /> Extracted by AI
            </span>
          )}
        </div>

        {meeting.action_items.length === 0 ? (
          <p style={{ fontSize: 13, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
            Nothing was extracted. That's a real answer, not a failure — the model is instructed never to
            invent commitments that weren't made.
          </p>
        ) : (
          <div className="stack gap-2">
            {[...open, ...done].map((item) => {
              const style = PRIORITY_STYLE[item.priority] ?? PRIORITY_STYLE.medium!
              return (
                <div
                  key={item.id}
                  className="row gap-3"
                  style={{
                    padding: '11px 12px',
                    borderRadius: 'var(--radius-sm)',
                    background: item.done ? 'transparent' : 'var(--surface-1)',
                    border: '1px solid var(--border-subtle)',
                    alignItems: 'flex-start',
                    opacity: item.done ? 0.55 : 1,
                    transition: 'opacity 200ms, background 200ms',
                  }}
                >
                  <button
                    onClick={() => toggle(item.id, !item.done)}
                    disabled={busy === item.id}
                    style={{
                      color: item.done ? 'var(--success)' : 'var(--text-quaternary)',
                      flexShrink: 0,
                      marginTop: 1,
                      display: 'flex',
                    }}
                    aria-label={item.done ? 'Mark as not done' : 'Mark as done'}
                    title={item.done ? 'Mark as not done' : 'Mark as done'}
                  >
                    {item.done ? <IconCheck size={15} /> : <IconCircle size={15} />}
                  </button>

                  <div className="stack gap-2 grow" style={{ minWidth: 0 }}>
                    <span
                      style={{
                        fontSize: 13.5,
                        lineHeight: 1.55,
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
                        <span className="badge badge-neutral" style={{ fontSize: 10.5 }}>
                          due {item.due_text}
                        </span>
                      )}
                      <span
                        className="badge"
                        style={{ background: style.bg, color: style.fg, fontSize: 10.5, borderColor: 'transparent' }}
                      >
                        {item.priority}
                      </span>
                      {item.quote_time !== null && (
                        <button
                          className="mono"
                          onClick={() => onSeek(item.quote_time!)}
                          style={{ fontSize: 10.5, color: 'var(--accent-bright)' }}
                          title="Hear this being said"
                        >
                          {formatDuration(item.quote_time)} ↗
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
