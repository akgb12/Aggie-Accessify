import { ArrowLeft, PanelLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cx } from './classes'

export function PanelToggle({
  label,
  pressed,
  onClick,
  children,
}: {
  label: string
  pressed: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      onClick={onClick}
      className={cx('rounded-md p-1.5 hover:bg-slate-100', pressed ? 'text-brand-800' : 'text-slate-400')}
    >
      {children}
    </button>
  )
}

export default function EditorToolbar({
  projectName,
  file,
  leftOpen,
  onToggleLeft,
  children,
}: {
  projectName: string | null
  file: string | null
  leftOpen: boolean
  onToggleLeft: () => void
  children?: ReactNode
}) {
  return (
    <div className="flex h-12 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-3">
      <PanelToggle label="Show or hide the file list" pressed={leftOpen} onClick={onToggleLeft}>
        <PanelLeft aria-hidden className="h-4 w-4" />
      </PanelToggle>
      <Link
        to="/"
        className="flex min-w-0 items-center gap-2 rounded-md px-1 py-0.5 text-sm text-slate-500 hover:bg-slate-100"
        title="All projects"
      >
        <ArrowLeft aria-hidden className="h-4 w-4 shrink-0" />
        <span className="max-w-48 truncate">{projectName ?? 'Projects'}</span>
      </Link>
      {file && (
        <>
          <span aria-hidden className="text-slate-300">
            /
          </span>
          <span className="min-w-0 truncate font-mono text-sm font-medium text-slate-800">{file}</span>
        </>
      )}
      <div className="ml-auto flex items-center gap-3">{children}</div>
    </div>
  )
}
