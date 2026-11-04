import { RotateCw } from 'lucide-react'
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

// Run the deck again from the review screen, or open an earlier run of it
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
      label="Run again"
      icon={<RotateCw aria-hidden className="h-4 w-4" />}
      buttonClassName="border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 data-[state=open]:bg-slate-100"
    >
      <div className="space-y-5">
        <TranslateForm
          projectId={projectId}
          file={file}
          compact
          onStarted={(run) => {
            setOpen(false)
            onStarted(run)
          }}
        />
        {earlier.length > 0 && (
          <div className="border-t border-slate-200 pt-4">
            <p className="mb-2 text-sm font-semibold text-slate-800">Earlier runs</p>
            <ul className="-mx-2">
              {earlier.map((run) => (
                <li key={run.id}>
                  <Link
                    to={editorPath(projectId, file, run.id)}
                    onClick={() => setOpen(false)}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-slate-100"
                  >
                    <span className="flex items-center gap-2">
                      <RunStatusBadge status={run.status} />
                      <span className="capitalize text-slate-700">{run.effort}</span>
                    </span>
                    <span className="text-slate-600">
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
