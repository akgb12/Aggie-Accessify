import {
  ChevronDown,
  ChevronRight,
  File as FileIcon,
  FileCode,
  FileText,
  Folder,
  Image,
  Palette,
  Presentation,
  X,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { buildTree, foldersAbove } from '../fileTree'
import type { TreeNode } from '../fileTree'
import { fileKind, relativeTime } from '../format'
import type { ProjectFile, Run } from '../types'
import { cx } from './classes'

const ICONS = {
  tex: FileCode,
  deck: Presentation,
  document: FileText,
  pdf: FileText,
  image: Image,
  style: Palette,
  other: FileIcon,
}

interface Props {
  files: ProjectFile[]
  targets: string[]
  latestByFile: Map<string, Run>
  selectedFile: string | null
  onSelect: (path: string) => void
  onRemove: (path: string) => void
}

function statusText(run: Run | undefined): string {
  if (!run) return 'Not made accessible yet'
  if (run.status === 'succeeded') return `Made accessible ${relativeTime(run.created_at)}`
  if (run.status === 'queued' || run.status === 'running') return 'Working on it'
  return run.status === 'failed' ? 'Last run failed' : 'Last run needs files'
}

export default function FileTree({ files, targets, latestByFile, selectedFile, onSelect, onRemove }: Props) {
  const tree = useMemo(() => buildTree(files), [files])
  const [open, setOpen] = useState<Set<string>>(() => new Set(selectedFile ? foldersAbove(selectedFile) : []))

  function toggle(path: string) {
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  function renderNode(node: TreeNode, depth: number) {
    const indent = { paddingLeft: 8 + depth * 14 }
    if (node.folder) {
      const isOpen = open.has(node.path)
      return (
        <li key={node.path}>
          <button
            type="button"
            onClick={() => toggle(node.path)}
            aria-expanded={isOpen}
            style={indent}
            className="flex w-full items-center gap-1.5 rounded-md py-1 pr-2 text-left text-sm text-slate-700 hover:bg-slate-50"
          >
            {isOpen ? <ChevronDown aria-hidden className="h-3.5 w-3.5" /> : <ChevronRight aria-hidden className="h-3.5 w-3.5" />}
            <Folder aria-hidden className="h-4 w-4 text-slate-400" />
            <span className="truncate">{node.name}</span>
          </button>
          {isOpen && <ul>{node.children.map((child) => renderNode(child, depth + 1))}</ul>}
        </li>
      )
    }
    const isTarget = targets.includes(node.path)
    const isSelected = node.path === selectedFile
    const Icon = ICONS[fileKind(node.path)]
    const body = (
      <>
        <Icon aria-hidden className={cx('h-4 w-4 shrink-0', isTarget ? 'text-brand-800' : 'text-slate-400')} />
        <span className="min-w-0 flex-1">
          <span className={cx('block truncate', !isTarget && 'text-slate-400')}>{node.name}</span>
          {isTarget && (
            <span className="block truncate text-xs text-slate-600">{statusText(latestByFile.get(node.path))}</span>
          )}
        </span>
      </>
    )
    return (
      <li key={node.path} className="group relative">
        {isTarget ? (
          <button
            type="button"
            onClick={() => onSelect(node.path)}
            aria-current={isSelected}
            style={indent}
            className={cx(
              'flex w-full items-center gap-1.5 rounded-md py-1 pr-7 text-left text-sm',
              isSelected ? 'bg-brand-50 ring-1 ring-brand-200' : 'text-slate-800 hover:bg-slate-50',
            )}
          >
            {body}
          </button>
        ) : (
          <div
            style={indent}
            title={node.path.endsWith('.tex') ? 'Not a Beamer presentation' : undefined}
            className="flex items-center gap-1.5 py-1 pr-7 text-sm"
          >
            {body}
          </div>
        )}
        <button
          type="button"
          onClick={() => onRemove(node.path)}
          aria-label={`Remove ${node.path}`}
          className="absolute right-1 top-1 flex h-7 w-7 items-center justify-center rounded-md text-slate-600 opacity-0 hover:bg-red-50 hover:text-danger focus-visible:opacity-100 group-hover:opacity-100"
        >
          <X aria-hidden className="h-3.5 w-3.5" />
        </button>
      </li>
    )
  }

  return (
    <ul className="px-2 pb-2">{tree.map((node) => renderNode(node, 0))}</ul>
  )
}
