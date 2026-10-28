import { ChevronLeft, ChevronRight, Maximize, ZoomIn, ZoomOut } from 'lucide-react'
import { useLayoutEffect, useRef, useState } from 'react'
import type { ReviewElement, ReviewPage } from '../types'
import { cx } from './classes'
import PageOverlay from './PageOverlay'

const PADDING = 24
const ZOOM_STEP = 1.25
const MIN_ZOOM = 0.5
const MAX_ZOOM = 4

interface Props {
  pages: ReviewPage[]
  pageNumber: number
  elements: ReviewElement[]
  selectedId: string | null
  onSelect: (id: string) => void
  onPage: (page: number) => void
}

function IconButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={cx(
        'rounded-md p-1.5 text-slate-600 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40',
      )}
    >
      {children}
    </button>
  )
}

export default function PageViewer({ pages, pageNumber, elements, selectedId, onSelect, onPage }: Props) {
  const page = pages.find((candidate) => candidate.number === pageNumber) ?? pages[0]
  const pane = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [zoom, setZoom] = useState(1)
  const [draft, setDraft] = useState<string | null>(null)

  useLayoutEffect(() => {
    const element = pane.current
    if (!element) return
    const measure = () => setSize({ width: element.clientWidth, height: element.clientHeight })
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  if (!page) return <p className="p-6 text-sm text-slate-500">No slide previews were rendered for this run. Use the list on the left to review each description.</p>

  // Fit the whole slide inside the pane, then apply the zoom on top
  const availableWidth = Math.max(0, size.width - PADDING * 2)
  const availableHeight = Math.max(0, size.height - PADDING * 2)
  const fit = Math.min(availableWidth / page.width_points, availableHeight / page.height_points)
  const scale = fit * zoom

  function commitPage() {
    const parsed = Number.parseInt(draft ?? '', 10)
    if (Number.isFinite(parsed)) onPage(Math.min(pages.length, Math.max(1, parsed)))
    setDraft(null)
  }

  return (
    <div
      className="flex h-full min-h-0 flex-col"
      onKeyDown={(event) => {
        if ((event.target as HTMLElement).tagName === 'INPUT') return
        if (event.key === 'ArrowLeft' && pageNumber > 1) onPage(pageNumber - 1)
        if (event.key === 'ArrowRight' && pageNumber < pages.length) onPage(pageNumber + 1)
      }}
    >
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-2">
        <div className="flex items-center gap-1">
          <IconButton label="Previous page" disabled={pageNumber <= 1} onClick={() => onPage(pageNumber - 1)}>
            <ChevronLeft aria-hidden className="h-4 w-4" />
          </IconButton>
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            <span className="sr-only">Page number</span>
            <input
              type="number"
              min={1}
              max={pages.length}
              value={draft ?? pageNumber}
              onChange={(event) => setDraft(event.target.value)}
              onBlur={commitPage}
              onKeyDown={(event) => event.key === 'Enter' && commitPage()}
              className="w-12 rounded-md border border-slate-300 px-1.5 py-0.5 text-center text-sm"
            />
            <span aria-hidden>/ {pages.length}</span>
          </label>
          <IconButton label="Next page" disabled={pageNumber >= pages.length} onClick={() => onPage(pageNumber + 1)}>
            <ChevronRight aria-hidden className="h-4 w-4" />
          </IconButton>
        </div>
        <div className="flex items-center gap-1">
          <IconButton label="Zoom out" disabled={zoom <= MIN_ZOOM} onClick={() => setZoom(Math.max(MIN_ZOOM, zoom / ZOOM_STEP))}>
            <ZoomOut aria-hidden className="h-4 w-4" />
          </IconButton>
          <span className="w-12 text-center text-xs tabular-nums text-slate-500">
            {zoom === 1 ? 'Fit' : `${Math.round(zoom * 100)}%`}
          </span>
          <IconButton label="Zoom in" disabled={zoom >= MAX_ZOOM} onClick={() => setZoom(Math.min(MAX_ZOOM, zoom * ZOOM_STEP))}>
            <ZoomIn aria-hidden className="h-4 w-4" />
          </IconButton>
          <IconButton label="Fit slide to the window" disabled={zoom === 1} onClick={() => setZoom(1)}>
            <Maximize aria-hidden className="h-4 w-4" />
          </IconButton>
        </div>
      </div>

      <div ref={pane} className="flex min-h-0 flex-1 overflow-auto bg-slate-100" style={{ padding: PADDING }}>
        {scale > 0 && (
          <div className="m-auto shrink-0">
            <PageOverlay
              page={page}
              width={page.width_points * scale}
              height={page.height_points * scale}
              elements={elements}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          </div>
        )}
      </div>
    </div>
  )
}
