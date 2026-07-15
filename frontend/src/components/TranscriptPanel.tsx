import { useEffect, useMemo, useRef, useState } from 'react'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type MeetingDetail, type Segment } from '../lib/api'
import { formatDuration } from '../lib/format'
import { IconCheck, IconEdit, IconSearch, IconUsers, IconX } from './Icons'

interface Props {
  meeting: MeetingDetail
  currentTime: number
  onSeek: (seconds: number) => void
  onSpeakersChanged: () => void
}

/** Highlights matches without innerHTML - the search term is user input. */
function Highlight({ text, term }: { text: string; term: string }) {
  if (!term.trim()) return <>{text}</>

  const lower = text.toLowerCase()
  const needle = term.toLowerCase()
  const parts: React.ReactNode[] = []
  let i = 0
  let key = 0

  while (i < text.length) {
    const found = lower.indexOf(needle, i)
    if (found === -1) {
      parts.push(text.slice(i))
      break
    }
    if (found > i) parts.push(text.slice(i, found))
    parts.push(
      <mark
        key={key++}
        style={{ background: 'rgba(99,102,241,0.3)', color: 'inherit', borderRadius: 3, padding: '0 2px' }}
      >
        {text.slice(found, found + needle.length)}
      </mark>,
    )
    i = found + needle.length
  }
  return <>{parts}</>
}

