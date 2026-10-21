import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { errorMessage } from './errors'
import { isFinished } from './status'
import type { Review, Run } from './types'

const POLL_MS = 2000

interface RunState {
  runId: string | null
  run: Run | null
  review: Review | null
  error: string | null
}

const EMPTY: RunState = { runId: null, run: null, review: null, error: null }

// Follow one run until it finishes, loading its review when it succeeds
export function useRun(runId: string | null, onFinished?: () => void): RunState {
  const [state, setState] = useState<RunState>(EMPTY)
  const finished = useRef(onFinished)
  useEffect(() => {
    finished.current = onFinished
  })

  useEffect(() => {
    if (!runId) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    async function poll() {
      try {
        const run = await api.getRun(runId as string)
        if (cancelled) return
        const review = run.status === 'succeeded' ? await api.getReview(run.id) : null
        if (cancelled) return
        setState({ runId, run, review, error: null })
        if (isFinished(run.status)) finished.current?.()
        else timer = setTimeout(poll, POLL_MS)
      } catch (e) {
        if (!cancelled) setState((current) => ({ ...current, runId, error: errorMessage(e) }))
      }
    }

    void poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [runId])

  // State belonging to a different run is never shown
  return state.runId === runId ? state : EMPTY
}
