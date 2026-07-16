import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { ApiError, api, type MeetingDetail } from '../lib/api'
import { formatDuration } from '../lib/format'
import { IconCheck, IconFile, IconUsers } from './Icons'

interface Props {
  meeting: MeetingDetail
}

/** WhatsApp's own share URL. No API, no account, no Business API fees — it just
 *  opens WhatsApp with the text pre-filled and lets the user pick the chat.
 *  The Business API would cost money per message and need approval; for "send my
 *  team the summary" this is strictly better. */
const WA_LIMIT = 1800

function buildWhatsAppText(meeting: MeetingDetail): string {
  const lines: string[] = []
  lines.push(`*${meeting.title}*`)
  lines.push(
    `_${formatDuration(meeting.duration_seconds)} · ${meeting.speakers.length} speaker${
      meeting.speakers.length === 1 ? '' : 's'
    }_`,
  )
  lines.push('')

  // Just the Overview section: WhatsApp truncates long messages and nobody reads
  // a wall of text on a phone anyway.
  if (meeting.summary) {
    const overview = meeting.summary
      .split(/^##\s+/m)
      .find((s) => s.toLowerCase().startsWith('overview'))
      ?.replace(/^overview\s*/i, '')
      .trim()

    const body = (overview ?? meeting.summary).replace(/[*#`]/g, '').trim()
    lines.push(body.slice(0, 600))
    lines.push('')
  }

  const open = meeting.action_items.filter((a) => !a.done)
  if (open.length > 0) {
    lines.push('*Action items:*')
    for (const a of open.slice(0, 8)) {
      const due = a.due_text ? ` _(due ${a.due_text})_` : ''
      lines.push(`• ${a.owner_label}: ${a.task}${due}`)
    }
    if (open.length > 8) lines.push(`_...and ${open.length - 8} more_`)
    lines.push('')
  }

  lines.push('_Summarised by MeetMind_')

  let text = lines.join('\n')
  if (text.length > WA_LIMIT) text = `${text.slice(0, WA_LIMIT - 3)}...`
  return text
}

export default function ExportPanel({ meeting }: Props) {
  const toast = useToast()
  const [includeTranscript, setIncludeTranscript] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const download = async (format: 'pdf' | 'docx') => {
    setBusy(format)
    try {
      const { filename, size } = await api.exportMeeting(meeting.id, format, includeTranscript)
      toast.success(`Downloaded ${filename} (${Math.round(size / 1024)} KB)`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : `Could not generate the ${format.toUpperCase()}.`)
    } finally {
      setBusy(null)
    }
  }

  const shareWhatsApp = () => {
    const text = buildWhatsAppText(meeting)
    // api.whatsapp.com works on both desktop and mobile; wa.me redirects oddly on
    // some desktop browsers when no phone number is given.
    window.open(`https://api.whatsapp.com/send?text=${encodeURIComponent(text)}`, '_blank', 'noopener')
  }

  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(buildWhatsAppText(meeting))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('Could not copy — your browser blocked clipboard access.')
    }
  }

  const preview = buildWhatsAppText(meeting)

  return (
    <div className="stack gap-4">
      <div className="card card-pad stack gap-4">
        <div className="stack gap-1">
          <span className="eyebrow">Download</span>
          <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
            Generated on the server from the real data — not a screenshot of this page.
          </span>
        </div>

        <label className="row gap-2" style={{ cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={includeTranscript}
            onChange={(e) => setIncludeTranscript(e.target.checked)}
            style={{ accentColor: 'var(--accent)', width: 14, height: 14 }}
          />
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            Include the full transcript
          </span>
        </label>

        <div className="row gap-2 wrap">
          <button className="btn btn-secondary" onClick={() => download('pdf')} disabled={busy !== null}>
            {busy === 'pdf' ? <span className="spinner" /> : <IconFile size={14} />}
            {busy === 'pdf' ? 'Generating...' : 'Download PDF'}
          </button>
          <button className="btn btn-secondary" onClick={() => download('docx')} disabled={busy !== null}>
            {busy === 'docx' ? <span className="spinner" /> : <IconFile size={14} />}
            {busy === 'docx' ? 'Generating...' : 'Download Word'}
          </button>
        </div>
      </div>

      <div className="card card-pad stack gap-4">
        <div className="stack gap-1">
          <span className="eyebrow">Send on WhatsApp</span>
          <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
            Opens WhatsApp with the summary and open action items ready to send. You choose the chat.
          </span>
        </div>

        <div
          style={{
            padding: '11px 13px',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--bg-sunk)',
            border: '1px solid var(--border-subtle)',
            fontSize: 12,
            lineHeight: 1.65,
            color: 'var(--text-secondary)',
            whiteSpace: 'pre-wrap',
            maxHeight: 190,
            overflowY: 'auto',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {preview}
        </div>

        <div className="row gap-2 wrap">
          <button
            className="btn"
            onClick={shareWhatsApp}
            style={{ background: '#25D366', color: '#062e17', fontWeight: 600 }}
          >
            <IconUsers size={14} /> Open in WhatsApp
          </button>
          <button className="btn btn-secondary" onClick={copyText}>
            {copied ? <IconCheck size={14} /> : null}
            {copied ? 'Copied' : 'Copy text'}
          </button>
          <span style={{ fontSize: 11, color: 'var(--text-quaternary)', alignSelf: 'center' }}>
            {preview.length} characters
          </span>
        </div>
      </div>
    </div>
  )
}
