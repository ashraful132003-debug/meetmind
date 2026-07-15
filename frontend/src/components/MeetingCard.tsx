import type { MeetingListItem } from '../lib/api'
import { STATUS_LABELS, formatDuration, formatRelativeTime, isProcessing, languageName } from '../lib/format'
import { IconAlert, IconCheckCircle, IconClock, IconUsers } from './Icons'

function StatusBadge({ meeting }: { meeting: MeetingListItem }) {
  if (meeting.status === 'ready') {
    return (
      <span className="badge badge-success">
        <span className="badge-dot" /> Ready
      </span>
    )
  }
  if (meeting.status === 'failed') {
    return (
      <span className="badge badge-danger">
        <IconAlert size={10} /> Failed
      </span>
    )
  }
  return (
    <span className="badge badge-accent">
      <span className="spinner" style={{ width: 8, height: 8, borderWidth: 1.3 }} />
      {STATUS_LABELS[meeting.status] ?? meeting.status}
    </span>
  )
}

export default function MeetingCard({
  meeting,
  onClick,
}: {
  meeting: MeetingListItem
  onClick: () => void
}) {
  const processing = isProcessing(meeting.status)

  return (
    <article
      className="card card-hover meeting-card"
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={`Open meeting ${meeting.title}`}
    >
      <div className="row gap-2" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <StatusBadge meeting={meeting} />
        <span style={{ fontSize: 11, color: 'var(--text-quaternary)', whiteSpace: 'nowrap' }}>
          {formatRelativeTime(meeting.created_at)}
        </span>
      </div>

      <h3 className="meeting-title grow">{meeting.title}</h3>

      {processing ? (
        <div className="stack gap-2">
          <div className="row" style={{ justifyContent: 'space-between', fontSize: 11.5 }}>
            <span style={{ color: 'var(--text-tertiary)' }}>{meeting.stage_label}</span>
            <span className="mono" style={{ color: 'var(--text-quaternary)' }}>
              {meeting.progress}%
            </span>
          </div>
          <div className="progress-track">
            <div className="progress-fill active" style={{ width: `${meeting.progress}%` }} />
          </div>
        </div>
      ) : meeting.status === 'failed' ? (
        <p
          style={{
            fontSize: 12,
            color: '#fca5a5',
            lineHeight: 1.5,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {meeting.error_message ?? 'Processing failed.'}
        </p>
      ) : (
        <>
          {meeting.topics && meeting.topics.length > 0 && (
            <div className="topic-chips">
              {meeting.topics.slice(0, 3).map((t) => (
                <span key={t} className="chip">
                  {t}
                </span>
              ))}
              {meeting.topics.length > 3 && <span className="chip">+{meeting.topics.length - 3}</span>}
            </div>
          )}

          <div className="meta-row" style={{ marginTop: 'auto' }}>
            <span className="row gap-1">
              <IconClock size={11} /> {formatDuration(meeting.duration_seconds)}
            </span>
            <span className="meta-dot" />
            <span className="row gap-1">
              <IconUsers size={11} /> {meeting.speaker_count}
            </span>
            {meeting.action_item_count > 0 && (
              <>
                <span className="meta-dot" />
                <span
                  className="row gap-1"
                  style={{ color: meeting.open_action_count > 0 ? 'var(--warning)' : 'var(--success)' }}
                >
                  <IconCheckCircle size={11} />
                  {meeting.open_action_count > 0
                    ? `${meeting.open_action_count} open`
                    : `${meeting.action_item_count} done`}
                </span>
              </>
            )}
            {meeting.language && (
              <>
                <span className="meta-dot" />
                <span>{languageName(meeting.language)}</span>
              </>
            )}
          </div>
        </>
      )}
    </article>
  )
}
