import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { IconAlert, IconCheckCircle, IconSparkle, IconX } from '../components/Icons'

type ToastKind = 'success' | 'error' | 'info'

interface Toast {
  id: number
  kind: ToastKind
  message: string
  leaving?: boolean
}

interface ToastApi {
  success: (message: string) => void
  error: (message: string) => void
  info: (message: string) => void
}

const ToastContext = createContext<ToastApi | null>(null)

// Errors stay longer: the user needs time to actually read what went wrong.
const DURATION: Record<ToastKind, number> = { success: 3200, error: 6500, info: 4200 }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const remove = useCallback((id: number) => {
    // Mark leaving first so the exit animation runs, then unmount.
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)))
    window.setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 180)
  }, [])

  const push = useCallback(
    (kind: ToastKind, message: string) => {
      const id = nextId.current++
      // Cap the stack so a burst of errors can't cover the whole screen.
      setToasts((prev) => [...prev.slice(-3), { id, kind, message }])
      window.setTimeout(() => remove(id), DURATION[kind])
    },
    [remove],
  )

  const value = useMemo<ToastApi>(
    () => ({
      success: (m: string) => push('success', m),
      error: (m: string) => push('error', m),
      info: (m: string) => push('info', m),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}${t.leaving ? ' leaving' : ''}`}>
            <span
              style={{
                color:
                  t.kind === 'success'
                    ? 'var(--success)'
                    : t.kind === 'error'
                      ? 'var(--danger)'
                      : 'var(--accent-bright)',
                flexShrink: 0,
                marginTop: 1,
              }}
            >
              {t.kind === 'success' ? (
                <IconCheckCircle size={15} />
              ) : t.kind === 'error' ? (
                <IconAlert size={15} />
              ) : (
                <IconSparkle size={15} />
              )}
            </span>
            <span className="grow">{t.message}</span>
            <button
              className="btn-ghost"
              onClick={() => remove(t.id)}
              aria-label="Dismiss notification"
              style={{ color: 'var(--text-quaternary)', padding: 2, borderRadius: 4 }}
            >
              <IconX size={13} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
