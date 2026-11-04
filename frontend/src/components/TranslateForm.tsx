import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import { useUser } from '../authContext'
import { errorMessage } from '../errors'
import type { DefaultEffort, Run } from '../types'
import EffortPicker from './EffortPicker'
import { Alert, Button } from './ui'

interface Props {
  projectId: string
  file: string
  onStarted: (run: Run) => void
  compact?: boolean
}

export default function TranslateForm({ projectId, file, onStarted, compact = false }: Props) {
  const { preferences } = useUser()
  const [effort, setEffort] = useState<DefaultEffort>(preferences.default_effort)
  const [seedWeak, setSeedWeak] = useState('')
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function start() {
    setStarting(true)
    setError(null)
    try {
      const run = await api.createRun(projectId, {
        effort,
        main_file: file,
        seed_weak: seedWeak.trim() || null,
      })
      onStarted(run)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="space-y-4">
      <EffortPicker value={effort} onChange={setEffort} compact={compact} />

      {preferences.show_demo_options && (
        <details className="text-sm">
          <summary className="font-semibold text-slate-700 hover:text-slate-900">Demo options</summary>
          <label className="mt-2 block text-slate-800">
            Give this figure a weak first description
            <input
              value={seedWeak}
              onChange={(event) => setSeedWeak(event.target.value)}
              placeholder="slide_04/figure_01"
              className="mt-1.5 block h-9 w-full rounded-md border border-slate-300 px-2.5 font-mono text-sm placeholder:text-slate-400"
            />
            <span className="mt-1 block text-slate-600">
              Shows the repair loop fixing a poor description during the demo.
            </span>
          </label>
        </details>
      )}

      {error && <Alert tone="danger">{error}</Alert>}
      <Button
        variant="primary"
        className="h-10 w-full text-base"
        loading={starting}
        onClick={() => void start()}
        icon={<Sparkles aria-hidden className="h-4 w-4" />}
      >
        Make accessible
      </Button>
    </div>
  )
}
