import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api, setAccessToken, setAuthLostHandler, type User } from '../lib/api'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, fullName: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const refreshTimer = useRef<number | null>(null)

  const clearTimer = useCallback(() => {
    if (refreshTimer.current !== null) {
      window.clearTimeout(refreshTimer.current)
      refreshTimer.current = null
    }
  }, [])

  /**
   * Refresh proactively at 75% of the token's life rather than waiting for a
   * 401. The reactive path in api.ts still exists as a safety net, but a user
   * mid-demo should never see a request stall while a token is swapped.
   */
  const scheduleRefresh = useCallback(
    (expiresIn: number) => {
      clearTimer()
      const delay = Math.max(30_000, expiresIn * 1000 * 0.75)
      refreshTimer.current = window.setTimeout(async () => {
        try {
          const res = await api.refresh()
          setAccessToken(res.access_token)
          setUser(res.user)
          scheduleRefresh(res.expires_in)
        } catch {
          setAccessToken(null)
          setUser(null)
        }
      }, delay)
    },
    [clearTimer],
  )

  // On boot, try the refresh cookie. This is what makes a page reload keep you
  // signed in without ever putting a token in localStorage.
  useEffect(() => {
    let cancelled = false

    ;(async () => {
      try {
        const res = await api.refresh()
        if (cancelled) return
        setAccessToken(res.access_token)
        setUser(res.user)
        scheduleRefresh(res.expires_in)
      } catch {
        if (!cancelled) {
          setAccessToken(null)
          setUser(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [scheduleRefresh])

  // If a refresh fails anywhere in the app, drop to signed-out cleanly rather
  // than leaving a half-authenticated UI making failing requests.
  useEffect(() => {
    setAuthLostHandler(() => {
      clearTimer()
      setAccessToken(null)
      setUser(null)
    })
    return () => setAuthLostHandler(null)
  }, [clearTimer])

  useEffect(() => clearTimer, [clearTimer])

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api.login({ email, password })
      setAccessToken(res.access_token)
      setUser(res.user)
      scheduleRefresh(res.expires_in)
    },
    [scheduleRefresh],
  )

  const register = useCallback(
    async (email: string, fullName: string, password: string) => {
      const res = await api.register({ email, full_name: fullName, password })
      setAccessToken(res.access_token)
      setUser(res.user)
      scheduleRefresh(res.expires_in)
    },
    [scheduleRefresh],
  )

  const logout = useCallback(async () => {
    clearTimer()
    try {
      await api.logout()
    } catch {
      // Even if the server call fails, the local session must end.
    }
    setAccessToken(null)
    setUser(null)
  }, [clearTimer])

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
