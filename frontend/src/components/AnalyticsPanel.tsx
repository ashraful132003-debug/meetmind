import { useEffect, useState } from 'react'
import { ApiError, api, type MeetingAnalytics } from '../lib/api'
import { formatDuration } from '../lib/format'
import { IconChart } from './Icons'

interface Props {
  meetingId: string
  currentTime: number
  onSeek: (seconds: number) => void
}

function balanceVerdict(score: number): { label: string; color: string; note: string } {
  if (score >= 80)
    return {
      label: 'Well balanced',
      color: 'var(--success)',
      note: 'Everyone got comparable airtime.',
    }
  if (score >= 55)
    return {
      label: 'Somewhat uneven',
      color: 'var(--warning)',
      note: 'One or two people carried most of the conversation.',
    }
  return {
    label: 'Dominated',
    color: 'var(--danger)',
    note: 'One person did most of the talking.',
  }
}

export default function AnalyticsPanel({ meetingId, currentTime, onSeek }: Props) {
  const [data, setData] = useState<MeetingAnalytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    ;(async () => {
      try {
        const res = await api.getAnalytics(meetingId)
        if (!cancelled) setData(res)
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load analytics.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [meetingId])

  if (loading) {
    return (
      <div className="stack gap-3">
        <div className="skeleton" style={{ height: 92 }} />
        <div className="skeleton" style={{ height: 180 }} />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="card empty">
        <div className="empty-icon">
          <IconChart size={19} />
        </div>
        <h3>No analytics available</h3>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>{error || 'This meeting has no analysable content.'}</p>
      </div>
    )
  }

  const verdict = balanceVerdict(data.balance_score)
  const totalDuration = data.duration_seconds || 1
  const cursorPct = Math.min(100, (currentTime / totalDuration) * 100)

  return (
    <div className="stack gap-4">
      <div className="stat-grid">
        <div className="card stat">
          <span className="stat-label">Duration</span>
          <span className="stat-value">{formatDuration(data.duration_seconds)}</span>
          <span className="stat-sub">{data.speaker_count} speakers</span>
        </div>
        <div className="card stat">
          <span className="stat-label">Words spoken</span>
          <span className="stat-value">{data.total_words.toLocaleString()}</span>
          <span className="stat-sub">
            {data.duration_seconds > 0
              ? `${Math.round(data.total_words / (data.duration_seconds / 60))} per minute`
              : '-'}
          </span>
        </div>
        <div className="card stat">
          <span className="stat-label">Participation</span>
          <span className="stat-value" style={{ color: verdict.color }}>
            {data.balance_score}
          </span>
          <span className="stat-sub">{verdict.label}</span>
        </div>
        <div className="card stat">
          <span className="stat-label">Longest stretch</span>
          <span className="stat-value">{formatDuration(data.longest_monologue_seconds)}</span>
          <span className="stat-sub truncate">{data.longest_monologue_speaker ?? '-'}</span>
        </div>
      </div>

      <div className="card card-pad stack gap-4">
        <div className="stack gap-1">
          <span className="eyebrow">Who spoke, and when</span>
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
            Click anywhere on the track to jump to that moment.
          </span>
        </div>

        <div
          className="timeline-track"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect()
            const ratio = (e.clientX - rect.left) / rect.width
            onSeek(Math.max(0, Math.min(1, ratio)) * totalDuration)
          }}
          role="slider"
          tabIndex={0}
          aria-label="Meeting timeline"
          aria-valuemin={0}
          aria-valuemax={Math.round(totalDuration)}
          aria-valuenow={Math.round(currentTime)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowRight') onSeek(Math.min(totalDuration, currentTime + 5))
            if (e.key === 'ArrowLeft') onSeek(Math.max(0, currentTime - 5))
          }}
        >
          {data.timeline.map((b, i) => (
            <div
              key={i}
              className="timeline-block"
              style={{
                left: `${(b.start_time / totalDuration) * 100}%`,
                width: `${Math.max(0.25, ((b.end_time - b.start_time) / totalDuration) * 100)}%`,
                background: b.color,
              }}
              title={`${b.speaker_name} · ${formatDuration(b.start_time)} - ${formatDuration(b.end_time)}`}
            />
          ))}
          <div className="timeline-cursor" style={{ left: `${cursorPct}%` }} />
        </div>

        <div className="row gap-3 wrap">
          {data.speakers.map((s) => (
            <div key={s.tag} className="row gap-2">
              <span style={{ width: 8, height: 8, borderRadius: 3, background: s.color, flexShrink: 0 }} />
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{s.name}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card card-pad stack gap-4">
        <div className="stack gap-1">
          <span className="eyebrow">Talk time</span>
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{verdict.note}</span>
        </div>

        <div className="stack gap-4">
          {data.speakers.map((s) => (
            <div key={s.tag} className="stack gap-2">
              <div className="row gap-2" style={{ justifyContent: 'space-between' }}>
                <div className="row gap-2" style={{ minWidth: 0 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 3, background: s.color, flexShrink: 0 }} />
                  <span className="truncate" style={{ fontSize: 13, fontWeight: 550 }}>
                    {s.name}
                  </span>
                </div>
                <div className="row gap-3" style={{ flexShrink: 0 }}>
                  <span className="mono" style={{ fontSize: 11.5, color: 'var(--text-tertiary)' }}>
                    {formatDuration(s.talk_seconds)}
                  </span>
                  <span className="mono" style={{ fontSize: 11.5, color: 'var(--text-secondary)', minWidth: 40, textAlign: 'right' }}>
                    {s.share_percent}%
                  </span>
                </div>
              </div>

              <div className="share-bar">
                <div className="share-fill" style={{ width: `${s.share_percent}%`, background: s.color }} />
              </div>

              <div className="row gap-3" style={{ fontSize: 11, color: 'var(--text-quaternary)' }}>
                <span>{s.word_count.toLocaleString()} words</span>
                <span className="meta-dot" />
                <span>{s.words_per_minute} wpm</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {data.topics.length > 0 && (
        <div className="card card-pad stack gap-3">
          <span className="eyebrow">Topics discussed</span>
          <div className="topic-chips">
            {data.topics.map((t) => (
              <span key={t} className="chip" style={{ fontSize: 12, padding: '4px 10px' }}>
                {t}
              </span>
            ))}
          </div>
          {data.sentiment && (
            <div className="row gap-2" style={{ marginTop: 2 }}>
              <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Overall tone:</span>
              <span className="badge badge-neutral" style={{ textTransform: 'capitalize' }}>
                {data.sentiment}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
