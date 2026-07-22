import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, type BlindSpotReport } from '../lib/api'
import { IconAlert, IconBulb, IconRefresh } from './Icons'

/**
 * Blind Spot Detector — a constructive, after-the-fact review of one meeting.
 *
 * The point is not to be negative: it is to catch the things a busy room misses —
 * a risk raised and dropped, a stakeholder never consulted, a deadline nobody
 * pressure-tested — so the *next* decision is stronger. The report is computed
 * once and cached server-side, so re-opening this tab is instant.
 */

const CATEGORY_COLOR: Record<string, string> = {
  'Ignored risk': '#f87171',
  'Missing stakeholder': '#fbbf24',
  'Unrealistic deadline': '#fb923c',
  'Budget concern': '#34d399',
  'Legal or compliance': '#a78bfa',
  'No fallback plan': '#f472b6',
  'Untested assumption': '#60a5fa',
}

function colorFor(category: string): string {
  return CATEGORY_COLOR[category] ?? 'var(--accent-bright)'
}

export default function BlindSpotPanel({ meetingId, ready }: { meetingId: string; ready: boolean }) {
  const [report, setReport] = useState<BlindSpotReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setReport(await api.getBlindSpots(meetingId))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not review this meeting.')
    } finally {
      setLoading(false)
    }
  }, [meetingId])

  useEffect(() => {
    if (ready) load()
    else setLoading(false)
  }, [ready, load])

  if (!ready) {
    return (
      <div className="card empty">
        <div className="empty-icon">
          <IconBulb size={19} />
        </div>
        <h3>Not ready yet</h3>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 360, lineHeight: 1.6 }}>
          The Blind Spot review runs once the meeting has finished processing.
        </p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="stack gap-3">
        <div className="skeleton" style={{ height: 60 }} />
        <div className="skeleton" style={{ height: 84 }} />
        <div className="skeleton" style={{ height: 84 }} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="card empty">
        <div className="empty-icon" style={{ color: 'var(--danger)', borderColor: 'rgba(239,68,68,0.3)' }}>
          <IconAlert size={19} />
        </div>
        <h3>Couldn't run the review</h3>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 380, lineHeight: 1.6 }}>{error}</p>
        <button className="btn btn-secondary" onClick={load} style={{ marginTop: 6 }}>
          <IconRefresh size={13} /> Try again
        </button>
      </div>
    )
  }

  if (!report) return null

  return (
    <div className="stack gap-4">
      <div className="row gap-3" style={{ alignItems: 'flex-start' }}>
        <div
          className="empty-icon"
          style={{ color: 'var(--accent-bright)', width: 38, height: 38, flexShrink: 0, margin: 0 }}
        >
          <IconBulb size={18} />
        </div>
        <div className="stack gap-1 grow">
          <div className="row gap-2" style={{ justifyContent: 'space-between' }}>
            <span className="eyebrow">Blind Spot Detector</span>
            <button className="btn btn-ghost btn-sm" onClick={load} title="Re-run">
              <IconRefresh size={12} />
            </button>
          </div>
          <p style={{ fontSize: 15, fontWeight: 560, lineHeight: 1.5 }}>{report.headline}</p>
        </div>
      </div>

      {report.findings.length === 0 ? (
        <div className="card card-pad" style={{ textAlign: 'center' }}>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 13.5, lineHeight: 1.6 }}>
            No obvious blind spots — this meeting covered its bases well.
          </p>
        </div>
      ) : (
        <div className="stack gap-2">
          {report.findings.map((f, i) => {
            const color = colorFor(f.category)
            return (
              <div
                key={i}
                className="card"
                style={{ padding: '14px 16px', borderLeft: `3px solid ${color}` }}
              >
                <div className="stack gap-2">
                  <span
                    className="badge"
                    style={{
                      background: `${color}1f`,
                      color,
                      borderColor: 'transparent',
                      fontSize: 10.5,
                      alignSelf: 'flex-start',
                    }}
                  >
                    {f.category}
                  </span>
                  <p style={{ fontSize: 14, lineHeight: 1.55 }}>{f.concern}</p>
                  {f.question && (
                    <p
                      style={{
                        fontSize: 12.5,
                        color: 'var(--text-tertiary)',
                        lineHeight: 1.5,
                        fontStyle: 'italic',
                        borderTop: '1px solid var(--border-subtle)',
                        paddingTop: 8,
                      }}
                    >
                      Ask: {f.question}
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <p style={{ fontSize: 11, color: 'var(--text-quaternary)', lineHeight: 1.5 }}>
        An AI review of what the meeting may have overlooked — grounded in what was said, not a substitute for judgement.
      </p>
    </div>
  )
}
