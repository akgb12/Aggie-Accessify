import { useEffect, useRef } from 'react'
import { absoluteUrl } from '../api'
import type { ReviewPage } from '../types'
import { cx } from './classes'

export default function PageThumbnails({
  pages,
  pageNumber,
  flaggedPages,
  onPage,
}: {
  pages: ReviewPage[]
  pageNumber: number
  flaggedPages: Set<number>
  onPage: (page: number) => void
}) {
  const list = useRef<HTMLDivElement>(null)

  useEffect(() => {
    list.current?.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView({ block: 'nearest' })
  }, [pageNumber])

  return (
    <div ref={list} className="h-full overflow-auto p-2">
      <ul className="grid grid-cols-2 gap-2">
        {pages.map((page) => (
          <li key={page.number}>
            <button
              type="button"
              onClick={() => onPage(page.number)}
              aria-current={page.number === pageNumber ? 'page' : undefined}
              aria-label={`Go to page ${page.number}${flaggedPages.has(page.number) ? ', has items to review' : ''}`}
              style={{ aspectRatio: `${page.width_points} / ${page.height_points}` }}
              className={cx(
                'relative block w-full overflow-hidden rounded-md border-2 bg-white ring-1 ring-slate-200',
                page.number === pageNumber ? 'border-brand-600' : 'border-transparent hover:border-slate-300',
              )}
            >
              <img
                src={absoluteUrl(page.thumb_url)}
                alt=""
                loading="lazy"
                decoding="async"
                className="absolute inset-0 h-full w-full"
              />
              <span className="absolute bottom-0 left-0 rounded-tr bg-slate-900/80 px-1.5 text-xs text-white">
                {page.number}
              </span>
              {flaggedPages.has(page.number) && (
                <span aria-hidden className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full bg-warning ring-2 ring-white" />
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
