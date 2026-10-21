import { Languages } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import { errorMessage } from '../errors'
import type { Effort, Run } from '../types'
import { cx } from './classes'
import { Alert, Button } from './ui'

const EFFORTS: { value: Exclude<Effort, 'baseline'>; label: string; hint: string }[] = [
  { value: 'low', label: 'Low', hint: 'Quick pass' },
  { value: 'medium', label: 'Medium', hint: 'Balanced' },
  { value: 'high', label: 'High', hint: 'Most thorough' },
]

interface Props {
  projectId: string
  file: string
  onStarted: (run: Run) => void
}

export default function TranslateForm({ projectId, file, onStarted }: Props) {
  const [effort, setEffort] = useState<Effort>('medium')
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
    <div className="space-y-3">
      <fieldset>
        <legend className="text-xs font-medium uppercase tracking-wide text-slate-400">Effort</legend>
        <div className="mt-1 grid grid-cols-3 gap-1.5">
          {EFFORTS.map((option) => (
            <label
              key={option.value}
              className={cx(
                'cursor-pointer rounded-lg border px-2 py-1.5 text-center text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand-600',
                effort === option.value
                  ? 'border-brand-600 bg-brand-50 ring-1 ring-brand-600'
                  : 'border-slate-200 bg-white hover:border-slate-300',
              )}
            >
              <input
                type="radio"
                name={`effort-${file}`}
                value={option.value}
                checked={effort === option.value}
                onChange={() => setEffort(option.value)}
                className="sr-only"
              />
              <span className="block font-medium text-slate-900">{option.label}</span>
              <span className="block text-xs text-slate-500">{option.hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <details className="text-sm">
        <summary className="font-medium text-slate-500 hover:text-slate-800">Demo options</summary>
        <label className="mt-2 block text-slate-700">
          Seed a weak description for element
          <input
            value={seedWeak}
            onChange={(event) => setSeedWeak(event.target.value)}
            placeholder="slide_04/figure_01"
            className="mt-1 block w-full rounded-lg border border-slate-300 px-2.5 py-1.5 font-mono text-sm placeholder:text-slate-400"
          />
          <span className="mt-1 block text-xs text-slate-500">
            Forces a poor first description so you can watch the repair loop fix it.
          </span>
        </label>
      </details>

      {error && <Alert tone="danger">{error}</Alert>}
      <Button
        variant="primary"
        className="w-full"
        loading={starting}
        onClick={() => void start()}
        icon={<Languages aria-hidden className="h-4 w-4" />}
      >
        Translate
      </Button>
    </div>
  )
}
