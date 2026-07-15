import { useCallback, useEffect, useRef, useState } from 'react'
import { useToast } from '../context/ToastContext'
import { ApiError, api } from '../lib/api'
import { formatBytes, formatDuration } from '../lib/format'
import { IconAlert, IconFile, IconMic, IconUpload, IconX } from './Icons'

type Mode = 'record' | 'upload'

const ACCEPTED = '.wav,.mp3,.m4a,.mp4,.webm,.ogg,.flac,.aac'
const MAX_MB = 200
const WAVE_BARS = 36

interface Props {
  onClose: () => void
  onCreated: (meetingId: string) => void
}

/**
 * Records from the microphone or accepts a file, then uploads to the real
 * pipeline. Both paths land on the same endpoint and are processed identically -
 * a recording is not a special case, it is just an upload with a generated name.
 */
export default function NewMeetingModal({ onClose, onCreated }: Props) {
  const toast = useToast()
  const [mode, setMode] = useState<Mode>('record')
  const [title, setTitle] = useState('')

  const [recording, setRecording] = useState(false)
  const [paused, setPaused] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [levels, setLevels] = useState<number[]>(() => new Array(WAVE_BARS).fill(3))
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null)
  const [micError, setMicError] = useState('')

  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [fileError, setFileError] = useState('')

  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)

  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const stream = useRef<MediaStream | null>(null)
  const audioCtx = useRef<AudioContext | null>(null)
  const analyser = useRef<AnalyserNode | null>(null)
  const rafId = useRef<number | null>(null)
  const timerId = useRef<number | null>(null)

  /** Release the mic, the audio graph, and every timer. Called on stop AND on
   *  unmount - a forgotten getUserMedia stream leaves the browser's recording
   *  indicator on, which looks exactly like spyware. */
  const teardown = useCallback(() => {
    if (rafId.current !== null) cancelAnimationFrame(rafId.current)
    rafId.current = null

    if (timerId.current !== null) window.clearInterval(timerId.current)
    timerId.current = null

    stream.current?.getTracks().forEach((t) => t.stop())
    stream.current = null

    if (audioCtx.current && audioCtx.current.state !== 'closed') {
      void audioCtx.current.close()
    }
    audioCtx.current = null
    analyser.current = null
  }, [])

  useEffect(() => teardown, [teardown])

  const drawLevels = useCallback(() => {
    const node = analyser.current
    if (!node) return

    const data = new Uint8Array(node.frequencyBinCount)
    node.getByteFrequencyData(data)

    // Sample across the spectrum rather than showing raw bins - a linear slice
    // of an FFT is mostly empty at the top and looks dead.
    const next: number[] = []
    const step = Math.floor(data.length / WAVE_BARS) || 1
    for (let i = 0; i < WAVE_BARS; i++) {
      let sum = 0
      for (let j = 0; j < step; j++) sum += data[i * step + j] ?? 0
      const avg = sum / step
      next.push(Math.max(3, Math.min(48, (avg / 255) * 48 * 1.7)))
    }
    setLevels(next)
    rafId.current = requestAnimationFrame(drawLevels)
  }, [])

  const startRecording = async () => {
    setMicError('')
    setRecordedBlob(null)

    if (!navigator.mediaDevices?.getUserMedia) {
      setMicError('This browser does not support microphone recording. Try Chrome or Edge, or upload a file instead.')
      return
    }

    try {
      const s = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      })
      stream.current = s

      const ctx = new AudioContext()
      audioCtx.current = ctx
      const source = ctx.createMediaStreamSource(s)
      const node = ctx.createAnalyser()
      node.fftSize = 256
      node.smoothingTimeConstant = 0.75
      source.connect(node)
      analyser.current = node

      // Pick a container the browser actually supports rather than assuming.
      const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
      const mimeType = candidates.find((t) => MediaRecorder.isTypeSupported(t)) ?? ''

      const recorder = new MediaRecorder(s, mimeType ? { mimeType, audioBitsPerSecond: 128_000 } : undefined)
      chunks.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunks.current, { type: mimeType || 'audio/webm' })
        setRecordedBlob(blob)
        teardown()
      }
      recorder.onerror = () => {
        setMicError('Recording stopped unexpectedly. Please try again.')
        teardown()
        setRecording(false)
      }

      recorder.start(1000)
      mediaRecorder.current = recorder

      setRecording(true)
      setPaused(false)
      setElapsed(0)
      timerId.current = window.setInterval(() => setElapsed((v) => v + 1), 1000)
      rafId.current = requestAnimationFrame(drawLevels)
    } catch (err) {
      const name = (err as DOMException)?.name
      if (name === 'NotAllowedError') {
        setMicError('Microphone access was denied. Allow it in your browser settings, then try again.')
      } else if (name === 'NotFoundError') {
        setMicError('No microphone was found. Plug one in, or upload a file instead.')
      } else {
        setMicError('Could not start recording. Check that no other app is using the microphone.')
      }
    }
  }

  const togglePause = () => {
    const rec = mediaRecorder.current
    if (!rec) return

    if (rec.state === 'recording') {
      rec.pause()
      setPaused(true)
      if (timerId.current !== null) window.clearInterval(timerId.current)
      if (rafId.current !== null) cancelAnimationFrame(rafId.current)
      setLevels(new Array(WAVE_BARS).fill(3))
    } else if (rec.state === 'paused') {
      rec.resume()
      setPaused(false)
      timerId.current = window.setInterval(() => setElapsed((v) => v + 1), 1000)
      rafId.current = requestAnimationFrame(drawLevels)
    }
  }

  const stopRecording = () => {
    if (mediaRecorder.current?.state !== 'inactive') mediaRecorder.current?.stop()
    setRecording(false)
    setPaused(false)
  }

  const discardRecording = () => {
    setRecordedBlob(null)
    setElapsed(0)
    setLevels(new Array(WAVE_BARS).fill(3))
  }

  const validateFile = (f: File): string => {
    const ext = '.' + (f.name.split('.').pop() ?? '').toLowerCase()
    if (!ACCEPTED.split(',').includes(ext)) {
      return `${ext || 'That file type'} isn't supported. Use ${ACCEPTED.replace(/\./g, '').replace(/,/g, ', ')}.`
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      return `That file is ${formatBytes(f.size)}. The limit is ${MAX_MB}MB.`
    }
    if (f.size === 0) return 'That file is empty.'
    return ''
  }

  const pickFile = (f: File | undefined) => {
    if (!f) return
    const err = validateFile(f)
    setFileError(err)
    setFile(err ? null : f)
    if (!err && !title.trim()) {
      setTitle(f.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').slice(0, 200))
    }
  }

  const canSubmit = mode === 'record' ? !!recordedBlob : !!file

  const handleSubmit = async () => {
    if (uploading || !canSubmit) return

    const payload =
      mode === 'record' && recordedBlob
        ? new File([recordedBlob], `recording-${Date.now()}.webm`, { type: recordedBlob.type || 'audio/webm' })
        : file

    if (!payload) return

    setUploading(true)
    setProgress(0)
    try {
      const res = await api.uploadMeeting(payload, title.trim(), mode === 'record' ? 'recording' : 'upload', setProgress)
      toast.success('Upload complete. Processing has started.')
      onCreated(res.id)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Upload failed. Please try again.')
      setUploading(false)
    }
  }

  const handleClose = () => {
    if (uploading) return
    if (recording) stopRecording()
    teardown()
    onClose()
  }

  // Escape closes, but never mid-upload - losing a 200MB upload to a stray
  // keypress would be infuriating.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !uploading) handleClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && handleClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="new-meeting-title">
        <div className="modal-header">
          <div className="row gap-3" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div className="stack gap-1">
              <h2 id="new-meeting-title" style={{ fontSize: 17 }}>
                New meeting
              </h2>
              <p style={{ fontSize: 12.5, color: 'var(--text-tertiary)' }}>
                Everything is processed on this machine.
              </p>
            </div>
            <button className="btn btn-icon btn-ghost" onClick={handleClose} disabled={uploading} aria-label="Close">
              <IconX size={15} />
            </button>
          </div>

          <div className="tabs" style={{ marginTop: 14 }}>
            <button
              className={`tab${mode === 'record' ? ' active' : ''}`}
              onClick={() => setMode('record')}
              disabled={uploading || recording}
            >
              <IconMic size={13} /> Record
            </button>
            <button
              className={`tab${mode === 'upload' ? ' active' : ''}`}
              onClick={() => setMode('upload')}
              disabled={uploading || recording}
            >
              <IconUpload size={13} /> Upload
            </button>
          </div>
        </div>

        <div className="modal-body stack gap-4">
          {mode === 'record' ? (
            <div className="stack gap-4">
              <div
                className="stack gap-3"
                style={{
                  padding: '18px 16px',
                  borderRadius: 'var(--radius-lg)',
                  background: 'var(--surface-1)',
                  border: '1px solid var(--border-subtle)',
                  alignItems: 'center',
                }}
              >
                <div className="waveform" aria-hidden>
                  {levels.map((h, i) => (
                    <div
                      key={i}
                      className="wave-bar"
                      style={{
                        height: `${h}px`,
                        opacity: recording && !paused ? 0.45 + (h / 48) * 0.55 : 0.22,
                      }}
                    />
                  ))}
                </div>

                <div className="row gap-2">
                  {recording && !paused && <span className="rec-dot" />}
                  <span className="mono" style={{ fontSize: 21, fontWeight: 600, letterSpacing: '-0.02em' }}>
                    {formatDuration(elapsed)}
                  </span>
                </div>

                <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                  {recordedBlob
                    ? `Recorded · ${formatBytes(recordedBlob.size)}`
                    : recording
                      ? paused
                        ? 'Paused'
                        : 'Recording...'
                      : 'Ready to record'}
                </span>
              </div>

              {micError && (
                <div
                  className="row gap-2"
                  style={{
                    padding: '10px 12px',
                    borderRadius: 'var(--radius-sm)',
                    background: 'var(--danger-glow)',
                    border: '1px solid rgba(239,68,68,0.28)',
                    color: '#fca5a5',
                    fontSize: 12.5,
                    alignItems: 'flex-start',
                    lineHeight: 1.5,
                  }}
                  role="alert"
                >
                  <span style={{ flexShrink: 0, marginTop: 1 }}>
                    <IconAlert size={13} />
                  </span>
                  <span>{micError}</span>
                </div>
              )}

              <div className="row gap-2" style={{ justifyContent: 'center' }}>
                {!recording && !recordedBlob && (
                  <button className="btn btn-primary" onClick={startRecording} disabled={uploading}>
                    <IconMic size={14} /> Start recording
                  </button>
                )}
                {recording && (
                  <>
                    <button className="btn btn-secondary" onClick={togglePause}>
                      {paused ? 'Resume' : 'Pause'}
                    </button>
                    <button className="btn btn-danger" onClick={stopRecording}>
                      Stop
                    </button>
                  </>
                )}
                {recordedBlob && !recording && (
                  <button className="btn btn-secondary btn-sm" onClick={discardRecording} disabled={uploading}>
                    Discard and re-record
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="stack gap-3">
              <label
                className={`dropzone${dragging ? ' dragging' : ''}`}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setDragging(false)
                  pickFile(e.dataTransfer.files[0])
                }}
              >
                <input
                  type="file"
                  accept={ACCEPTED}
                  className="sr-only"
                  onChange={(e) => pickFile(e.target.files?.[0])}
                  disabled={uploading}
                />
                <div className="stack gap-2" style={{ alignItems: 'center' }}>
                  <div className="empty-icon" style={{ marginBottom: 0 }}>
                    {file ? <IconFile size={17} /> : <IconUpload size={17} />}
                  </div>
                  {file ? (
                    <>
                      <span style={{ fontSize: 13.5, fontWeight: 550 }} className="truncate">
                        {file.name}
                      </span>
                      <span style={{ fontSize: 11.5, color: 'var(--text-tertiary)' }}>
                        {formatBytes(file.size)} · click to choose a different file
                      </span>
                    </>
                  ) : (
                    <>
                      <span style={{ fontSize: 13.5, fontWeight: 550 }}>Drop an audio file, or click to browse</span>
                      <span style={{ fontSize: 11.5, color: 'var(--text-tertiary)' }}>
                        WAV, MP3, M4A, WEBM, OGG, FLAC · up to {MAX_MB}MB
                      </span>
                    </>
                  )}
                </div>
              </label>

              {fileError && (
                <span className="field-error">
                  <IconAlert size={12} /> {fileError}
                </span>
              )}
            </div>
          )}

          <div className="field">
            <label className="label" htmlFor="meeting-title">
              Title <span style={{ color: 'var(--text-quaternary)', fontWeight: 400 }}>(optional)</span>
            </label>
            <input
              id="meeting-title"
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Leave blank and the AI will name it"
              maxLength={200}
              disabled={uploading}
            />
          </div>

          {uploading && (
            <div className="stack gap-2">
              <div className="row" style={{ justifyContent: 'space-between', fontSize: 12 }}>
                <span style={{ color: 'var(--text-secondary)' }}>
                  {progress < 100 ? 'Uploading...' : 'Finishing up...'}
                </span>
                <span className="mono" style={{ color: 'var(--text-tertiary)' }}>
                  {progress}%
                </span>
              </div>
              <div className="progress-track">
                <div className="progress-fill active" style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={handleClose} disabled={uploading}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={!canSubmit || uploading}>
            {uploading && <span className="spinner" />}
            {uploading ? 'Uploading...' : 'Process meeting'}
          </button>
        </div>
      </div>
    </div>
  )
}
