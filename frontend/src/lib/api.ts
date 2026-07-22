/**
 * API client.
 *
 * Two things here are worth understanding:
 *
 * 1. The access token lives in a module variable, NOT in localStorage. Anything
 *    in localStorage is readable by any script on the page, so an XSS bug would
 *    hand an attacker a token they could keep using. In memory, it dies with the
 *    tab. The refresh cookie is httpOnly, so JavaScript cannot read that either.
 *
 * 2. When a request 401s, we transparently refresh and retry once. Concurrent
 *    401s share a single in-flight refresh (see `refreshPromise`) - otherwise ten
 *    parallel requests would fire ten refreshes, and since refresh tokens rotate,
 *    nine of them would be rejected as "reused" and log the user out. That bug is
 *    easy to write and painful to find.
 */

export class ApiError extends Error {
  status: number
  requestId?: string

  constructor(message: string, status: number, requestId?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.requestId = requestId
  }
}

let accessToken: string | null = null
let refreshPromise: Promise<boolean> | null = null
let onAuthLost: (() => void) | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
}

export function getAccessToken() {
  return accessToken
}

export function setAuthLostHandler(handler: (() => void) | null) {
  onAuthLost = handler
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
    if (Array.isArray(body?.detail)) {
      return body.detail.map((d: { msg?: string }) => d?.msg ?? 'Invalid input').join(', ')
    }
  } catch {
    /* non-JSON error body */
  }
  return res.statusText || `Request failed (${res.status})`
}

async function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise

  refreshPromise = (async () => {
    try {
      const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) return false
      const data = await res.json()
      accessToken = data.access_token
      return true
    } catch {
      return false
    } finally {
      // Cleared on the next tick so simultaneous callers all observe the same
      // settled promise before it is dropped.
      setTimeout(() => {
        refreshPromise = null
      }, 0)
    }
  })()

  return refreshPromise
}

interface RequestOptions {
  method?: string
  body?: unknown
  isFormData?: boolean
  signal?: AbortSignal
  skipRetry?: boolean
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, isFormData = false, signal, skipRetry = false } = options

  const headers: Record<string, string> = {}
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  if (body !== undefined && !isFormData) headers['Content-Type'] = 'application/json'

  const res = await fetch(path, {
    method,
    headers,
    credentials: 'include',
    signal,
    body: body === undefined ? undefined : isFormData ? (body as FormData) : JSON.stringify(body),
  })

  if (res.status === 401 && !skipRetry && !path.includes('/auth/refresh')) {
    const refreshed = await refreshAccessToken()
    if (refreshed) {
      return request<T>(path, { ...options, skipRetry: true })
    }
    accessToken = null
    onAuthLost?.()
    throw new ApiError('Your session has expired. Please sign in again.', 401)
  }

  if (!res.ok) {
    throw new ApiError(await parseError(res), res.status, res.headers.get('X-Request-ID') ?? undefined)
  }

  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

// --- Types -------------------------------------------------------------------

