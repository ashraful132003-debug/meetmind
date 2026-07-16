import { useEffect, useState } from 'react'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type EmailDelivery } from '../lib/api'
import { formatRelativeTime } from '../lib/format'
import { IconAlert, IconCheckCircle, IconMail, IconSend, IconSparkle, IconX } from './Icons'

interface Props {
  meetingId: string
  ready: boolean
}

const TONES = [
  { key: 'professional', label: 'Professional' },
  { key: 'friendly', label: 'Friendly' },
  { key: 'brief', label: 'Brief' },
  { key: 'formal', label: 'Formal' },
]

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function EmailPanel({ meetingId, ready }: Props) {
  const toast = useToast()

  const [recipients, setRecipients] = useState<string[]>([])
  const [draft, setDraft] = useState('')
  const [note, setNote] = useState('')
  const [includeTranscript, setIncludeTranscript] = useState(false)
  const [sending, setSending] = useState(false)
  const [history, setHistory] = useState<EmailDelivery[]>([])
  const [error, setError] = useState('')
  const [drafting, setDrafting] = useState(false)
  const [tone, setTone] = useState('professional')

  const draftWithAI = async () => {
    setDrafting(true)
    try {
      const draft = await api.draftFollowUp(meetingId, tone)
      // The draft goes into the note field, which the email template already
      // renders at the top — so the AI's words become the email's opening, above
      // the generated summary, exactly where a human would write them.
      setNote(draft.body)
      toast.success('Draft written. Edit it as you like before sending.')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not draft the email.')
    } finally {
      setDrafting(false)
    }
  }

  const loadHistory = async () => {
    try {
      setHistory(await api.listEmails(meetingId))
    } catch {
      /* history is a nicety; failing to load it shouldn't block sending */
    }
  }

  useEffect(() => {
    loadHistory()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meetingId])

  const addRecipient = (raw: string) => {
    const value = raw.trim().replace(/[,;]$/, '')
    if (!value) return

    if (!EMAIL_RE.test(value)) {
      setError(`"${value}" doesn't look like an email address.`)
      return
    }
    if (recipients.includes(value.toLowerCase())) {
      setError('That address is already on the list.')
      setDraft('')
      return
    }
    if (recipients.length >= 20) {
      setError('You can send to at most 20 recipients at once.')
      return
    }

    setRecipients((prev) => [...prev, value.toLowerCase()])
    setDraft('')
    setError('')
  }

  const onDraftKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Enter, comma and space all commit the address - people type all three.
    if (e.key === 'Enter' || e.key === ',' || e.key === ' ') {
      e.preventDefault()
      addRecipient(draft)
    } else if (e.key === 'Backspace' && !draft && recipients.length > 0) {
      setRecipients((prev) => prev.slice(0, -1))
    }
  }

  const send = async () => {
    // Catch the common mistake of typing an address and hitting Send without
    // committing it as a chip.
    const pending = draft.trim()
    const list = pending && EMAIL_RE.test(pending) ? [...recipients, pending.toLowerCase()] : recipients

    if (list.length === 0) {
      setError('Add at least one recipient.')
      return
    }

    setSending(true)
    setError('')
    try {
      const res = await api.sendEmail(meetingId, {
        recipients: list,
        include_transcript: includeTranscript,
        note: note.trim(),
      })
      setRecipients([])
      setDraft('')
      setNote('')
      await loadHistory()

      if (res.status === 'captured') {
        toast.success('Email composed and captured locally. Open the preview to see exactly what would be sent.')
      } else {
        toast.success(`Summary sent to ${list.length} recipient${list.length === 1 ? '' : 's'}.`)
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Could not send the email.'
      setError(message)
      toast.error(message)
      await loadHistory()
    } finally {
      setSending(false)
    }
  }

  if (!ready) {
    return (
      <div className="card empty">
        <div className="empty-icon">
          <IconMail size={19} />
        </div>
        <h3>Not ready yet</h3>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 320, lineHeight: 1.6 }}>
          Once the summary is generated you can email it to everyone who was in the meeting.
        </p>
      </div>
    )
  }

  return (
    <div className="stack gap-4">
      <div className="card card-pad stack gap-4">
        <div className="stack gap-1">
          <span className="eyebrow">Share the summary</span>
          <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
            Sends the summary, action items and speaker breakdown as a formatted email.
          </span>
        </div>

        <div className="field">
          <label className="label" htmlFor="recipients">
            Recipients
          </label>
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 6,
              padding: recipients.length ? '7px 8px' : '0',
              background: recipients.length ? 'var(--bg-sunk)' : 'transparent',
              border: recipients.length ? '1px solid var(--border)' : 'none',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            {recipients.map((r) => (
              <span
                key={r}
                className="badge badge-accent"
                style={{ paddingRight: 4, fontSize: 11.5, gap: 4 }}
              >
                {r}
                <button
                  onClick={() => setRecipients((prev) => prev.filter((x) => x !== r))}
                  style={{ display: 'flex', color: 'inherit', opacity: 0.7, padding: 1 }}
                  aria-label={`Remove ${r}`}
                >
                  <IconX size={10} />
                </button>
              </span>
            ))}
            <input
              id="recipients"
              className="input"
              style={
                recipients.length
                  ? { border: 'none', background: 'transparent', padding: 0, height: 22, flex: 1, minWidth: 160 }
                  : undefined
              }
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onDraftKeyDown}
              onBlur={() => draft.trim() && addRecipient(draft)}
              placeholder={recipients.length ? 'Add another...' : 'rahul@company.com'}
              disabled={sending}
              aria-describedby="recipients-hint"
            />
          </div>
          <span className="field-hint" id="recipients-hint">
            Press Enter, comma or space after each address.
          </span>
        </div>

        <div className="field">
          <div className="row gap-2 wrap" style={{ justifyContent: 'space-between' }}>
            <label className="label" htmlFor="note">
              Message <span style={{ color: 'var(--text-quaternary)', fontWeight: 400 }}>(optional)</span>
            </label>

            <div className="row gap-1">
              <select
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                disabled={drafting || sending}
                className="input"
                style={{ height: 27, padding: '0 6px', fontSize: 11.5, width: 'auto' }}
                aria-label="Tone"
              >
                {TONES.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.label}
                  </option>
                ))}
              </select>
              <button
                className="btn btn-secondary btn-sm"
                onClick={draftWithAI}
                disabled={drafting || sending}
                title="Let the AI write the follow-up, grounded in what was actually said"
              >
                {drafting ? <span className="spinner" /> : <IconSparkle size={12} />}
                {drafting ? 'Writing...' : 'Write with AI'}
              </button>
            </div>
          </div>

          <textarea
            id="note"
            className="textarea"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Write a note, or let the AI draft the follow-up from what was actually said."
            maxLength={1000}
            disabled={sending || drafting}
            style={{ minHeight: drafting || note ? 150 : 64, transition: 'min-height 200ms' }}
          />
          <span className="field-hint">
            This appears at the top of the email, above the generated summary and action items.
          </span>
        </div>

        <label className="row gap-2" style={{ cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={includeTranscript}
            onChange={(e) => setIncludeTranscript(e.target.checked)}
            disabled={sending}
            style={{ accentColor: 'var(--accent)', width: 14, height: 14 }}
          />
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Include the full transcript</span>
        </label>

        {error && (
          <span className="field-error">
            <IconAlert size={12} /> {error}
          </span>
        )}

        <button
          className="btn btn-primary"
          onClick={send}
          disabled={sending || (recipients.length === 0 && !draft.trim())}
          style={{ alignSelf: 'flex-start' }}
        >
          {sending ? <span className="spinner" /> : <IconSend size={14} />}
          {sending ? 'Sending...' : 'Send summary'}
        </button>
      </div>

      {history.length > 0 && (
        <div className="card card-pad stack gap-3">
          <span className="eyebrow">Delivery history</span>
          <div className="stack gap-2">
            {history.map((d) => (
              <div
                key={d.id}
                className="row gap-3"
                style={{
                  padding: '10px 12px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--surface-1)',
                  border: '1px solid var(--border-subtle)',
                  alignItems: 'flex-start',
                }}
              >
                <span
                  style={{
                    color:
                      d.status === 'sent'
                        ? 'var(--success)'
                        : d.status === 'captured'
                          ? 'var(--accent-bright)'
                          : 'var(--danger)',
                    flexShrink: 0,
                    marginTop: 1,
                    display: 'flex',
                  }}
                >
                  {d.status === 'failed' ? <IconAlert size={13} /> : <IconCheckCircle size={13} />}
                </span>

                <div className="stack gap-1 grow" style={{ minWidth: 0 }}>
                  <span className="truncate" style={{ fontSize: 12.5 }}>
                    {d.recipients.join(', ')}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-quaternary)', lineHeight: 1.5 }}>
                    {formatRelativeTime(d.created_at)} · {d.detail}
                  </span>
                </div>

                {d.preview_url && (
                  <a
                    className="btn btn-secondary btn-sm"
                    href={d.preview_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ flexShrink: 0 }}
                  >
                    View email
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
