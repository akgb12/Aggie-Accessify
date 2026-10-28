import { Download, FileArchive, FileText, Info, PanelRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { artifactUrl } from '../api'
import { formatCost, scoreTone } from '../format'
import type { ReviewOutput, Run } from '../types'
import { cx } from './classes'
import EditorToolbar, { PanelToggle } from './EditorToolbar'
import Popover from './Popover'

const TONE_TEXT = {
  success: 'text-emerald-700',
  warning: 'text-amber-700',
  danger: 'text-red-700',
}

function Score({ label, title, value }: { label: string; title: string; value: number | null }) {
  return (
    <span className="flex items-baseline gap-1" title={`${title} (preliminary)`}>
      <span className="text-xs font-medium text-slate-500">{label}</span>
      <span className={cx('text-sm font-semibold tabular-nums', value !== null && TONE_TEXT[scoreTone(value)])}>
        {value === null ? '–' : value.toFixed(1)}
      </span>
    </span>
  )
}

function outputIcon(path: string) {
  const className = 'h-4 w-4'
  if (path.endsWith('.zip')) return <FileArchive aria-hidden className={className} />
  if (path.endsWith('.html') || path.endsWith('.diff')) return <FileText aria-hidden className={className} />
  return <Download aria-hidden className={className} />
}

interface Props {
  run: Run
  projectName: string
  renderEngine: string | null
  outputs: ReviewOutput[]
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
  attentionCount,
  leftOpen,
  rightOpen,
  onToggleLeft,
  onToggleRight,
  translateSlot,
}: Props) {
  const links = outputs.map((output) => ({
    href: artifactUrl(run.id, output.path),
    icon: outputIcon(output.path),
    text: output.label,
  }))

  return (
    <EditorToolbar projectName={projectName} file={run.main_file || null} leftOpen={leftOpen} onToggleLeft={onToggleLeft}>
      <div className="flex items-center gap-3">
        <Score label="A" title="Accessibility" value={run.a_score} />
        <Score label="F" title="Fidelity" value={run.f_score} />
        <span className="text-[11px] uppercase tracking-wide text-slate-400">prelim.</span>
      </div>
      {attentionCount > 0 && (
        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-inset ring-amber-200">
          {attentionCount} need attention
        </span>
      )}
      {translateSlot}
      <Popover label="Run details" icon={<Info aria-hidden className="h-4 w-4" />} width="w-80">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
          <dt className="text-slate-500">Effort</dt>
          <dd className="capitalize">{run.effort}</dd>
          <dt className="text-slate-500">Model cost</dt>
          <dd>{formatCost(run.cost_usd)}</dd>
          <dt className="text-slate-500">Tokens</dt>
          <dd>
            {run.input_tokens.toLocaleString()} in · {run.output_tokens.toLocaleString()} out
          </dd>
          <dt className="text-slate-500">Provider</dt>
          <dd>{run.model_provider}</dd>
          <dt className="text-slate-500">Stopped</dt>
          <dd className="capitalize">{run.stop_reason.replace(/_/g, ' ') || '–'}</dd>
          {renderEngine && (
            <>
              <dt className="text-slate-500">Rendered with</dt>
              <dd className="break-words">{renderEngine}</dd>
            </>
          )}
        </dl>
      </Popover>
      <Popover
        label="Download"
        icon={<Download aria-hidden className="h-4 w-4" />}
        buttonClassName="border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
        width="w-60"
      >
        <ul className="-m-1">
          {links.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                className="flex items-center gap-2 rounded-md px-2 py-1.5 text-slate-700 hover:bg-slate-100"
              >
                {link.icon}
                {link.text}
              </a>
            </li>
          ))}
        </ul>
      </Popover>
      <PanelToggle label="Show or hide the inspector" pressed={rightOpen} onClick={onToggleRight}>
        <PanelRight aria-hidden className="h-4 w-4" />
      </PanelToggle>
    </EditorToolbar>
  )
}