export interface User {
  id: string
  email: string
  full_name: string
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface MeetingListItem {
  id: string
  title: string
  status: MeetingStatus
  progress: number
  stage_label: string
  duration_seconds: number
  language: string | null
  topics: string[] | null
  sentiment: string | null
  speaker_count: number
  action_item_count: number
  open_action_count: number
  created_at: string
  error_message: string | null
}

export type MeetingStatus =
  | 'uploaded'
  | 'transcribing'
  | 'diarizing'
  | 'analyzing'
  | 'indexing'
  | 'ready'
  | 'failed'

export interface Speaker {
  id: string
  tag: string
  display_name: string
  talk_seconds: number
  word_count: number
  segment_count: number
  color: string
}

export interface ActionItem {
  id: string
  task: string
  owner_label: string
  speaker_tag: string | null
  due_text: string | null
  priority: 'low' | 'medium' | 'high'
  done: boolean
  quote_time: number | null
}

export interface MeetingDetail {
  id: string
  title: string
  status: MeetingStatus
  progress: number
  stage_label: string
  source: string
  audio_filename: string | null
  duration_seconds: number
  language: string | null
  summary: string | null
  topics: string[] | null
  sentiment: string | null
  created_at: string
  processed_at: string | null
  error_message: string | null
  speakers: Speaker[]
  action_items: ActionItem[]
  audio_url: string | null
}

export interface Segment {
  id: string
  speaker_tag: string
  speaker_name: string
  start_time: number
  end_time: number
  text: string
}

export interface TranscriptResponse {
  meeting_id: string
  language: string | null
  segments: Segment[]
}

export interface Citation {
  start_time: number
  end_time: number
  timestamp: string
  speakers: string[]
  score: number
  preview: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[] | null
  created_at: string
}

export interface SpeakerShare {
  name: string
  tag: string
  color: string
  talk_seconds: number
  share_percent: number
  word_count: number
  words_per_minute: number
}

export interface TimelineBlock {
  speaker_tag: string
  speaker_name: string
  color: string
  start_time: number
  end_time: number
}

export interface MeetingAnalytics {
  meeting_id: string
  duration_seconds: number
  total_words: number
  speaker_count: number
  speakers: SpeakerShare[]
  timeline: TimelineBlock[]
  topics: string[]
  sentiment: string | null
  balance_score: number
  longest_monologue_seconds: number
  longest_monologue_speaker: string | null
}

export interface WorkspaceStats {
  total_meetings: number
  ready_meetings: number
  processing_meetings: number
  total_duration_seconds: number
  total_action_items: number
  open_action_items: number
  hours_saved_estimate: number
  top_topics: { topic: string; count: number }[]
  recent_activity: {
    id: string
    title: string
    status: string
    created_at: string
    duration_seconds: number
  }[]
}

export interface EmailDelivery {
  id: string
  recipients: string[]
  subject: string
  transport: string
  status: string
  detail: string | null
  preview_url: string | null
  created_at: string
}

export interface SessionInfo {
  id: string
  user_agent: string
  ip_address: string
  created_at: string
  last_used_at: string
}

export interface MemoryCitation {
  meeting_id: string
  meeting_title: string
  meeting_date: string
  start_time: number
  end_time: number
  timestamp: string
  speakers: string[]
  score: number
  preview: string
}

export interface MemoryMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: MemoryCitation[] | null
  created_at: string
  searched_meetings?: number
  time_filter?: string | null
}

export interface ActionBoardItem {
  id: string
  task: string
  owner_label: string
  due_text: string | null
  priority: 'low' | 'medium' | 'high'
  done: boolean
  quote_time: number | null
  meeting_id: string
  meeting_title: string
  meeting_date: string
}

export interface ActionBoard {
  items: ActionBoardItem[]
  total: number
  open_count: number
  done_count: number
  owners: { name: string; open: number }[]
}

export interface FollowUpDraft {
  subject: string
  body: string
  tone: string
}

// --- Insights ----------------------------------------------------------------

export interface DecisionItem {
  id: string
  decision: string
  made_by: string
  topic: string
  status: 'decided' | 'reversed'
  quote: string
  meeting_id: string
  meeting_title: string
  meeting_date: string
}

export interface DecisionBoard {
  items: DecisionItem[]
  total: number
  topics: { topic: string; count: number }[]
}

export interface ContradictionItem {
  topic: string
  explanation: string
  earlier: DecisionItem
  later: DecisionItem
}

export interface ContradictionBoard {
  items: ContradictionItem[]
  total: number
  checked_decisions: number
}

export interface BlindSpotFinding {
  category: string
  concern: string
  question: string
}

export interface BlindSpotReport {
  meeting_id: string
  headline: string
  findings: BlindSpotFinding[]
}

export interface TimelineEvent {
  date: string
  kind: 'meeting' | 'decision'
  title: string
  detail: string
  meeting_id: string
  meeting_title: string
  status: string | null
}

export interface TimelineResponse {
  events: TimelineEvent[]
  total: number
}

export interface GraphNode {
  id: string
  label: string
  kind: 'meeting' | 'person' | 'project' | 'client'
  weight: number
}

export interface GraphEdge {
  source: string
  target: string
}

export interface KnowledgeGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  meeting_count: number
  entity_count: number
}

export interface DigestMeeting {
  id: string
  title: string
  created_at: string
  duration_seconds: number
  open_action_count: number
}

export interface DigestResponse {
  generated_for: string
  is_today: boolean
  meeting_count: number
  meetings: DigestMeeting[]
  decisions: DecisionItem[]
  open_action_count: number
  priority_actions: ActionBoardItem[]
  narrative: string
  empty: boolean
}

export interface PrepResponse {
  meeting_id: string
  briefing: string
  related_meetings: { id: string; title: string }[]
}

