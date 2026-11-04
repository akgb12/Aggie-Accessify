import { ChevronRight, PanelLeft } from 'lucide-react'
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
      className={cx(
        'flex h-9 w-9 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-slate-100',
        pressed ? 'text-slate-900' : 'text-slate-600',
      )}
    >
      {children}
    </button>
  )
}

function fileName(path: string): string {
  return path.split('/').pop() ?? path
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
    <div className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-3">
      <PanelToggle label="Show or hide the side panel" pressed={leftOpen} onClick={onToggleLeft}>
        <PanelLeft aria-hidden className="h-4 w-4" />
      </PanelToggle>
      <h1 className="sr-only">{file ? fileName(file) : (projectName ?? 'Project')}</h1>
      <nav aria-label="Breadcrumb" className="min-w-0">
        <ol className="flex min-w-0 items-center gap-1.5 text-sm">
          <li className="shrink-0">
            <Link
              to="/"
              className="rounded-sm text-slate-600 underline-offset-4 hover:text-slate-900 hover:underline"
            >
              Projects
            </Link>
          </li>
          {projectName && (
            <>
              <li aria-hidden className="text-slate-400">
                <ChevronRight className="h-4 w-4" />
              </li>
              <li className="min-w-0 max-w-64 truncate text-slate-700" aria-current={file ? undefined : 'page'}>
                {projectName}
              </li>
            </>
          )}
          {file && (
            <>
              <li aria-hidden className="text-slate-400">
                <ChevronRight className="h-4 w-4" />
              </li>
              <li className="min-w-0 truncate font-semibold text-slate-900" aria-current="page" title={file}>
                {fileName(file)}
              </li>
            </>
          )}
        </ol>
      </nav>
      <div className="ml-auto flex items-center gap-2">{children}</div>
    </div>
  )
}
