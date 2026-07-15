import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { formatDuration } from '../lib/format'
import { IconPause, IconPlay } from './Icons'

export interface AudioPlayerHandle {
  seekTo: (seconds: number) => void
  getCurrentTime: () => number
}

interface Props {
  src: string
  duration: number
  onTimeUpdate?: (seconds: number) => void
}

const SPEEDS = [1, 1.25, 1.5, 2]

/**
 * Audio player over the signed media URL.
 *
 * The backend supports HTTP range requests, so seeking works properly rather
 * than re-downloading the file. `duration` is passed in from the meeting record
 * because WebM recordings produced by MediaRecorder often report Infinity for
 * their own duration - a well-known browser quirk that would otherwise leave the
 * scrubber unusable on exactly the recordings this app creates.
 */
const AudioPlayer = forwardRef<AudioPlayerHandle, Props>(({ src, duration, onTimeUpdate }, ref) => {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [current, setCurrent] = useState(0)
  const [speed, setSpeed] = useState(1)
  const [error, setError] = useState('')
  const [ready, setReady] = useState(false)

  const total = duration > 0 && Number.isFinite(duration) ? duration : 0

  useImperativeHandle(ref, () => ({
    seekTo: (seconds: number) => {
      const el = audioRef.current
      if (!el) return
      el.currentTime = Math.max(0, total > 0 ? Math.min(seconds, total) : seconds)
      setCurrent(el.currentTime)
      void el.play().then(() => setPlaying(true)).catch(() => {
        /* autoplay policy - the user can press play */
      })
    },
    getCurrentTime: () => audioRef.current?.currentTime ?? 0,
  }))

  useEffect(() => {
    const el = audioRef.current
    if (!el) return

    const onTime = () => {
      setCurrent(el.currentTime)
      onTimeUpdate?.(el.currentTime)
    }
    const onEnd = () => setPlaying(false)
    const onErr = () => setError('Could not load the audio. The link may have expired - refresh the page.')
    const onReady = () => {
      setReady(true)
      setError('')
    }

    el.addEventListener('timeupdate', onTime)
    el.addEventListener('ended', onEnd)
    el.addEventListener('error', onErr)
    el.addEventListener('loadedmetadata', onReady)
    el.addEventListener('canplay', onReady)

    return () => {
      el.removeEventListener('timeupdate', onTime)
      el.removeEventListener('ended', onEnd)
      el.removeEventListener('error', onErr)
      el.removeEventListener('loadedmetadata', onReady)
      el.removeEventListener('canplay', onReady)
    }
  }, [onTimeUpdate])

  const toggle = async () => {
    const el = audioRef.current
    if (!el) return
    if (playing) {
      el.pause()
      setPlaying(false)
    } else {
      try {
        await el.play()
        setPlaying(true)
      } catch {
        setError('Playback was blocked by the browser. Click play again.')
      }
    }
  }

  const cycleSpeed = () => {
    const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length] ?? 1
    setSpeed(next)
    if (audioRef.current) audioRef.current.playbackRate = next
  }

  const scrub = (e: React.ChangeEvent<HTMLInputElement>) => {
    const el = audioRef.current
    if (!el) return
    const t = Number(e.target.value)
    el.currentTime = t
    setCurrent(t)
  }

  const pct = total > 0 ? (current / total) * 100 : 0

  return (
    <div className="card card-pad stack gap-3">
      <audio ref={audioRef} src={src} preload="metadata" />

      {error ? (
        <span style={{ fontSize: 12.5, color: '#fca5a5' }}>{error}</span>
      ) : (
        <div className="row gap-3">
          <button
            className="btn btn-primary btn-icon"
            onClick={toggle}
            disabled={!ready && !playing}
            aria-label={playing ? 'Pause' : 'Play'}
            style={{ width: 36, height: 36, borderRadius: 99, flexShrink: 0 }}
          >
            {playing ? <IconPause size={14} /> : <IconPlay size={14} />}
          </button>

          <div className="stack gap-1 grow" style={{ minWidth: 0 }}>
            <input
              type="range"
              min={0}
              max={total || 100}
              step={0.1}
              value={current}
              onChange={scrub}
              disabled={!total}
              aria-label="Seek"
              style={{
                width: '100%',
                height: 4,
                borderRadius: 99,
                appearance: 'none',
                background: `linear-gradient(90deg, var(--accent) ${pct}%, var(--surface-3) ${pct}%)`,
                cursor: total ? 'pointer' : 'default',
                outline: 'none',
              }}
            />
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span className="mono" style={{ fontSize: 10.5, color: 'var(--text-tertiary)' }}>
                {formatDuration(current)}
              </span>
              <span className="mono" style={{ fontSize: 10.5, color: 'var(--text-quaternary)' }}>
                {formatDuration(total)}
              </span>
            </div>
          </div>

          <button
            className="btn btn-secondary btn-sm mono"
            onClick={cycleSpeed}
            style={{ flexShrink: 0, minWidth: 44 }}
            title="Playback speed"
          >
            {speed}×
          </button>
        </div>
      )}

      <style>{`
        input[type='range']::-webkit-slider-thumb {
          appearance: none;
          width: 12px;
          height: 12px;
          border-radius: 99px;
          background: #fff;
          cursor: pointer;
          box-shadow: 0 1px 4px rgba(0,0,0,0.5);
          transition: transform 120ms;
        }
        input[type='range']::-webkit-slider-thumb:hover { transform: scale(1.18); }
        input[type='range']::-moz-range-thumb {
          width: 12px; height: 12px; border: none; border-radius: 99px;
          background: #fff; cursor: pointer;
        }
      `}</style>
    </div>
  )
})

AudioPlayer.displayName = 'AudioPlayer'
export default AudioPlayer
