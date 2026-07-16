import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AnalyticsPanel from '../components/AnalyticsPanel'
import AudioPlayer, { type AudioPlayerHandle } from '../components/AudioPlayer'
import ChatPanel from '../components/ChatPanel'
import EmailPanel from '../components/EmailPanel'
import ExportPanel from '../components/ExportPanel'
import SummaryPanel from '../components/SummaryPanel'
import TranscriptPanel from '../components/TranscriptPanel'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type MeetingDetail } from '../lib/api'
import { STATUS_LABELS, formatDateTime, formatDuration, isProcessing, languageName } from '../lib/format'
import {
  IconAlert,
  IconChart,
  IconChat,
  IconEdit,
  IconFile,
  IconMail,
  IconRefresh,
  IconSparkle,
  IconTrash,
  IconUsers,
} from '../components/Icons'

type Tab = 'summary' | 'transcript' | 'ask' | 'analytics' | 'share' | 'export'

const STAGES = ['uploaded', 'transcribing', 'diarizing', 'analyzing', 'indexing'] as const

/** Shows the pipeline as discrete stages driven by real backend status, so the
 *  user can see what is happening rather than watching a bar guess. */
function ProcessingView({ meeting, onRetry }: { meeting: MeetingDetail; onRetry: () => void }) {
  const currentIndex = STAGES.indexOf(meeting.status as (typeof STAGES)[number])

  if (meeting.status === 'failed') {
    return (
      <div className="card empty">
        <div className="empty-icon" style={{ color: 'var(--danger)', borderColor: 'rgba(239,68,68,0.3)' }}>
          <IconAlert size={19} />
        </div>
        <h3>Processing failed</h3>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 440, lineHeight: 1.65 }}>
          {meeting.error_message ?? 'Something went wrong while processing this meeting.'}
        </p>
        <button className="btn btn-primary" onClick={onRetry} style={{ marginTop: 8 }}>
          <IconRefresh size={14} /> Try again
        </button>
      </div>
    )
  }

  return (
    <div className="card card-pad stack gap-5" style={{ padding: 26 }}>
      <div className="stack gap-2">
        <div className="row gap-2">
          <span className="spinner" style={{ color: 'var(--accent-bright)' }} />
          <span style={{ fontSize: 14.5, fontWeight: 560 }}>{meeting.stage_label}</span>
        </div>
        <p style={{ fontSize: 12.5, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
          Running on your GPU. A ten-minute meeting usually takes one to two minutes.
        </p>
      </div>

      <div className="stack gap-2">
        <div className="progress-track" style={{ height: 5 }}>
          <div className="progress-fill active" style={{ width: `${meeting.progress}%` }} />
        </div>
        <span className="mono" style={{ fontSize: 11, color: 'var(--text-quaternary)', alignSelf: 'flex-end' }}>
          {meeting.progress}%
        </span>
      </div>

      <div className="stack gap-3">
        {STAGES.map((stage, i) => {
          const done = currentIndex > i
          const active = currentIndex === i
          return (
            <div key={stage} className="row gap-3">
              <span
                style={{
                  width: 16,
                  height: 16,
                  borderRadius: 99,
                  flexShrink: 0,
                  display: 'grid',
                  placeItems: 'center',
                  background: done ? 'var(--success)' : active ? 'var(--accent)' : 'var(--surface-3)',
                  color: '#fff',
                  transition: 'background 300ms',
                }}
              >
                {done ? (
                  <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : active ? (
                  <span style={{ width: 5, height: 5, borderRadius: 99, background: '#fff' }} />
                ) : null}
              </span>
              <span
                style={{
                  fontSize: 13,
                  color: done || active ? 'var(--text-primary)' : 'var(--text-quaternary)',
                  fontWeight: active ? 550 : 400,
                }}
              >
                {STATUS_LABELS[stage]}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function MeetingDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const toast = useToast()

  const [meeting, setMeeting] = useState<MeetingDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('summary')
  const [currentTime, setCurrentTime] = useState(0)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [notFound, setNotFound] = useState(false)

  const playerRef = useRef<AudioPlayerHandle>(null)

  const load = useCallback(async () => {
    if (!id) return
    try {
      const res = await api.getMeeting(id)
      setMeeting(res)
      setNotFound(false)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true)
      else toast.error(err instanceof ApiError ? err.message : 'Could not load this meeting.')
    } finally {
      setLoading(false)
    }
  }, [id, toast])

  useEffect(() => {
    load()
  }, [load])

  const processing = meeting ? isProcessing(meeting.status) : false

  // Poll while work is in flight, and only then.
  useEffect(() => {
    if (!processing) return
    const timer = window.setInterval(load, 2000)
    return () => window.clearInterval(timer)
  }, [processing, load])

  const seek = useCallback((seconds: number) => {
    playerRef.current?.seekTo(seconds)
  }, [])

  const saveTitle = async () => {
    if (!meeting || !titleDraft.trim() || titleDraft.trim() === meeting.title) {
      setEditingTitle(false)
      return
    }
    try {
      const updated = await api.renameMeeting(meeting.id, titleDraft.trim())
      setMeeting(updated)
      setEditingTitle(false)
      toast.success('Renamed.')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not rename this meeting.')
    }
  }

  const retry = async () => {
    if (!meeting) return
    try {
      await api.reprocess(meeting.id)
      toast.info('Reprocessing started.')
      load()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not restart processing.')
    }
  }

  const remove = async () => {
    if (!meeting) return
    if (
      !window.confirm(
        `Delete "${meeting.title}"?\n\nThe recording, transcript, summary and chat history are all permanently erased. This cannot be undone.`,
      )
    )
      return
    try {
      await api.deleteMeeting(meeting.id)
      toast.success('Meeting deleted.')
      navigate('/meetings')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not delete this meeting.')
    }
  }

  if (loading) {
    return (
      <div className="page stack gap-4">
        <div className="skeleton" style={{ height: 34, width: 300 }} />
        <div className="skeleton" style={{ height: 72 }} />
        <div className="skeleton" style={{ height: 320 }} />
      </div>
    )
  }

  if (notFound || !meeting) {
    return (
      <div className="page">
        <div className="card empty">
          <div className="empty-icon">
            <IconAlert size={19} />
          </div>
          <h3>Meeting not found</h3>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 340, lineHeight: 1.6 }}>
            This meeting doesn't exist, or it belongs to someone else.
          </p>
          <button className="btn btn-secondary" onClick={() => navigate('/meetings')} style={{ marginTop: 6 }}>
            Back to meetings
          </button>
        </div>
      </div>
    )
  }

  const openActions = meeting.action_items.filter((a) => !a.done).length
  const ready = meeting.status === 'ready'

  const TABS: { key: Tab; label: string; icon: typeof IconSparkle; count?: number }[] = [
    { key: 'summary', label: 'Summary', icon: IconSparkle },
    { key: 'transcript', label: 'Transcript', icon: IconUsers },
    { key: 'ask', label: 'Ask', icon: IconChat },
    { key: 'analytics', label: 'Analytics', icon: IconChart },
    { key: 'share', label: 'Email', icon: IconMail },
    { key: 'export', label: 'Export', icon: IconFile },
  ]

  return (
    <div className="page stack gap-4">
      <div className="stack gap-3">
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => navigate('/meetings')}
          style={{ alignSelf: 'flex-start', paddingLeft: 4 }}
        >
          ← Meetings
        </button>

        <div className="page-header" style={{ marginBottom: 0 }}>
          <div className="stack gap-2 grow" style={{ minWidth: 0 }}>
            {editingTitle ? (
              <div className="row gap-2">
                <input
                  className="input"
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') saveTitle()
                    if (e.key === 'Escape') setEditingTitle(false)
                  }}
                  autoFocus
                  maxLength={200}
                  style={{ fontSize: 20, fontWeight: 600, maxWidth: 560 }}
                  aria-label="Meeting title"
                />
                <button className="btn btn-primary btn-sm" onClick={saveTitle}>
                  Save
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => setEditingTitle(false)}>
                  Cancel
                </button>
              </div>
            ) : (
              <div className="row gap-2" style={{ minWidth: 0 }}>
                <h1 className="truncate" title={meeting.title}>
                  {meeting.title}
                </h1>
                <button
                  className="btn btn-icon btn-ghost"
                  onClick={() => {
                    setTitleDraft(meeting.title)
                    setEditingTitle(true)
                  }}
                  title="Rename"
                  aria-label="Rename meeting"
                  style={{ flexShrink: 0 }}
                >
                  <IconEdit size={13} />
                </button>
              </div>
            )}

            <div className="meta-row">
              <span>{formatDateTime(meeting.created_at)}</span>
              {ready && (
                <>
                  <span className="meta-dot" />
                  <span>{formatDuration(meeting.duration_seconds)}</span>
                  <span className="meta-dot" />
                  <span>
                    {meeting.speakers.length} speaker{meeting.speakers.length === 1 ? '' : 's'}
                  </span>
                  {meeting.language && (
                    <>
                      <span className="meta-dot" />
                      <span>{languageName(meeting.language)}</span>
                    </>
                  )}
                  {openActions > 0 && (
                    <>
                      <span className="meta-dot" />
                      <span style={{ color: 'var(--warning)' }}>{openActions} open action</span>
                    </>
                  )}
                </>
              )}
              <span className="meta-dot" />
              <span className="badge badge-neutral" style={{ fontSize: 10 }}>
                {meeting.source === 'recording' ? 'Recorded here' : 'Uploaded'}
              </span>
            </div>
          </div>

          <div className="row gap-2">
            {ready && (
              <button className="btn btn-secondary btn-sm" onClick={retry} title="Re-run the pipeline">
                <IconRefresh size={13} /> Reprocess
              </button>
            )}
            <button className="btn btn-danger btn-sm" onClick={remove}>
              <IconTrash size={13} /> Delete
            </button>
          </div>
        </div>
      </div>

      {meeting.audio_url && (
        <AudioPlayer
          ref={playerRef}
          src={meeting.audio_url}
          duration={meeting.duration_seconds}
          onTimeUpdate={setCurrentTime}
        />
      )}

      {processing || meeting.status === 'failed' ? (
        <ProcessingView meeting={meeting} onRetry={retry} />
      ) : (
        <>
          <div className="tabs">
            {TABS.map(({ key, label, icon: Icon }) => (
              <button key={key} className={`tab${tab === key ? ' active' : ''}`} onClick={() => setTab(key)}>
                <Icon size={13} /> {label}
                {key === 'summary' && meeting.action_items.length > 0 && (
                  <span className="tab-count">{meeting.action_items.length}</span>
                )}
              </button>
            ))}
          </div>

          <div style={{ minHeight: 300 }}>
            {tab === 'summary' && <SummaryPanel meeting={meeting} onChange={setMeeting} onSeek={seek} />}
            {tab === 'transcript' && (
              <TranscriptPanel
                meeting={meeting}
                currentTime={currentTime}
                onSeek={seek}
                onSpeakersChanged={load}
              />
            )}
            {tab === 'ask' && <ChatPanel meetingId={meeting.id} ready={ready} onSeek={seek} />}
            {tab === 'analytics' && (
              <AnalyticsPanel meetingId={meeting.id} currentTime={currentTime} onSeek={seek} />
            )}
            {tab === 'share' && <EmailPanel meetingId={meeting.id} ready={ready} />}
            {tab === 'export' && <ExportPanel meeting={meeting} />}
          </div>
        </>
      )}
    </div>
  )
}