export interface HealthResponse {
  status: string
  database: boolean
  llm: { provider: string; reachable: boolean; models: string[]; detail: string }
  whisper_model: string
  version: string
}

// --- Endpoints ---------------------------------------------------------------

export const api = {
  register: (payload: { email: string; full_name: string; password: string }) =>
    request<TokenResponse>('/api/auth/register', { method: 'POST', body: payload }),

  login: (payload: { email: string; password: string }) =>
    request<TokenResponse>('/api/auth/login', { method: 'POST', body: payload }),

  refresh: () => request<TokenResponse>('/api/auth/refresh', { method: 'POST', skipRetry: true }),

  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),

  me: () => request<User>('/api/auth/me'),

  sessions: () => request<SessionInfo[]>('/api/auth/sessions'),

  revokeAllSessions: () => request<void>('/api/auth/sessions/revoke-all', { method: 'POST' }),

  health: () => request<HealthResponse>('/api/health'),

  listMeetings: (search = '') =>
    request<MeetingListItem[]>(`/api/meetings${search ? `?search=${encodeURIComponent(search)}` : ''}`),

  getMeeting: (id: string) => request<MeetingDetail>(`/api/meetings/${id}`),

  getTranscript: (id: string) => request<TranscriptResponse>(`/api/meetings/${id}/transcript`),

  getAnalytics: (id: string) => request<MeetingAnalytics>(`/api/meetings/${id}/analytics`),

  getWorkspaceStats: () => request<WorkspaceStats>('/api/analytics/workspace'),

  renameMeeting: (id: string, title: string) =>
    request<MeetingDetail>(`/api/meetings/${id}`, { method: 'PATCH', body: { title } }),

  renameSpeaker: (meetingId: string, speakerId: string, displayName: string) =>
    request<Speaker>(`/api/meetings/${meetingId}/speakers/${speakerId}`, {
      method: 'PATCH',
      body: { display_name: displayName },
    }),

  toggleAction: (meetingId: string, actionId: string, done: boolean) =>
    request<ActionItem>(`/api/meetings/${meetingId}/actions/${actionId}`, {
      method: 'PATCH',
      body: { done },
    }),

  reprocess: (id: string) => request<{ id: string; message: string }>(`/api/meetings/${id}/reprocess`, { method: 'POST' }),

  deleteMeeting: (id: string) => request<void>(`/api/meetings/${id}`, { method: 'DELETE' }),

  getChatHistory: (id: string) => request<ChatMessage[]>(`/api/meetings/${id}/chat`),

  getChatSuggestions: (id: string) => request<string[]>(`/api/meetings/${id}/chat/suggestions`),

  ask: (id: string, question: string) =>
    request<{ answer: ChatMessage; suggestions: string[] }>(`/api/meetings/${id}/chat`, {
      method: 'POST',
      body: { question },
    }),

  clearChat: (id: string) => request<void>(`/api/meetings/${id}/chat`, { method: 'DELETE' }),

  // --- Cross-meeting memory ---
  getMemoryHistory: () => request<MemoryMessage[]>('/api/memory/history'),

  getMemorySuggestions: () => request<string[]>('/api/memory/suggestions'),

  askMemory: (question: string) =>
    request<MemoryMessage>('/api/memory', { method: 'POST', body: { question } }),

  clearMemory: () => request<void>('/api/memory', { method: 'DELETE' }),

  // --- Unified action board ---
  getActionBoard: (show: 'open' | 'done' | 'all' = 'open', owner = '') =>
    request<ActionBoard>(
      `/api/memory/actions?show=${show}${owner ? `&owner=${encodeURIComponent(owner)}` : ''}`,
    ),

  // --- AI follow-up email ---
  draftFollowUp: (meetingId: string, tone: string, note = '') =>
    request<FollowUpDraft>(`/api/memory/meetings/${meetingId}/followup`, {
      method: 'POST',
      body: { tone, note },
    }),

  // --- Insights ---
  getDecisions: () => request<DecisionBoard>('/api/insights/decisions'),

  getContradictions: () => request<ContradictionBoard>('/api/insights/contradictions'),

  getTimeline: () => request<TimelineResponse>('/api/insights/timeline'),

  getKnowledgeGraph: () => request<KnowledgeGraph>('/api/insights/graph'),

  getDigest: () => request<DigestResponse>('/api/insights/digest'),

  getBlindSpots: (meetingId: string) =>
    request<BlindSpotReport>(`/api/insights/meetings/${meetingId}/blindspots`),

  getMeetingPrep: (meetingId: string) =>
    request<PrepResponse>(`/api/insights/meetings/${meetingId}/prep`),

  /**
   * Download an .ics calendar file. Like exportMeeting, this uses fetch + Blob
   * rather than a plain navigation because the endpoint needs the Authorization
   * header — a bare <a href> could not send one and would just 401.
   */
  downloadCalendar: async (meetingId?: string): Promise<{ filename: string }> => {
    const path = meetingId
      ? `/api/insights/meetings/${meetingId}/calendar.ics`
      : '/api/insights/calendar.ics'
    const res = await fetch(path, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      credentials: 'include',
    })

    if (res.status === 401) {
      const refreshed = await refreshAccessToken()
      if (refreshed) return api.downloadCalendar(meetingId)
      onAuthLost?.()
      throw new ApiError('Your session has expired. Please sign in again.', 401)
    }
    if (!res.ok) throw new ApiError(await parseError(res), res.status)

    const blob = await res.blob()
    const filename = meetingId ? `${meetingId}.ics` : 'meetmind.ics'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    return { filename }
  },

  listEmails: (id: string) => request<EmailDelivery[]>(`/api/meetings/${id}/email`),

  sendEmail: (id: string, payload: { recipients: string[]; include_transcript: boolean; note: string }) =>
    request<EmailDelivery>(`/api/meetings/${id}/email`, { method: 'POST', body: payload }),

  /**
   * Download an export. Uses fetch + Blob rather than pointing window.location at
   * the URL, because the export endpoint needs the Authorization header and a
   * plain navigation cannot send one - it would just 401.
   */
  // The explicit return type is required, not cosmetic: this function calls
  // itself on a 401 retry, so TypeScript cannot infer the type without it.
  exportMeeting: async (
    id: string,
    format: 'pdf' | 'docx',
    includeTranscript: boolean,
  ): Promise<{ filename: string; size: number }> => {
    const res = await fetch(
      `/api/meetings/${id}/export?format=${format}&include_transcript=${includeTranscript}`,
      {
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
        credentials: 'include',
      },
    )

    if (res.status === 401) {
      // Mirror the retry that `request` does, so a download never fails just
      // because the access token aged out while the user was reading.
      const refreshed = await refreshAccessToken()
      if (refreshed) return api.exportMeeting(id, format, includeTranscript)
      onAuthLost?.()
      throw new ApiError('Your session has expired. Please sign in again.', 401)
    }
    if (!res.ok) throw new ApiError(await parseError(res), res.status)

    const blob = await res.blob()

    // Prefer the server's filename - it already handles unsafe characters.
    const disposition = res.headers.get('Content-Disposition') ?? ''
    const match = /filename="([^"]+)"/.exec(disposition)
    const filename = match?.[1] ?? `meeting.${format}`

    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    // Revoke on the next tick: revoking synchronously can cancel the download
    // in some browsers before it has started reading the blob.
    setTimeout(() => URL.revokeObjectURL(url), 1000)

    return { filename, size: blob.size }
  },

  uploadMeeting: (file: File, title: string, source: 'upload' | 'recording', onProgress?: (pct: number) => void) => {
    // XHR rather than fetch: fetch still cannot report upload progress, and a
    // 200MB upload with no progress bar feels broken.
    return new Promise<{ id: string; title: string; status: string; message: string }>((resolve, reject) => {
      const form = new FormData()
      form.append('file', file)
      form.append('title', title)
      form.append('source', source)

      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/meetings')
      xhr.withCredentials = true
      if (accessToken) xhr.setRequestHeader('Authorization', `Bearer ${accessToken}`)

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText))
          } catch {
            reject(new ApiError('The server returned a malformed response.', xhr.status))
          }
        } else {
          let message = `Upload failed (${xhr.status})`
          try {
            const parsed = JSON.parse(xhr.responseText)
            if (typeof parsed?.detail === 'string') message = parsed.detail
          } catch {
            /* keep default */
          }
          reject(new ApiError(message, xhr.status))
        }
      }

      xhr.onerror = () => reject(new ApiError('Network error during upload.', 0))
      xhr.onabort = () => reject(new ApiError('Upload cancelled.', 0))
      xhr.send(form)
    })
  },
}
