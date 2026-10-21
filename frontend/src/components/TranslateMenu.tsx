import { Languages } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { editorPath } from '../editorState'
import { formatCost, relativeTime } from '../format'
import type { Run } from '../types'
import Popover from './Popover'
import TranslateForm from './TranslateForm'
import { RunStatusBadge } from './ui'

interface Props {
  projectId: string
  file: string
  runs: Run[]
  onStarted: (run: Run) => void
}

export default function TranslateMenu({ projectId, file, runs, onStarted }: Props) {
  const [open, setOpen] = useState(false)
  const earlier = runs
    .filter((run) => run.main_file === file)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 5)

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      width="w-80"
      label="Translate"
      icon={<Languages aria-hidden className="h-4 w-4" />}
      buttonClassName="bg-brand-800 text-white hover:bg-brand-700"
    >
      <div className="space-y-3">
        <p className="truncate font-mono text-sm font-medium text-slate-800" title={file}>
          {file}
        </p>
        <TranslateForm
          projectId={projectId}
          file={file}
          onStarted={(run) => {
            setOpen(false)
            onStarted(run)
          }}
        />
        {earlier.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">Earlier translations</p>
            <ul className="-mx-1">
              {earlier.map((run) => (
                <li key={run.id}>
                  <Link
                    to={editorPath(projectId, file, run.id)}
                    onClick={() => setOpen(false)}
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
