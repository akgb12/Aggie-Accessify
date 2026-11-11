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
  // The file's current version, which the run starts from
  version?: number | null
}

export default function TranslateForm({ projectId, file, onStarted, compact = false, version = null }: Props) {
  const { preferences } = useUser()
  const [effort, setEffort] = useState<DefaultEffort>(preferences.default_effort)
  const [seedWeak, setSeedWeak] = useState('')
  const [fresh, setFresh] = useState(false)
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
        fresh,
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

      <label className="flex items-start gap-2.5 text-sm text-slate-800">
        <input
          type="checkbox"
          checked={fresh}
          onChange={(event) => setFresh(event.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-400 accent-brand-800"
        />
        <span>
          Write every description from scratch
          <span className="block text-slate-600">
            Off: answers from earlier runs of this deck are reused, so you pay only for what changed.
          </span>
        </span>
      </label>

      {version !== null && (
        <p className="text-sm text-slate-600">
          Starts from version {version}, the current version of this file, so changes you uploaded are kept.
        </p>
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
