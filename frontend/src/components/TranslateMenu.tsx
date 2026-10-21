import { Languages, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { errorMessage } from '../errors'
import { formatCost, relativeTime } from '../format'
import type { Effort, Run } from '../types'
import { cx } from './classes'
import Popover from './Popover'
import { Alert, Button, RunStatusBadge } from './ui'

const EFFORTS: { value: Exclude<Effort, 'baseline'>; label: string; hint: string }[] = [
  { value: 'low', label: 'Low', hint: 'Quick' },
  { value: 'medium', label: 'Medium', hint: 'Balanced' },
  { value: 'high', label: 'High', hint: 'Thorough' },
]

interface Props {
  projectId: string
  targets: string[]
  runs: Run[]
  latestByFile: Map<string, Run>
  currentFile: string
  // A file the user asked to translate from the file list
  requestedFile: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function TranslateMenu({
  projectId,
  targets,
  runs,
  latestByFile,
  currentFile,
  requestedFile,
  open,
  onOpenChange,
}: Props) {
  const navigate = useNavigate()
  const [file, setFile] = useState(requestedFile ?? currentFile)
  const [lastRequested, setLastRequested] = useState(requestedFile)
  const [effort, setEffort] = useState<Effort>('medium')
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Follow a file chosen in the file list, adjusting during render rather than in an effect
  if (requestedFile !== lastRequested) {
    setLastRequested(requestedFile)
    if (requestedFile) setFile(requestedFile)
  }

  const translated = latestByFile.has(file)
  const earlier = runs
    .filter((run) => run.main_file === file)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 4)
  const options = targets.includes(currentFile) ? targets : [currentFile, ...targets]

  async function start() {
    setStarting(true)
    try {
      const run = await api.createRun(projectId, { effort, main_file: file })
      onOpenChange(false)
      navigate(`/runs/${run.id}`)
    } catch (e) {
      setError(errorMessage(e))
      setStarting(false)
    }
  }

  return (
    <Popover
      open={open}
      onOpenChange={onOpenChange}
      width="w-80"
      label={file === currentFile ? 'Re-translate' : 'Translate'}
      icon={file === currentFile ? <RefreshCw aria-hidden className="h-4 w-4" /> : <Languages aria-hidden className="h-4 w-4" />}
      buttonClassName="border border-slate-300 bg-white text-slate-800 shadow-sm hover:bg-slate-50"
    >
      <div className="space-y-3">
        <label className="block">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-400">File</span>
          <select
            value={file}
            onChange={(event) => setFile(event.target.value)}
            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 font-mono text-sm"
          >
            {options.map((option) => {
              const latest = latestByFile.get(option)
              return (
                <option key={option} value={option}>
                  {option}
                  {latest ? (latest.a_score !== null ? ` · A ${latest.a_score.toFixed(0)}` : ` · ${latest.status}`) : ' · not translated'}
                </option>
              )
            })}
          </select>
        </label>

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
                    : 'border-slate-200 hover:border-slate-300',
                )}
              >
                <input
                  type="radio"
                  name="translate-effort"
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

        {error && <Alert tone="danger">{error}</Alert>}
        <Button variant="primary" className="w-full" loading={starting} onClick={() => void start()}>
          {translated ? 'Re-translate this file' : 'Translate this file'}
        </Button>

        {earlier.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">Earlier runs of this file</p>
            <ul className="-mx-1">
              {earlier.map((run) => (
                <li key={run.id}>
                  <Link
                    to={`/runs/${run.id}`}
                    onClick={() => onOpenChange(false)}
                    className="flex items-center justify-between gap-2 rounded-md px-1 py-1 text-sm hover:bg-slate-50"
                  >
                    <span className="flex items-center gap-2">
                      <RunStatusBadge status={run.status} />
                      <span className="capitalize text-slate-500">{run.effort}</span>
                    </span>
                    <span className="text-xs text-slate-400">
                      {run.a_score !== null ? `A ${run.a_score.toFixed(0)} · ` : ''}
                      {formatCost(run.cost_usd)} · {relativeTime(run.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Popover>
  )
}
