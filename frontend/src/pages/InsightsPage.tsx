import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ApiError,
  api,
  type ContradictionBoard,
  type DecisionBoard,
  type DigestResponse,
  type KnowledgeGraph,
  type TimelineResponse,
} from '../lib/api'
import { formatDuration, formatRelativeTime } from '../lib/format'
import {
  IconAlert,
  IconBulb,
  IconCheckCircle,
  IconGitCommit,
  IconNetwork,
  IconRefresh,
  IconScale,
  IconSparkle,
} from '../components/Icons'

type Section = 'digest' | 'decisions' | 'contradictions' | 'timeline' | 'graph'

const SECTIONS: { key: Section; label: string; icon: typeof IconSparkle }[] = [
  { key: 'digest', label: 'Daily Digest', icon: IconSparkle },
  { key: 'decisions', label: 'Decisions', icon: IconScale },
  { key: 'contradictions', label: 'Contradictions', icon: IconAlert },
  { key: 'timeline', label: 'Timeline', icon: IconGitCommit },
  { key: 'graph', label: 'Knowledge Graph', icon: IconNetwork },
]

/** Shared "reading your meetings" loading state — the first hit computes AI insights. */
function Computing({ label }: { label: string }) {
  return (
    <div className="stack gap-3">
      <div className="row gap-2">
        <span className="spinner" style={{ color: 'var(--accent-bright)' }} />
        <span style={{ fontSize: 13.5, color: 'var(--text-secondary)' }}>{label}</span>
      </div>
      <div className="skeleton" style={{ height: 90 }} />
      <div className="skeleton" style={{ height: 90 }} />
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="card empty">
      <div className="empty-icon" style={{ color: 'var(--danger)', borderColor: 'rgba(239,68,68,0.3)' }}>
        <IconAlert size={19} />
      </div>
      <h3>Something went wrong</h3>
      <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 380, lineHeight: 1.6 }}>{message}</p>
      <button className="btn btn-secondary" onClick={onRetry} style={{ marginTop: 6 }}>
        <IconRefresh size={13} /> Try again
      </button>
    </div>
  )
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="card empty">
      <div className="empty-icon">
        <IconBulb size={19} />
      </div>
      <h3>{title}</h3>
      <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 400, lineHeight: 1.6 }}>{body}</p>
    </div>
  )
}

// --- Daily digest ------------------------------------------------------------