export default function TranscriptPanel({ meeting, currentTime, onSeek, onSpeakersChanged }: Props) {
  const toast = useToast()
  const [segments, setSegments] = useState<Segment[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [follow, setFollow] = useState(true)
  const [editing, setEditing] = useState<string | null>(null)
  const [nameDraft, setNameDraft] = useState('')

  const activeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false

    ;(async () => {
      try {
        const res = await api.getTranscript(meeting.id)
        if (!cancelled) setSegments(res.segments)
      } catch (err) {
        if (!cancelled) toast.error(err instanceof ApiError ? err.message : 'Could not load the transcript.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [meeting.id, toast])

  const colors = useMemo(
    () => Object.fromEntries(meeting.speakers.map((s) => [s.tag, s.color])),
    [meeting.speakers],
  )
  const names = useMemo(
    () => Object.fromEntries(meeting.speakers.map((s) => [s.tag, s.display_name])),
    [meeting.speakers],
  )

  const activeId = useMemo(() => {
    const seg = segments.find((s) => currentTime >= s.start_time && currentTime < s.end_time)
    return seg?.id ?? null
  }, [segments, currentTime])

  // Keep the spoken line in view while playing, but never fight the user: if
  // they turn follow off (or scroll to read), we stop moving the viewport.
  useEffect(() => {
    if (!follow || !activeId) return
    activeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeId, follow])

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return segments
    return segments.filter(
      (s) => s.text.toLowerCase().includes(q) || (names[s.speaker_tag] ?? '').toLowerCase().includes(q),
    )
  }, [segments, search, names])

  const renameSpeaker = async (speakerId: string) => {
    const trimmed = nameDraft.trim()
    if (!trimmed) {
      setEditing(null)
      return
    }
    try {
      await api.renameSpeaker(meeting.id, speakerId, trimmed)
      setEditing(null)
      onSpeakersChanged()
      toast.success(`Renamed to ${trimmed}. Action items updated too.`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not rename that speaker.')
    }
  }

  if (loading) {
    return (
      <div className="stack gap-2">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="skeleton" style={{ height: 52 }} />
        ))}
      </div>
    )
  }

  if (segments.length === 0) {
    return (
      <div className="card empty">
        <div className="empty-icon">
          <IconUsers size={19} />
        </div>
        <h3>No transcript</h3>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>No speech was found in this recording.</p>
      </div>
    )
  }

  return (
    <div className="stack gap-4">
      <div className="card card-pad stack gap-3">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <span className="eyebrow">Speakers</span>
          <span style={{ fontSize: 11, color: 'var(--text-quaternary)' }}>
            Click a name to correct it
          </span>
        </div>

        <div className="row gap-2 wrap">
          {meeting.speakers.map((s) => (
            <div key={s.id}>
              {editing === s.id ? (
                <div className="row gap-1">
                  <input
                    className="input"
                    style={{ height: 28, fontSize: 12.5, width: 130, padding: '0 8px' }}
                    value={nameDraft}
                    onChange={(e) => setNameDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') renameSpeaker(s.id)
                      if (e.key === 'Escape') setEditing(null)
                    }}
                    autoFocus
                    maxLength={120}
                    aria-label={`Rename ${s.display_name}`}
                  />
                  <button className="btn btn-icon btn-primary" style={{ width: 28, height: 28 }} onClick={() => renameSpeaker(s.id)} aria-label="Save">
                    <IconCheck size={12} />
                  </button>
                  <button className="btn btn-icon btn-ghost" style={{ width: 28, height: 28 }} onClick={() => setEditing(null)} aria-label="Cancel">
                    <IconX size={12} />
                  </button>
                </div>
              ) : (
                <button
                  className="row gap-2"
                  onClick={() => {
                    setEditing(s.id)
                    setNameDraft(s.display_name)
                  }}
                  style={{
                    padding: '5px 10px',
                    borderRadius: 99,
                    background: `${s.color}14`,
                    border: `1px solid ${s.color}38`,
                    color: s.color,
                    fontSize: 12,
                    fontWeight: 570,
                  }}
                  title="Click to rename"
                >
                  <span style={{ width: 6, height: 6, borderRadius: 99, background: s.color }} />
                  {s.display_name}
                  <span style={{ opacity: 0.65, fontWeight: 400 }}>{formatDuration(s.talk_seconds)}</span>
                  <IconEdit size={10} />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="row gap-3 wrap" style={{ justifyContent: 'space-between' }}>
        <div style={{ position: 'relative', flex: '1 1 240px', maxWidth: 340 }}>
          <span
            style={{
              position: 'absolute',
              left: 10,
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--text-quaternary)',
              pointerEvents: 'none',
              display: 'flex',
            }}
          >
            <IconSearch size={13} />
          </span>
          <input
            className="input"
            style={{ paddingLeft: 31, height: 34 }}
            placeholder="Search the transcript..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search transcript"
          />
        </div>

        <div className="row gap-3">
          {search && (
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
              {visible.length} of {segments.length}
            </span>
          )}
          <label className="row gap-2" style={{ cursor: 'pointer', fontSize: 12.5, color: 'var(--text-secondary)' }}>
            <input
              type="checkbox"
              checked={follow}
              onChange={(e) => setFollow(e.target.checked)}
              style={{ accentColor: 'var(--accent)', width: 13, height: 13 }}
            />
            Follow playback
          </label>
        </div>
      </div>

      <div className="card" style={{ padding: 8, maxHeight: 620, overflowY: 'auto' }}>
        {visible.length === 0 ? (
          <div className="empty" style={{ padding: '36px 20px' }}>
            <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
              Nothing in the transcript matches "{search}".
            </span>
          </div>
        ) : (
          visible.map((s) => {
            const isActive = s.id === activeId
            return (
              <div
                key={s.id}
                ref={isActive ? activeRef : null}
                className={`transcript-line${isActive ? ' playing' : ''}`}
                onClick={() => onSeek(s.start_time)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onSeek(s.start_time)
                }}
                title="Jump to this moment"
              >
                <span className="transcript-time">{formatDuration(s.start_time)}</span>
                <div className="stack">
                  <span className="speaker-name" style={{ color: colors[s.speaker_tag] ?? 'var(--text-primary)' }}>
                    {names[s.speaker_tag] ?? s.speaker_name}
                  </span>
                  <span className="transcript-text">
                    <Highlight text={s.text} term={search} />
                  </span>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
