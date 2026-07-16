import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type MemoryMessage } from '../lib/api'
import { formatRelativeTime } from '../lib/format'
import {
  IconAlert,
  IconClock,
  IconSend,
  IconShield,
  IconSparkle,
  IconTrash,
} from '../components/Icons'

/**
 * Ask questions across every meeting, not just one.
 *
 * The distinction from per-meeting chat is the whole point: this answers
 * "what did the client say about pricing last month" — where the user does not
 * remember which meeting it was in, which is the question people actually have.
 */
export default function MemoryPage() {
  const toast = useToast()
  const navigate = useNavigate()

  const [messages, setMessages] = useState<MemoryMessage[]>([])
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [question, setQuestion] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)

  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const load = useCallback(async () => {
    try {
      const history = await api.getMemoryHistory()
      setMessages(history)
      if (history.length === 0) {
        setSuggestions(await api.getMemorySuggestions().catch(() => []))
      }
    } catch {
      /* an empty history is a fine fallback */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  const ask = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || sending) return

    setQuestion('')
    setSuggestions([])
    setSending(true)

    const optimistic: MemoryMessage = {
      id: `pending-${Date.now()}`,
      role: 'user',
      content: trimmed,
      citations: null,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, optimistic])

    try {
      const answer = await api.askMemory(trimmed)
      setMessages((prev) => [...prev.filter((m) => m.id !== optimistic.id), optimistic, answer])
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id))
      setQuestion(trimmed)
      toast.error(err instanceof ApiError ? err.message : 'Could not search your meetings.')
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  const clear = async () => {
    if (!window.confirm('Clear this conversation? Your meetings are not affected.')) return
    try {
      await api.clearMemory()
      setMessages([])
      setSuggestions(await api.getMemorySuggestions().catch(() => []))
      toast.success('Conversation cleared.')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not clear the conversation.')
    }
  }

  return (
    <div className="page stack gap-4">
      <div className="page-header" style={{ marginBottom: 0 }}>
        <div className="stack gap-1">
          <span className="eyebrow">Across every meeting</span>
          <h1>Ask your meetings</h1>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 13.5, maxWidth: 620, lineHeight: 1.6 }}>
            You don't have to remember which meeting it was in. Ask what the client said about
            pricing, or what anyone committed to last week.
          </p>
        </div>
        {messages.length > 0 && (
          <button className="btn btn-ghost btn-sm" onClick={clear}>
            <IconTrash size={13} /> Clear
          </button>
        )}
      </div>

      <div
        className="card stack"
        style={{ height: 'clamp(460px, 66vh, 720px)', overflow: 'hidden' }}
      >
        <div className="chat-scroll" ref={scrollRef}>
          {loading ? (
            <div className="stack gap-3">
              <div className="skeleton" style={{ height: 40, width: '60%' }} />
              <div className="skeleton" style={{ height: 70, width: '82%', alignSelf: 'flex-end' }} />
            </div>
          ) : messages.length === 0 ? (
            <div className="stack gap-4" style={{ margin: 'auto 0', alignItems: 'center', textAlign: 'center' }}>
              <div className="empty-icon">
                <IconSparkle size={19} />
              </div>
              <div className="stack gap-1">
                <span style={{ fontSize: 14.5, fontWeight: 550 }}>Your meeting memory</span>
                <span
                  style={{ fontSize: 12.5, color: 'var(--text-tertiary)', maxWidth: 360, lineHeight: 1.6 }}
                >
                  Every answer names the meeting it came from, and every quote is checked against
                  that meeting's transcript before you see it.
                </span>
              </div>

              {suggestions.length > 0 && (
                <div className="stack gap-2" style={{ width: '100%', maxWidth: 420 }}>
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      className="citation"
                      onClick={() => ask(s)}
                      style={{ justifyContent: 'flex-start', fontSize: 12.5 }}
                    >
                      <span style={{ color: 'var(--accent-bright)', flexShrink: 0, marginTop: 1 }}>
                        <IconSparkle size={11} />
                      </span>
                      <span>{s}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className="stack gap-2"
                style={{ alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}
              >
                <div className={`bubble ${m.role === 'user' ? 'bubble-user' : 'bubble-assistant'}`}>
                  {m.content}
                </div>

                {m.role === 'assistant' && (m.searched_meetings || m.time_filter) && (
                  <div className="row gap-2" style={{ paddingLeft: 2 }}>
                    {m.time_filter && (
                      <span className="badge badge-accent" style={{ fontSize: 10 }}>
                        <IconClock size={9} /> {m.time_filter}
                      </span>
                    )}
                    {m.searched_meetings ? (
                      <span style={{ fontSize: 10.5, color: 'var(--text-quaternary)' }}>
                        searched {m.searched_meetings} meeting{m.searched_meetings === 1 ? '' : 's'}
                      </span>
                    ) : null}
                  </div>
                )}

                {m.citations && m.citations.length > 0 && (
                  <div className="stack gap-1" style={{ maxWidth: '82%', width: '100%' }}>
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 620,
                        letterSpacing: '0.07em',
                        textTransform: 'uppercase',
                        color: 'var(--text-quaternary)',
                        paddingLeft: 2,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 5,
                      }}
                    >
                      <IconShield size={10} /> Verified sources
                    </span>
                    {m.citations.map((c, i) => (
                      <button
                        key={i}
                        className="citation"
                        onClick={() => navigate(`/meetings/${c.meeting_id}`)}
                        title="Open this meeting"
                        style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 5 }}
                      >
                        <span className="row gap-2" style={{ width: '100%' }}>
                          <span
                            style={{
                              fontSize: 12,
                              fontWeight: 600,
                              color: 'var(--accent-bright)',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {c.meeting_title}
                          </span>
                          <span
                            className="mono"
                            style={{ fontSize: 10, color: 'var(--text-quaternary)', flexShrink: 0, marginLeft: 'auto' }}
                          >
                            {formatRelativeTime(c.meeting_date)} · {c.timestamp}
                          </span>
                        </span>
                        <span style={{ fontSize: 11.5, lineHeight: 1.5, textAlign: 'left' }}>
                          {c.preview}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}

          {sending && (
            <div className="bubble bubble-assistant" style={{ padding: '11px 14px' }}>
              <span className="typing-dots" aria-label="Searching your meetings">
                <span />
                <span />
                <span />
              </span>
            </div>
          )}
        </div>

        <div className="chat-composer">
          <textarea
            ref={inputRef}
            className="textarea"
            style={{ minHeight: 38, maxHeight: 110, padding: '9px 11px', resize: 'none' }}
            placeholder="What did the client say about pricing last week?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                ask(question)
              }
            }}
            rows={1}
            maxLength={1000}
            disabled={sending}
            aria-label="Your question"
          />
          <button
            className="btn btn-primary btn-icon"
            onClick={() => ask(question)}
            disabled={!question.trim() || sending}
            aria-label="Ask"
            style={{ flexShrink: 0, height: 38, width: 38 }}
          >
            {sending ? <span className="spinner" /> : <IconSend size={14} />}
          </button>
        </div>
      </div>

      <div className="row gap-2" style={{ color: 'var(--text-quaternary)', fontSize: 11.5 }}>
        <IconAlert size={12} />
        <span>
          Answers come only from your own meetings. Every quote is verified against the transcript
          it's attributed to — an unverifiable one is dropped rather than shown.
        </span>
      </div>
    </div>
  )
}
