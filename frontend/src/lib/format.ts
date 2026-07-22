/** Formatting helpers shared across the app. */

export function formatDuration(seconds: number): string {
  if (!seconds || seconds < 0) return '0:00'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Human duration for stat tiles: "1h 24m", "8m", "45s". */
export function formatDurationLong(seconds: number): string {
  if (!seconds || seconds < 1) return '0m'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  if (m > 0) return `${m}m`
  return `${Math.floor(seconds)}s`
}

export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'unknown'

  const diff = Date.now() - then
  const mins = Math.floor(diff / 60000)

  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`

  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`

  const days = Math.floor(hours / 24)
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days}d ago`

  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: days > 365 ? 'numeric' : undefined,
  })
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'unknown'
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return (parts[0] ?? '?').slice(0, 2).toUpperCase()
  return ((parts[0]?.[0] ?? '') + (parts[parts.length - 1]?.[0] ?? '')).toUpperCase()
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English',
  hi: 'Hindi',
  ur: 'Urdu',
  ta: 'Tamil',
  te: 'Telugu',
  bn: 'Bengali',
  mr: 'Marathi',
  gu: 'Gujarati',
  kn: 'Kannada',
  ml: 'Malayalam',
  pa: 'Punjabi',
}

export function languageName(code: string | null): string {
  if (!code) return 'Unknown'
  return LANGUAGE_NAMES[code.toLowerCase()] ?? code.toUpperCase()
}

export const STATUS_LABELS: Record<string, string> = {
  uploaded: 'Queued',
  transcribing: 'Transcribing',
  diarizing: 'Identifying speakers',
  analyzing: 'Analysing',
  indexing: 'Indexing',
  ready: 'Ready',
  failed: 'Failed',
}

export function isProcessing(status: string): boolean {
  return ['uploaded', 'transcribing', 'diarizing', 'analyzing', 'indexing'].includes(status)
}

export type DueTone = 'overdue' | 'soon' | 'scheduled' | 'vague'

/**
 * Best-effort urgency from a free-text deadline like "Friday", "by the 20th",
 * "tomorrow", or "next sprint".
 *
 * Deliberately conservative: deadlines in meetings are spoken casually, and a
 * confident-but-wrong "overdue" flag is worse than an honest "has a deadline".
 * Anything it cannot resolve to a real date falls back to `vague` — still shown,
 * just not colour-coded as urgent. `reference` is injectable so this is testable
 * and never calls Date.now() implicitly in surprising places.
 */
export function parseDue(dueText: string | null, reference: Date = new Date()): { tone: DueTone; label: string } {
  if (!dueText) return { tone: 'vague', label: '' }
  const raw = dueText.trim()
  const t = raw.toLowerCase()
  const ref = new Date(reference.getFullYear(), reference.getMonth(), reference.getDate())
  const DAY = 86400000

  const daysUntil = (d: Date) => Math.round((d.getTime() - ref.getTime()) / DAY)
  const classify = (days: number): DueTone => (days < 0 ? 'overdue' : days <= 3 ? 'soon' : 'scheduled')

  if (/\btoday\b|\baaj\b/.test(t)) return { tone: 'soon', label: raw }
  if (/\btomorrow\b|\bkal\b/.test(t)) return { tone: 'soon', label: raw }
  if (/\byesterday\b/.test(t)) return { tone: 'overdue', label: raw }

  const WEEKDAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
  const wd = WEEKDAYS.findIndex((name) => t.includes(name))
  if (wd >= 0) {
    // Next occurrence of that weekday (today counts as this week).
    let delta = (wd - ref.getDay() + 7) % 7
    if (delta === 0) delta = 0
    const target = new Date(ref.getTime() + delta * DAY)
    return { tone: classify(daysUntil(target)), label: raw }
  }

  // "the 20th", "by 5th", "on the 3rd"
  const dom = t.match(/\b(\d{1,2})(?:st|nd|rd|th)\b/)
  if (dom) {
    const day = parseInt(dom[1]!, 10)
    if (day >= 1 && day <= 31) {
      let target = new Date(ref.getFullYear(), ref.getMonth(), day)
      if (target.getTime() < ref.getTime()) target = new Date(ref.getFullYear(), ref.getMonth() + 1, day)
      return { tone: classify(daysUntil(target)), label: raw }
    }
  }

  return { tone: 'vague', label: raw }
}
