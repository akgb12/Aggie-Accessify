import { useMemo, useState } from 'react'
import { usePersistentFlag } from '../hooks'
import { needsAttention, statusGroup } from '../status'
import type { ElementStatus, Review, ReviewElement, Run } from '../types'
import ElementSidebar from './ElementSidebar'
import Inspector from './Inspector'
import PageViewer from './PageViewer'
import ReviewToolbar from './ReviewToolbar'

const DEFAULT_HIDDEN: ElementStatus = 'done'

export default function ReviewView({ run, review }: { run: Run; review: Review }) {
  const [pageNumber, setPageNumber] = useState(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [leftOpen, setLeftOpen] = usePersistentFlag('review.left', true)
  const [rightOpen, setRightOpen] = usePersistentFlag('review.right', true)
  const [visible, setVisible] = useState<Set<ElementStatus>>(() => {
    const all = new Set<ElementStatus>()
    for (const element of review.elements) all.add(statusGroup(element.status))
    all.delete(DEFAULT_HIDDEN)
    return all
  })

  const elementsById = useMemo(() => {
    const map = new Map<string, ReviewElement>()
    for (const element of review.elements) map.set(element.id, element)
    return map
  }, [review])

  const counts = useMemo(() => {
    const result: Partial<Record<ElementStatus, number>> = {}
    for (const element of review.elements) {
      const group = statusGroup(element.status)
      result[group] = (result[group] ?? 0) + 1
    }
    return result
  }, [review])

  const attentionCount = review.elements.filter((element) => needsAttention(element.status)).length
  const pageElements = review.elements.filter(
    (element) => element.pages.includes(pageNumber) && visible.has(statusGroup(element.status)),
  )
  const flaggedOnPage = review.elements.filter(
    (element) => element.pages.includes(pageNumber) && needsAttention(element.status),
  )
  const selected = selectedId ? (elementsById.get(selectedId) ?? null) : null

  function toggle(status: ElementStatus) {
    setVisible((current) => {
      const next = new Set(current)
      if (next.has(status)) next.delete(status)
      else next.add(status)
      return next
    })
  }

  function select(id: string) {
    setSelectedId(id)
    const element = elementsById.get(id)
    if (!element) return
    // Unmapped elements fall back to the first page of their slide
    const container = review.containers.find((item) => item.id === id.split('/')[0])
    const pages = element.pages.length > 0 ? element.pages : (container?.rendered_pages ?? [])
    if (pages.length > 0 && !pages.includes(pageNumber)) setPageNumber(pages[0])
    // A selected element should always be visible on the slide
    const group = statusGroup(element.status)
    setVisible((current) => (current.has(group) ? current : new Set(current).add(group)))
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      <ReviewToolbar
        run={run}
        renderEngine={review.render_engine}
        attentionCount={attentionCount}
        leftOpen={leftOpen}
        rightOpen={rightOpen}
        onToggleLeft={() => setLeftOpen(!leftOpen)}
        onToggleRight={() => setRightOpen(!rightOpen)}
      />
      <div className="flex min-h-0 flex-1">
        {leftOpen && (
          <aside aria-label="Slides and issues" className="w-72 shrink-0 border-r border-slate-200">
            <ElementSidebar
              review={review}
              elementsById={elementsById}
              counts={counts}
              visible={visible}
              pageNumber={pageNumber}
              selectedId={selectedId}
              onToggleStatus={toggle}
              onShowAll={() => setVisible(new Set(Object.keys(counts) as ElementStatus[]))}
              onSelect={select}
              onGoToPage={setPageNumber}
            />
          </aside>
        )}
        <section aria-label="Slide preview" className="min-w-0 flex-1">
          <PageViewer
            pages={review.pages}
            pageNumber={pageNumber}
            elements={pageElements}
            selectedId={selectedId}
            onSelect={select}
            onPage={setPageNumber}
          />
        </section>
        {rightOpen && (
          <aside aria-label="Inspector" className="w-80 shrink-0 overflow-auto border-l border-slate-200">
            <Inspector element={selected} pageNumber={pageNumber} flagged={flaggedOnPage} onSelect={select} />
          </aside>
        )}
      </div>
    </div>
  )
}