function DigestView() {
  const navigate = useNavigate()
  const [data, setData] = useState<DigestResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.getDigest())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not build your digest.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <Computing label="Putting together your digest…" />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!data || data.empty)
    return <EmptyState title="Nothing to digest yet" body="Process a meeting and a daily digest of decisions, tasks and deadlines will appear here." />

  return (
    <div className="stack gap-4">
      <div className="row gap-2" style={{ justifyContent: 'space-between' }}>
        <div className="stack gap-0">
          <span className="eyebrow">{data.is_today ? 'Today' : 'Most recent day'}</span>
          <h2 style={{ fontSize: 18 }}>{data.generated_for}</h2>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={load} title="Refresh">
          <IconRefresh size={13} />
        </button>
      </div>

      {data.narrative && (
        <div className="card card-pad" style={{ borderLeft: '3px solid var(--accent)' }}>
          <p style={{ fontSize: 14.5, lineHeight: 1.65 }}>{data.narrative}</p>
        </div>
      )}

      <div className="stat-grid">
        <div className="stat">
          <span className="stat-label">Meetings</span>
          <span className="stat-value">{data.meeting_count}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Decisions</span>
          <span className="stat-value">{data.decisions.length}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Open actions</span>
          <span className="stat-value">{data.open_action_count}</span>
        </div>
      </div>

      {data.meetings.length > 0 && (
        <div className="stack gap-2">
          <span className="eyebrow">Meetings</span>
          {data.meetings.map((m) => (
            <button
              key={m.id}
              className="card card-hover row gap-3"
              onClick={() => navigate(`/meetings/${m.id}`)}
              style={{ padding: '12px 15px', textAlign: 'left', justifyContent: 'space-between' }}
            >
              <span className="truncate" style={{ fontSize: 14, fontWeight: 550 }}>
                {m.title}
              </span>
              <span className="row gap-2" style={{ flexShrink: 0, fontSize: 11 }}>
                <span style={{ color: 'var(--text-quaternary)' }}>{formatDuration(m.duration_seconds)}</span>
                {m.open_action_count > 0 && (
                  <span className="badge badge-warning" style={{ fontSize: 10 }}>
                    {m.open_action_count} open
                  </span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}

      {data.priority_actions.length > 0 && (
        <div className="stack gap-2">
          <span className="eyebrow">Priority action items</span>
          {data.priority_actions.map((a) => (
            <div key={a.id} className="card row gap-3" style={{ padding: '11px 14px' }}>
              <span
                className="badge"
                style={{
                  fontSize: 10,
                  flexShrink: 0,
                  background: a.priority === 'high' ? 'rgba(239,68,68,0.12)' : 'rgba(245,158,11,0.12)',
                  color: a.priority === 'high' ? '#f87171' : '#fbbf24',
                  borderColor: 'transparent',
                }}
              >
                {a.priority}
              </span>
              <span className="grow" style={{ fontSize: 13.5, lineHeight: 1.5 }}>
                {a.task}
              </span>
              <span style={{ fontSize: 11, color: 'var(--text-quaternary)', flexShrink: 0 }}>{a.owner_label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// --- Decisions ---------------------------------------------------------------

function DecisionsView() {
  const navigate = useNavigate()
  const [board, setBoard] = useState<DecisionBoard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [topic, setTopic] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setBoard(await api.getDecisions())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load decisions.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const items = useMemo(
    () => (board ? (topic ? board.items.filter((d) => d.topic === topic) : board.items) : []),
    [board, topic],
  )

  if (loading) return <Computing label="Extracting decisions from every meeting…" />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!board || board.total === 0)
    return <EmptyState title="No decisions yet" body="As your meetings settle on things — a date, a vendor, a direction — every decision will be collected here automatically." />

  return (
    <div className="stack gap-4">
      <div className="row gap-3 wrap" style={{ justifyContent: 'space-between' }}>
        <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
          <strong style={{ color: 'var(--text-primary)' }}>{board.total}</strong> decisions across your meetings
        </span>
        <button className="btn btn-ghost btn-sm" onClick={load} title="Refresh">
          <IconRefresh size={13} />
        </button>
      </div>

      {board.topics.length > 1 && (
        <div className="row gap-2 wrap">
          <button
            className="chip"
            onClick={() => setTopic('')}
            style={{ cursor: 'pointer', borderColor: !topic ? 'var(--accent)' : undefined, color: !topic ? 'var(--accent-bright)' : undefined }}
          >
            All
          </button>
          {board.topics.map((t) => (
            <button
              key={t.topic}
              className="chip"
              onClick={() => setTopic(topic === t.topic ? '' : t.topic)}
              style={{ cursor: 'pointer', borderColor: topic === t.topic ? 'var(--accent)' : undefined, color: topic === t.topic ? 'var(--accent-bright)' : undefined }}
            >
              {t.topic} <span style={{ opacity: 0.6 }}>{t.count}</span>
            </button>
          ))}
        </div>
      )}

      <div className="stack gap-2">
        {items.map((d) => (
          <div
            key={d.id}
            className="card"
            style={{ padding: '14px 16px', borderLeft: `3px solid ${d.status === 'reversed' ? '#fb923c' : 'var(--success)'}` }}
          >
            <div className="stack gap-2">
              <div className="row gap-2 wrap" style={{ alignItems: 'flex-start' }}>
                <span style={{ fontSize: 14.5, fontWeight: 550, lineHeight: 1.5 }} className="grow">
                  {d.decision}
                </span>
                {d.status === 'reversed' && (
                  <span className="badge" style={{ background: 'rgba(251,146,60,0.14)', color: '#fb923c', borderColor: 'transparent', fontSize: 10 }}>
                    reversal
                  </span>
                )}
              </div>
              {d.quote && (
                <p style={{ fontSize: 12.5, color: 'var(--text-tertiary)', fontStyle: 'italic', lineHeight: 1.5 }}>
                  “{d.quote}”
                </p>
              )}
              <div className="row gap-2 wrap" style={{ fontSize: 11 }}>
                <span className="badge badge-accent" style={{ fontSize: 10 }}>{d.topic}</span>
                <span className="badge badge-neutral" style={{ fontSize: 10 }}>{d.made_by}</span>
                <button
                  onClick={() => navigate(`/meetings/${d.meeting_id}`)}
                  style={{ fontSize: 10.5, color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: 4 }}
                  title="Open the meeting this came from"
                >
                  <IconSparkle size={9} />
                  <span className="truncate" style={{ maxWidth: 220, textDecoration: 'underline', textUnderlineOffset: 2 }}>
                    {d.meeting_title}
                  </span>
                  <span style={{ color: 'var(--text-quaternary)' }}>{formatRelativeTime(d.meeting_date)}</span>
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// --- Contradictions ----------------------------------------------------------

function ContradictionsView() {
  const navigate = useNavigate()
  const [board, setBoard] = useState<ContradictionBoard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setBoard(await api.getContradictions())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not check for contradictions.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <Computing label="Comparing decisions across your meetings…" />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!board || board.total === 0)
    return (
      <div className="card empty">
        <div className="empty-icon" style={{ color: 'var(--success)', borderColor: 'rgba(16,185,129,0.3)' }}>
          <IconCheckCircle size={19} />
        </div>
        <h3>No contradictions found</h3>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 13, maxWidth: 400, lineHeight: 1.6 }}>
          {board && board.checked_decisions > 0
            ? `Checked ${board.checked_decisions} decisions across your meetings — none of them conflict.`
            : 'Once you have decisions across a few meetings, MeetMind will flag any that contradict each other.'}
        </p>
      </div>
    )

  return (
    <div className="stack gap-4">
      <div className="row gap-2" style={{ justifyContent: 'space-between' }}>
        <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
          <strong style={{ color: 'var(--danger)' }}>{board.total}</strong> potential contradiction{board.total === 1 ? '' : 's'} across {board.checked_decisions} decisions
        </span>
        <button className="btn btn-ghost btn-sm" onClick={load} title="Refresh">
          <IconRefresh size={13} />
        </button>
      </div>

      {board.items.map((c, i) => (
        <div key={i} className="card card-pad" style={{ borderLeft: '3px solid var(--danger)' }}>
          <div className="stack gap-3">
            <div className="row gap-2" style={{ alignItems: 'center' }}>
              <span className="empty-icon" style={{ width: 30, height: 30, margin: 0, color: 'var(--danger)', borderColor: 'rgba(239,68,68,0.3)' }}>
                <IconAlert size={14} />
              </span>
              <span style={{ fontSize: 14.5, fontWeight: 600 }}>{c.topic}</span>
            </div>
            <p style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--text-secondary)' }}>{c.explanation}</p>

            <div className="stack gap-2">
              {[
                { d: c.earlier, tag: 'Earlier', color: 'var(--text-tertiary)' },
                { d: c.later, tag: 'Later', color: 'var(--danger)' },
              ].map(({ d, tag, color }) => (
                <button
                  key={tag}
                  onClick={() => navigate(`/meetings/${d.meeting_id}`)}
                  className="card row gap-3"
                  style={{ padding: '10px 13px', textAlign: 'left', alignItems: 'flex-start' }}
                >
                  <span className="badge" style={{ fontSize: 9.5, flexShrink: 0, color, borderColor: 'transparent', background: 'var(--surface-2)' }}>
                    {tag}
                  </span>
                  <div className="stack gap-1 grow" style={{ minWidth: 0 }}>
                    <span style={{ fontSize: 13, lineHeight: 1.45 }}>{d.decision}</span>
                    <span style={{ fontSize: 10.5, color: 'var(--text-quaternary)' }} className="truncate">
                      {d.meeting_title} · {formatRelativeTime(d.meeting_date)}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// --- Timeline ----------------------------------------------------------------

function TimelineView() {
  const navigate = useNavigate()
  const [data, setData] = useState<TimelineResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.getTimeline())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load the timeline.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <Computing label="Assembling your project history…" />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!data || data.total === 0)
    return <EmptyState title="No history yet" body="Every meeting and decision will appear here as a single chronological stream — how a project actually evolved over time." />

  return (
    <div className="stack gap-4">
      <div className="row gap-2" style={{ justifyContent: 'space-between' }}>
        <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>{data.total} events, newest first</span>
        <button className="btn btn-ghost btn-sm" onClick={load} title="Refresh">
          <IconRefresh size={13} />
        </button>
      </div>

      <div style={{ position: 'relative', paddingLeft: 22 }}>
        <div style={{ position: 'absolute', left: 6, top: 4, bottom: 4, width: 2, background: 'var(--border-subtle)' }} />
        <div className="stack gap-3">
          {data.events.map((e, i) => {
            const isMeeting = e.kind === 'meeting'
            const color = isMeeting ? 'var(--accent)' : e.status === 'reversed' ? '#fb923c' : 'var(--success)'
            return (
              <div key={i} style={{ position: 'relative' }}>
                <span
                  style={{
                    position: 'absolute',
                    left: -22,
                    top: 4,
                    width: 14,
                    height: 14,
                    borderRadius: 99,
                    background: 'var(--surface-0)',
                    border: `2.5px solid ${color}`,
                  }}
                />
                <button
                  className="card card-hover stack gap-1"
                  onClick={() => navigate(`/meetings/${e.meeting_id}`)}
                  style={{ padding: '11px 14px', textAlign: 'left', width: '100%' }}
                >
                  <div className="row gap-2" style={{ justifyContent: 'space-between' }}>
                    <span className="badge" style={{ fontSize: 9.5, background: `${color}1f`, color, borderColor: 'transparent' }}>
                      {isMeeting ? 'Meeting' : 'Decision'}
                    </span>
                    <span style={{ fontSize: 10.5, color: 'var(--text-quaternary)' }}>{formatRelativeTime(e.date)}</span>
                  </div>
                  <span style={{ fontSize: 13.5, fontWeight: isMeeting ? 600 : 500, lineHeight: 1.45 }}>{e.title}</span>
                  {e.detail && <span style={{ fontSize: 11.5, color: 'var(--text-tertiary)' }}>{e.detail}</span>}
                  {!isMeeting && (
                    <span className="truncate" style={{ fontSize: 10.5, color: 'var(--text-quaternary)' }}>
                      in {e.meeting_title}
                    </span>
                  )}
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// --- Knowledge graph ---------------------------------------------------------

const KIND_COLOR: Record<string, string> = {
  meeting: '#6366f1',
  person: '#34d399',
  project: '#fbbf24',
  client: '#f472b6',
}

function GraphView() {
  const navigate = useNavigate()
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hover, setHover] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setGraph(await api.getKnowledgeGraph())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not build the knowledge graph.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Deterministic two-ring layout: meetings on an inner ring, entities on an
  // outer ring. No physics, so it never jitters and always renders the same.
  const layout = useMemo(() => {
    if (!graph) return null
    const meetings = graph.nodes.filter((n) => n.kind === 'meeting')
    const entities = graph.nodes.filter((n) => n.kind !== 'meeting')
    const pos: Record<string, { x: number; y: number }> = {}

    const innerR = meetings.length <= 1 ? 0 : 120
    const outerR = 250
    meetings.forEach((n, i) => {
      const a = (2 * Math.PI * i) / Math.max(meetings.length, 1) - Math.PI / 2
      pos[n.id] = { x: Math.cos(a) * innerR, y: Math.sin(a) * innerR }
    })
    entities.forEach((n, i) => {
      const a = (2 * Math.PI * i) / Math.max(entities.length, 1) - Math.PI / 2
      pos[n.id] = { x: Math.cos(a) * outerR, y: Math.sin(a) * outerR }
    })
    return { pos, meetings, entities }
  }, [graph])

  if (loading) return <Computing label="Connecting people, projects and clients…" />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!graph || graph.nodes.length === 0)
    return <EmptyState title="Nothing to connect yet" body="Once your meetings mention people, projects and clients, MeetMind links them into a knowledge graph so you can see how everything relates." />

  const connectedToHover = new Set<string>()
  if (hover) {
    connectedToHover.add(hover)
    for (const e of graph.edges) {
      if (e.source === hover) connectedToHover.add(e.target)
      if (e.target === hover) connectedToHover.add(e.source)
    }
  }

  return (
    <div className="stack gap-4">
      <div className="row gap-2" style={{ justifyContent: 'space-between' }}>
        <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
          {graph.meeting_count} meetings · {graph.entity_count} entities
        </span>
        <button className="btn btn-ghost btn-sm" onClick={load} title="Refresh">
          <IconRefresh size={13} />
        </button>
      </div>

      <div className="row gap-3 wrap">
        {Object.entries(KIND_COLOR).map(([kind, color]) => (
          <span key={kind} className="row gap-1" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
            <span style={{ width: 9, height: 9, borderRadius: 99, background: color, display: 'inline-block' }} />
            {kind}
          </span>
        ))}
      </div>

      <div className="card" style={{ padding: 8, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <svg
            viewBox="-320 -320 640 640"
            style={{ width: '100%', minWidth: 460, maxHeight: 560, display: 'block' }}
            role="img"
            aria-label="Knowledge graph of meetings and entities"
          >
            {layout &&
              graph.edges.map((e, i) => {
                const a = layout.pos[e.source]
                const b = layout.pos[e.target]
                if (!a || !b) return null
                const active = !hover || (connectedToHover.has(e.source) && connectedToHover.has(e.target))
                return (
                  <line
                    key={i}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke="var(--border-strong, #333)"
                    strokeWidth={1}
                    opacity={active ? 0.5 : 0.08}
                  />
                )
              })}
            {layout &&
              graph.nodes.map((n) => {
                const p = layout.pos[n.id]
                if (!p) return null
                const color = KIND_COLOR[n.kind] ?? '#888'
                const r = n.kind === 'meeting' ? 9 : Math.min(6 + n.weight * 1.6, 13)
                const dim = hover && !connectedToHover.has(n.id)
                const isMeeting = n.kind === 'meeting'
                return (
                  <g
                    key={n.id}
                    transform={`translate(${p.x}, ${p.y})`}
                    opacity={dim ? 0.2 : 1}
                    style={{ cursor: isMeeting ? 'pointer' : 'default' }}
                    onMouseEnter={() => setHover(n.id)}
                    onMouseLeave={() => setHover(null)}
                    onClick={() => isMeeting && navigate(`/meetings/${n.id.replace('meeting:', '')}`)}
                  >
                    <circle r={r} fill={color} stroke="var(--surface-0)" strokeWidth={2} />
                    <text
                      y={r + 11}
                      textAnchor="middle"
                      fontSize={10}
                      fill="var(--text-secondary)"
                      style={{ pointerEvents: 'none' }}
                    >
                      {n.label.length > 22 ? n.label.slice(0, 21) + '…' : n.label}
                    </text>
                  </g>
                )
              })}
          </svg>
        </div>
      </div>
      <p style={{ fontSize: 11, color: 'var(--text-quaternary)' }}>
        Hover a node to highlight its connections. Click a meeting to open it.
      </p>
    </div>
  )
}

// --- Page shell --------------------------------------------------------------

export default function InsightsPage() {
  const [section, setSection] = useState<Section>('digest')

  return (
    <div className="page stack gap-5">
      <div className="page-header" style={{ marginBottom: 0 }}>
        <div className="stack gap-1">
          <span className="eyebrow">Your second brain</span>
          <h1>Insights</h1>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 13.5 }}>
            What your meetings decided, contradicted, and connected — across all of them.
          </p>
        </div>
      </div>

      <div className="tabs" style={{ overflowX: 'auto' }}>
        {SECTIONS.map(({ key, label, icon: Icon }) => (
          <button key={key} className={`tab${section === key ? ' active' : ''}`} onClick={() => setSection(key)}>
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      <div style={{ minHeight: 300 }}>
        {section === 'digest' && <DigestView />}
        {section === 'decisions' && <DecisionsView />}
        {section === 'contradictions' && <ContradictionsView />}
        {section === 'timeline' && <TimelineView />}
        {section === 'graph' && <GraphView />}
      </div>
    </div>
  )
}
