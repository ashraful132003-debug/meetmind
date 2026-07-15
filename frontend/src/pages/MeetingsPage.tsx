import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import MeetingCard from '../components/MeetingCard'
import NewMeetingModal from '../components/NewMeetingModal'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type MeetingListItem } from '../lib/api'
import { isProcessing } from '../lib/format'
import { IconMic, IconRefresh, IconSearch, IconX } from '../components/Icons'

type Filter = 'all' | 'ready' | 'processing' | 'failed'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'ready', label: 'Ready' },
  { key: 'processing', label: 'Processing' },
  { key: 'failed', label: 'Failed' },
]

export default function MeetingsPage() {
  const navigate = useNavigate()
  const toast = useToast()

  const [meetings, setMeetings] = useState<MeetingListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [showModal, setShowModal] = useState(false)

  const load = useCallback(async () => {
    try {
      setMeetings(await api.listMeetings())
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not load meetings.')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
  }, [load])

  const anyProcessing = meetings.some((m) => isProcessing(m.status))

  useEffect(() => {
    if (!anyProcessing) return
    const timer = window.setInterval(load, 2500)
    return () => window.clearInterval(timer)
  }, [anyProcessing, load])

  /**
   * Filtering happens client-side deliberately. The server can only search
   * titles (transcripts are encrypted at rest and genuinely unsearchable in SQL),
   * and the list is small enough that filtering here is instant and offline.
   */
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    return meetings.filter((m) => {
      const matchesFilter =
        filter === 'all'
          ? true
          : filter === 'processing'
            ? isProcessing(m.status)
            : m.status === filter

      if (!matchesFilter) return false
      if (!q) return true

      return (
        m.title.toLowerCase().includes(q) ||
        (m.topics ?? []).some((t) => t.toLowerCase().includes(q))
      )
    })
  }, [meetings, search, filter])

  const counts = useMemo(
    () => ({
      all: meetings.length,
      ready: meetings.filter((m) => m.status === 'ready').length,
      processing: meetings.filter((m) => isProcessing(m.status)).length,
      failed: meetings.filter((m) => m.status === 'failed').length,
    }),
    [meetings],
  )

  return (
    <div className="page stack gap-5">
      <div className="page-header">
        <div className="stack gap-1">
          <span className="eyebrow">Library</span>
          <h1>Meetings</h1>
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

      <div className="row gap-3 wrap" style={{ justifyContent: 'space-between' }}>
        <div className="tabs" style={{ border: 'none' }}>
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              className={`tab${filter === key ? ' active' : ''}`}
              onClick={() => setFilter(key)}
            >
              {label}
              {counts[key] > 0 && <span className="tab-count">{counts[key]}</span>}
            </button>
          ))}
        </div>

        <div style={{ position: 'relative', minWidth: 230, flex: '0 1 300px' }}>
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
            style={{ paddingLeft: 31, paddingRight: search ? 31 : 12, height: 34 }}
            placeholder="Search titles and topics..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search meetings"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              style={{
                position: 'absolute',
                right: 8,
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-quaternary)',
                display: 'flex',
                padding: 2,
              }}
              aria-label="Clear search"
            >
              <IconX size={12} />
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="meeting-grid">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="skeleton" style={{ height: 152 }} />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <div className="card empty">
          <div className="empty-icon">
            <IconSearch size={19} />
          </div>
          <h3>{meetings.length === 0 ? 'No meetings yet' : 'Nothing matches'}</h3>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 340, lineHeight: 1.6 }}>
            {meetings.length === 0
              ? 'Record or upload your first meeting to get started.'
              : search
                ? `No meeting matches "${search}"${filter !== 'all' ? ` in ${filter}` : ''}.`
                : `You have no ${filter} meetings.`}
          </p>
          {meetings.length === 0 ? (
            <button className="btn btn-primary" onClick={() => setShowModal(true)} style={{ marginTop: 6 }}>
              <IconMic size={14} /> New meeting
            </button>
          ) : (
            (search || filter !== 'all') && (
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setSearch('')
                  setFilter('all')
                }}
                style={{ marginTop: 6 }}
              >
                Clear filters
              </button>
            )
          )}
        </div>
      ) : (
        <div className="meeting-grid">
          {visible.map((m) => (
            <MeetingCard key={m.id} meeting={m} onClick={() => navigate(`/meetings/${m.id}`)} />
          ))}
        </div>
      )}

      {showModal && (
        <NewMeetingModal
          onClose={() => setShowModal(false)}
          onCreated={(id) => {
            setShowModal(false)
            toast.info('Processing started.')
            navigate(`/meetings/${id}`)
          }}
        />
      )}
    </div>
  )
}
