import { ArrowLeft, Download, FileArchive, FileText, Info, PanelLeft, PanelRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { artifactUrl } from '../api'
import { formatCost, scoreTone } from '../format'
import type { Run } from '../types'
import { cx } from './classes'
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

function PanelToggle({
  label,
  pressed,
  onClick,
  children,
}: {
  label: string
  pressed: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      onClick={onClick}
      className={cx(
        'rounded-md p-1.5 hover:bg-slate-100',
        pressed ? 'text-brand-800' : 'text-slate-400',
      )}
    >
      {children}
    </button>
  )
}

interface Props {
  run: Run
  renderEngine: string | null
  attentionCount: number
  leftOpen: boolean
  rightOpen: boolean
  onToggleLeft: () => void
  onToggleRight: () => void
  translateSlot: React.ReactNode
}

export default function ReviewToolbar({
  run,
  renderEngine,
  attentionCount,
  leftOpen,
  rightOpen,
  onToggleLeft,
  onToggleRight,
  translateSlot,
}: Props) {
  const links = [
    { href: artifactUrl(run.id, 'output/tagged.pdf'), icon: <Download aria-hidden className="h-4 w-4" />, text: 'Tagged PDF' },
    { href: artifactUrl(run.id, 'output/updated_project.zip'), icon: <FileArchive aria-hidden className="h-4 w-4" />, text: 'Updated project (.zip)' },
    { href: artifactUrl(run.id, 'report.html'), icon: <FileText aria-hidden className="h-4 w-4" />, text: 'Report' },
  ]

  return (
    <div className="flex h-12 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-3">
      <PanelToggle label="Show or hide the slide list" pressed={leftOpen} onClick={onToggleLeft}>
        <PanelLeft aria-hidden className="h-4 w-4" />
      </PanelToggle>
      <Link
        to={`/projects/${run.project_id}`}
        className="flex min-w-0 items-center gap-2 rounded-md px-1 py-0.5 text-sm hover:bg-slate-100"
        title="Back to the project"
      >
        <ArrowLeft aria-hidden className="h-4 w-4 shrink-0 text-slate-400" />
        <span className="truncate font-mono text-sm font-medium text-slate-800">{run.main_file || 'Run'}</span>
      </Link>

      <div className="ml-auto flex items-center gap-4">
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
          buttonClassName="bg-brand-800 text-white hover:bg-brand-700"
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
      </div>
    </div>
  )
}
