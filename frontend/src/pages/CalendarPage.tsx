import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type MeetingListItem } from '../lib/api'
import { formatDuration } from '../lib/format'
import { IconCalendar, IconDownload } from '../components/Icons'

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

/** Local YYYY-M-D key so meetings land on the day the user sees, not UTC. */
function dayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

/**
 * A month view of your meetings, plus a one-click export to any real calendar.
 *
 * "Calendar integration" without an OAuth dance: the .ics endpoint emits
 * standards-compliant iCalendar, so every meeting imports straight into Google
 * Calendar, Outlook or Apple Calendar at the time it was recorded.
 */
export default function CalendarPage() {
  const navigate = useNavigate()
  const toast = useToast()

  const [meetings, setMeetings] = useState<MeetingListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)
  const [cursor, setCursor] = useState(() => {
    const n = new Date()
    return { year: n.getFullYear(), month: n.getMonth() }
  })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setMeetings(await api.listMeetings())
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not load your meetings.')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
  }, [load])

  const byDay = useMemo(() => {
    const map = new Map<string, MeetingListItem[]>()
    for (const m of meetings) {
      const d = new Date(m.created_at)
      if (Number.isNaN(d.getTime())) continue
      const key = dayKey(d)
      const list = map.get(key) ?? []
      list.push(m)
      map.set(key, list)
    }
    return map
  }, [meetings])

  const cells = useMemo(() => {
    const first = new Date(cursor.year, cursor.month, 1)
    const startPad = first.getDay()
    const daysInMonth = new Date(cursor.year, cursor.month + 1, 0).getDate()
    const out: (Date | null)[] = []
    for (let i = 0; i < startPad; i++) out.push(null)
    for (let d = 1; d <= daysInMonth; d++) out.push(new Date(cursor.year, cursor.month, d))
    while (out.length % 7 !== 0) out.push(null)
    return out
  }, [cursor])

  const download = async () => {
    setDownloading(true)
    try {
      await api.downloadCalendar()
      toast.success('Calendar file downloaded. Import it into Google, Outlook or Apple Calendar.')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not export the calendar.')
    } finally {
      setDownloading(false)
    }
  }

  const shift = (delta: number) => {
    setCursor((c) => {
      const m = c.month + delta
      return { year: c.year + Math.floor(m / 12), month: ((m % 12) + 12) % 12 }
    })
  }

  const todayKey = dayKey(new Date())

  return (
    <div className="page stack gap-5">
      <div className="page-header" style={{ marginBottom: 0 }}>
        <div className="stack gap-1">
          <span className="eyebrow">Meetings, on a calendar</span>
          <h1>Calendar</h1>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 13.5 }}>
            See your meetings by date, and export them to any calendar app.
          </p>
        </div>
        <button className="btn btn-secondary" onClick={download} disabled={downloading}>
          <IconDownload size={14} /> {downloading ? 'Exporting…' : 'Add to your calendar'}
        </button>
      </div>

      <div className="row gap-3" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="row gap-2">
          <button className="btn btn-icon btn-secondary" onClick={() => shift(-1)} aria-label="Previous month">
            ‹
          </button>
          <button className="btn btn-icon btn-secondary" onClick={() => shift(1)} aria-label="Next month">
            ›
          </button>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              const n = new Date()
              setCursor({ year: n.getFullYear(), month: n.getMonth() })
            }}
          >
            Today
          </button>
        </div>
        <h2 style={{ fontSize: 17 }}>
          {MONTHS[cursor.month]} {cursor.year}
        </h2>
      </div>

      {loading ? (
        <div className="skeleton" style={{ height: 420 }} />
      ) : (
        <div className="card" style={{ padding: 10, overflowX: 'auto' }}>
          <div style={{ minWidth: 640 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 6, marginBottom: 6 }}>
              {WEEKDAYS.map((w) => (
                <div key={w} style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--text-quaternary)', textAlign: 'center', padding: '4px 0' }}>
                  {w.toUpperCase()}
                </div>
              ))}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 6 }}>
              {cells.map((date, i) => {
                if (!date) return <div key={i} />
                const key = dayKey(date)
                const dayMeetings = byDay.get(key) ?? []
                const isToday = key === todayKey
                return (
                  <div
                    key={i}
                    style={{
                      minHeight: 88,
                      borderRadius: 8,
                      border: `1px solid ${isToday ? 'var(--accent)' : 'var(--border-subtle)'}`,
                      background: isToday ? 'var(--accent-soft, rgba(99,102,241,0.06))' : 'var(--surface-1)',
                      padding: 6,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 4,
                    }}
                  >
                    <span style={{ fontSize: 11, fontWeight: 600, color: isToday ? 'var(--accent-bright)' : 'var(--text-tertiary)' }}>
                      {date.getDate()}
                    </span>
                    {dayMeetings.slice(0, 3).map((m) => (
                      <button
                        key={m.id}
                        onClick={() => navigate(`/meetings/${m.id}`)}
                        title={`${m.title} · ${formatDuration(m.duration_seconds)}`}
                        style={{
                          fontSize: 10,
                          textAlign: 'left',
                          padding: '3px 5px',
                          borderRadius: 5,
                          background: 'var(--accent)',
                          color: '#fff',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {m.title}
                      </button>
                    ))}
                    {dayMeetings.length > 3 && (
                      <span style={{ fontSize: 9.5, color: 'var(--text-quaternary)' }}>+{dayMeetings.length - 3} more</span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      <div className="row gap-2" style={{ fontSize: 11.5, color: 'var(--text-tertiary)', alignItems: 'center' }}>
        <IconCalendar size={13} />
        <span>{meetings.length} meeting{meetings.length === 1 ? '' : 's'} total. Click any to open it.</span>
      </div>
    </div>
  )
}
