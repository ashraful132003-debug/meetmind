import { useEffect, useState } from 'react'
import { api } from './api'

/**
 * Whether this build keeps audio on the machine (Ollama + local Whisper) or
 * sends it to a hosted provider (Groq on the deployed demo).
 *
 * The privacy copy in the UI is only true for the first case, so it should only
 * be shown once the backend has confirmed it. Until then, and if the call fails,
 * the answer is 'hosted' - the wording that is safe in both cases.
 */
export type DeployMode = 'local' | 'hosted'

let cached: Promise<DeployMode> | null = null

function detect(): Promise<DeployMode> {
  if (!cached) {
    cached = api
      .health()
      .then((h) => (h.llm.provider === 'ollama' ? 'local' : 'hosted') as DeployMode)
      .catch(() => {
        cached = null
        return 'hosted' as DeployMode
      })
  }
  return cached
}

export function useDeployMode(): DeployMode {
  const [mode, setMode] = useState<DeployMode>('hosted')

  useEffect(() => {
    let cancelled = false
    detect().then((m) => {
      if (!cancelled) setMode(m)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return mode
}
