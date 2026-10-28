import { ChevronLeft, ChevronRight } from 'lucide-react'
import { absoluteUrl } from '../api'
import { elementLabel } from '../format'
import { statusLabel } from '../status'
import type { ReviewElement } from '../types'
import { cx } from './classes'
import StatusSwatch from './StatusSwatch'

// Stands in for the slide image when the server has no slide renderer: the slide's own elements,
// with each picture next to the description written for it
export default function SlideOutline({
  slideCount,
  slideNumber,
  title,
  elements,
  selectedId,
  onSelect,
  onSlide,
}: {
  slideCount: number
  slideNumber: number
  title: string | null
  elements: ReviewElement[]
  selectedId: string | null
  onSelect: (id: string) => void
  onSlide: (slide: number) => void
}) {
  return (
    <div className="h-full overflow-auto bg-slate-50 p-6">
      <div className="mx-auto max-w-3xl">
        <div className="mb-4 flex items-center gap-2">
          <button
            type="button"
            aria-label="Previous slide"
            disabled={slideNumber <= 1}
            onClick={() => onSlide(slideNumber - 1)}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-200 disabled:opacity-40"
          >
            <ChevronLeft aria-hidden className="h-4 w-4" />
          </button>
          <h2 className="min-w-0 flex-1 truncate text-base font-semibold text-slate-900">
            Slide {slideNumber} of {slideCount}
            {title ? <span className="font-normal text-slate-500"> · {title}</span> : null}
          </h2>
          <button
            type="button"
            aria-label="Next slide"
            disabled={slideNumber >= slideCount}
            onClick={() => onSlide(slideNumber + 1)}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-200 disabled:opacity-40"
          >
            <ChevronRight aria-hidden className="h-4 w-4" />
          </button>
        </div>
        <p className="mb-4 text-xs text-slate-500">
          Slide previews need LibreOffice on the server, which is not installed. Elements appear in
          reading order.
        </p>
        {elements.length === 0 && <p className="text-sm text-slate-500">Nothing on this slide.</p>}
        <ul className="space-y-3">
          {elements.map((element) => {
            const label = elementLabel(element)
            const isFigure = element.type === 'figure'
            return (
              <li key={element.id}>
                <button
                  type="button"
                  onClick={() => onSelect(element.id)}
                  aria-pressed={selectedId === element.id}
                  className={cx(
                    'flex w-full gap-4 rounded-xl border bg-white p-3 text-left shadow-sm hover:border-brand-300',
                    selectedId === element.id ? 'border-brand-600 ring-1 ring-brand-600' : 'border-slate-200',
                  )}
                >
                  {element.image_url && (
                    <img
                      src={absoluteUrl(element.image_url)}
                      alt=""
                      className="h-24 w-32 shrink-0 rounded-md border border-slate-200 object-contain"
                    />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2 text-xs text-slate-500">
                      <StatusSwatch status={element.status} size={14} />
                      {statusLabel(element.status)} · {label.subtitle}
                    </span>
                    <span className="mt-1 block text-sm font-medium text-slate-900">{label.title}</span>
                    {isFigure && (
                      <span className="mt-1 block text-sm text-slate-700">
                        {element.alt ?? <em className="text-slate-400">No description yet</em>}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
