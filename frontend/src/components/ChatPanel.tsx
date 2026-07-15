import { useEffect, useRef, useState } from 'react'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type ChatMessage } from '../lib/api'
import { IconChat, IconSend, IconSparkle, IconTrash } from './Icons'

interface Props {
  meetingId: string
  ready: boolean
  onSeek: (seconds: number) => void
}

export default function ChatPanel({ meetingId, ready, onSeek }: Props) {
  const toast = useToast()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [question, setQuestion] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)

  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    let cancelled = false

    ;(async () => {
      try {
        const history = await api.getChatHistory(meetingId)
        if (!cancelled) setMessages(history)

        // Only bother generating starters for an empty conversation.
        if (history.length === 0 && ready) {
          const s = await api.getChatSuggestions(meetingId)
          if (!cancelled) setSuggestions(s)
        }
      } catch {
        /* An empty chat is a fine fallback - no need to shout about it. */
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [meetingId, ready])

  // Keep the newest message in view as the conversation grows.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  const ask = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || sending || !ready) return

    setQuestion('')
    setSuggestions([])
    setSending(true)

    // Optimistic echo so the question appears instantly. It carries a temporary
    // id; the server's canonical copy replaces the whole list on success.
    const optimistic: ChatMessage = {
      id: `pending-${Date.now()}`,
      role: 'user',
      content: trimmed,
      citations: null,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, optimistic])

    try {
      const res = await api.ask(meetingId, trimmed)
      setMessages((prev) => [...prev.filter((m) => m.id !== optimistic.id), optimistic, res.answer])
    } catch (err) {
      // Roll the optimistic message back - leaving it would imply it was asked.
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id))
      setQuestion(trimmed)
      toast.error(err instanceof ApiError ? err.message : 'Could not get an answer. Please try again.')
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  const clear = async () => {
    if (!window.confirm('Clear this conversation? The meeting itself is not affected.')) return
    try {
      await api.clearChat(meetingId)
      setMessages([])
      const s = await api.getChatSuggestions(meetingId).catch(() => [])
      setSuggestions(s)
      toast.success('Conversation cleared.')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not clear the conversation.')
    }
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends, Shift+Enter makes a newline - the convention every chat uses.
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      ask(question)
    }
  }

  if (!ready) {
    return (
      <div className="card empty">
        <div className="empty-icon">
          <IconChat size={19} />
        </div>
        <h3>Not ready yet</h3>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 340, lineHeight: 1.6 }}>
          Once this meeting finishes processing, you can ask questions about it and get answers with
          timestamps you can click to verify.
        </p>
      </div>
    )
  }

  return (
    <div className="card stack" style={{ height: 'clamp(420px, 62vh, 640px)', overflow: 'hidden' }}>
      <div
        className="row gap-2"
        style={{ padding: '12px 14px', borderBottom: '1px solid var(--border-subtle)', justifyContent: 'space-between' }}
      >
        <div className="row gap-2">
          <span style={{ color: 'var(--accent-bright)', display: 'flex' }}>
            <IconSparkle size={14} />
          </span>
          <span style={{ fontSize: 13.5, fontWeight: 570 }}>Ask this meeting</span>
        </div>
        {messages.length > 0 && (
          <button className="btn btn-ghost btn-sm" onClick={clear} title="Clear conversation">
            <IconTrash size={12} />
          </button>
        )}
      </div>

      <div className="chat-scroll" ref={scrollRef}>
        {loading ? (
          <div className="stack gap-3">
            <div className="skeleton" style={{ height: 40, width: '65%' }} />
            <div className="skeleton" style={{ height: 60, width: '80%', alignSelf: 'flex-end' }} />
          </div>
        ) : messages.length === 0 ? (
          <div className="stack gap-4" style={{ margin: 'auto 0', alignItems: 'center', textAlign: 'center' }}>
            <div className="empty-icon">
              <IconChat size={18} />
            </div>
            <div className="stack gap-1">
              <span style={{ fontSize: 14, fontWeight: 550 }}>Ask anything about this meeting</span>
              <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)', maxWidth: 300, lineHeight: 1.6 }}>
                Answers come only from the transcript, with timestamps you can click to check.
              </span>
            </div>

            {suggestions.length > 0 && (
              <div className="stack gap-2" style={{ width: '100%', maxWidth: 380 }}>
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
            <div key={m.id} className="stack gap-2" style={{ alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div className={`bubble ${m.role === 'user' ? 'bubble-user' : 'bubble-assistant'}`}>{m.content}</div>

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
                    }}
                  >
                    Sources
                  </span>
                  {m.citations.map((c, i) => (
                    <button
                      key={i}
                      className="citation"
                      onClick={() => onSeek(c.start_time)}
                      title="Jump to this moment in the recording"
                    >
                      <span className="mono" style={{ color: 'var(--accent-bright)', flexShrink: 0, fontSize: 11 }}>
                        {c.timestamp}
                      </span>
                      <span style={{ lineHeight: 1.5 }} className="grow">
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
            <span className="typing-dots" aria-label="Thinking">
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
          placeholder="What deadline did they agree on?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          maxLength={1000}
          disabled={sending}
          aria-label="Your question"
        />
        <button
          className="btn btn-primary btn-icon"
          onClick={() => ask(question)}
          disabled={!question.trim() || sending}
          aria-label="Send question"
          style={{ flexShrink: 0, height: 38, width: 38 }}
        >
          {sending ? <span className="spinner" /> : <IconSend size={14} />}
        </button>
      </div>
    </div>
  )
}
