import { ChevronDown, ChevronRight, File as FileIcon, FileCode, FileText, Folder, Image, Palette } from 'lucide-react'
import { useMemo, useState } from 'react'
import { buildTree, foldersAbove } from '../fileTree'
import type { TreeNode } from '../fileTree'
import { fileKind } from '../format'
import type { ProjectFile, Run } from '../types'
import { cx } from './classes'

const ICONS = { tex: FileCode, pdf: FileText, image: Image, style: Palette, other: FileIcon }

interface Props {
  files: ProjectFile[]
  targets: string[]
  latestByFile: Map<string, Run>
  currentFile: string
  onOpenTarget: (path: string) => void
}

export default function FileTree({ files, targets, latestByFile, currentFile, onOpenTarget }: Props) {
  const tree = useMemo(() => buildTree(files), [files])
  const [open, setOpen] = useState<Set<string>>(() => new Set(foldersAbove(currentFile)))

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
    const isCurrent = node.path === currentFile
    const latest = latestByFile.get(node.path)
    const Icon = ICONS[fileKind(node.path)]
    const content = (
      <>
        <Icon aria-hidden className={cx('h-4 w-4 shrink-0', isTarget ? 'text-brand-700' : 'text-slate-300')} />
        <span className="min-w-0 flex-1">
          <span className={cx('block truncate', !isTarget && 'text-slate-400')}>{node.name}</span>
          {isTarget && (
            <span className="block truncate text-[11px] text-slate-400">
              {isCurrent
                ? 'Showing now'
                : latest
                  ? latest.a_score !== null
                    ? `Translated · A ${latest.a_score.toFixed(0)}`
                    : latest.status
                  : 'Not translated yet'}
            </span>
          )}
        </span>
      </>
    )
    return (
      <li key={node.path}>
        {isTarget ? (
          <button
            type="button"
            onClick={() => onOpenTarget(node.path)}
            aria-current={isCurrent}
            title={isCurrent ? 'The file shown now' : latest ? 'Open its latest translation' : 'Translate this file'}
            style={indent}
            className={cx(
              'flex w-full items-center gap-1.5 rounded-md py-1 pr-2 text-left text-sm',
              isCurrent ? 'bg-brand-50 ring-1 ring-brand-200' : 'text-slate-800 hover:bg-slate-50',
            )}
          >
            {content}
          </button>
        ) : (
          <div
            style={indent}
            title={node.path.endsWith('.tex') ? 'Not a Beamer presentation' : undefined}
            className="flex items-center gap-1.5 py-1 pr-2 text-sm"
          >
            {content}
          </div>
        )}
      </li>
    )
  }

  return (
    <div className="h-full overflow-auto p-2">
      <p className="px-2 pb-2 text-xs text-slate-400">
        Maroon files are Beamer presentations. Click one to open its translation or translate it.
      </p>
      <ul>{tree.map((node) => renderNode(node, 0))}</ul>
    </div>
  )
}
