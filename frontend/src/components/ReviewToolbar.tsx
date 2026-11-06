import {
  CircleCheck,
  Download,
  FileArchive,
  FileDiff,
  FileText,
  Info,
  PanelRight,
  Presentation,
  TriangleAlert,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { artifactUrl } from '../api'
import { formatCost } from '../format'
import { outputHint, outputKind } from '../outputs'
import type { ReviewOutput, Run } from '../types'
import EditorToolbar, { PanelToggle } from './EditorToolbar'
import Popover from './Popover'

function outputIcon(path: string) {
  const className = 'mt-0.5 h-4 w-4 shrink-0 text-slate-600'
  switch (outputKind(path)) {
    case 'deck':
      return <Presentation aria-hidden className={className} />
    case 'document':
    case 'pdf':
    case 'report':
      return <FileText aria-hidden className={className} />
    case 'changes':
      return <FileDiff aria-hidden className={className} />
    case 'archive':
      return <FileArchive aria-hidden className={className} />
    default:
      return <Download aria-hidden className={className} />
  }
}

function score(value: number | null): string {
  return value === null ? 'Not available' : `${value.toFixed(1)} of 100`
}

// One plain status in place of raw scores: what the professor still has to look at
function ReviewStatus({ count }: { count: number }) {
  if (count === 0) {
    return (
      <span className="hidden items-center gap-1.5 text-sm font-semibold text-success md:flex">
        <CircleCheck aria-hidden className="h-4 w-4" />
        Nothing to review
      </span>
    )
  }
  return (
    <span className="hidden items-center gap-1.5 text-sm font-semibold text-warning md:flex">
      <TriangleAlert aria-hidden className="h-4 w-4" />
      {count} {count === 1 ? 'item' : 'items'} to review
    </span>
  )
}

interface Props {
  run: Run
  projectName: string
  renderEngine: string | null
  outputs: ReviewOutput[]
  updatingOutputs?: boolean
  attentionCount: number
  leftOpen: boolean
  rightOpen: boolean
  onToggleLeft: () => void
  onToggleRight: () => void
  translateSlot: ReactNode
}

export default function ReviewToolbar({
  run,
  projectName,
  renderEngine,
  outputs,
  updatingOutputs = false,
  attentionCount,
  leftOpen,
  rightOpen,
  onToggleLeft,
  onToggleRight,
  translateSlot,
}: Props) {
  return (
    <EditorToolbar projectName={projectName} file={run.main_file || null} leftOpen={leftOpen} onToggleLeft={onToggleLeft}>
      <ReviewStatus count={attentionCount} />
      <Popover label="Details" icon={<Info aria-hidden className="h-4 w-4" />} width="w-80">
        <h2 className="mb-3 font-semibold text-slate-900">About this run</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
          <dt className="text-slate-600">Accessibility score</dt>
          <dd className="tabular-nums">{score(run.a_score)}</dd>
          <dt className="text-slate-600">Unchanged look</dt>
          <dd className="tabular-nums">{score(run.f_score)}</dd>
          <dt className="text-slate-600">Effort</dt>
          <dd className="capitalize">{run.effort}</dd>
          <dt className="text-slate-600">Cost</dt>
          <dd className="tabular-nums">
            {formatCost(run.cost_usd)}
            {/* Saved answers from an earlier run are free, though their model use is still listed */}
            {Number(run.cost_usd) === 0 && run.input_tokens > 0 && run.model_provider !== 'fake' && (
              <span className="block text-sm text-slate-600">Reused saved answers from earlier runs</span>
            )}
          </dd>
          <dt className="text-slate-600">Model use</dt>
          <dd className="tabular-nums">
            {run.input_tokens.toLocaleString()} in · {run.output_tokens.toLocaleString()} out ({run.model_provider})
          </dd>
          <dt className="text-slate-600">Stopped because</dt>
          <dd>{run.stop_reason.replace(/_/g, ' ') || 'not recorded'}</dd>
          {renderEngine && (
            <>
              <dt className="text-slate-600">Rendered with</dt>
              <dd className="break-words">{renderEngine}</dd>
            </>
          )}
        </dl>
        <p className="mt-3 text-xs text-slate-600">Scores are preliminary and still being calibrated.</p>
      </Popover>
      {translateSlot}
      <Popover
        label="Download"
        icon={<Download aria-hidden className="h-4 w-4" />}
        buttonClassName="bg-brand-800 text-white hover:bg-brand-700 data-[state=open]:bg-brand-900"
        width="w-72"
      >
        <ul className="-m-2">
          {outputs.map((output) => {
            const hint = outputHint(output.path)
            return (
              <li key={output.path}>
                <a
                  href={artifactUrl(run.id, output.path)}
                  className="flex items-start gap-2.5 rounded-md px-2 py-2 text-slate-800 hover:bg-slate-100"
                >
                  {outputIcon(output.path)}
                  <span>
                    <span className="block font-medium">{output.label}</span>
                    {hint && <span className="block text-xs text-slate-600">{hint}</span>}
                  </span>
                </a>
              </li>
            )
          })}
        </ul>
        {updatingOutputs && (
          <p role="status" className="mt-3 border-t border-slate-200 pt-3 text-xs text-slate-600">
            Adding the newest download options to this result. This takes a few seconds and does not run the model again.
          </p>
        )}
      </Popover>
      <PanelToggle label="Show or hide the details panel" pressed={rightOpen} onClick={onToggleRight}>
        <PanelRight aria-hidden className="h-4 w-4" />
      </PanelToggle>
    </EditorToolbar>
  )
}
