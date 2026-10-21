import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePersistentFlag } from '../hooks'
import { needsAttention, statusGroup } from '../status'
import type { ElementStatus, Review, ReviewElement, ReviewIssue, Run } from '../types'
import { useWorkspaceData } from '../workspace'
import ElementList from './ElementList'
import FileTree from './FileTree'
import Inspector from './Inspector'
import PageThumbnails from './PageThumbnails'
import PageViewer from './PageViewer'
import ReviewSidebar from './ReviewSidebar'
import ReviewToolbar from './ReviewToolbar'
import TranslateMenu from './TranslateMenu'

const DEFAULT_HIDDEN: ElementStatus = 'done'

// Pages where an element can actually be seen, which for step-by-step slides is fewer than the pages it spans
const shownPages = (element: ReviewElement): number[] => element.visible_pages ?? element.pages

export default function ReviewView({ run, review }: { run: Run; review: Review }) {
  const navigate = useNavigate()
  const workspace = useWorkspaceData(run.project_id)
  const [pageNumber, setPageNumber] = useState(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [translateOpen, setTranslateOpen] = useState(false)
  const [requestedFile, setRequestedFile] = useState<string | null>(null)
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

  const slideTitles = useMemo(() => {
    const titles = new Map<string, string>()
    for (const container of review.containers) {
      const title = container.title_element_id ? elementsById.get(container.title_element_id)?.text : null
      if (title) titles.set(container.id, title)
    }
    return titles
  }, [review, elementsById])

  const counts = useMemo(() => {
    const result: Partial<Record<ElementStatus, number>> = {}
    for (const element of review.elements) {
      const group = statusGroup(element.status)
      result[group] = (result[group] ?? 0) + 1
    }
    return result
  }, [review])

  const flaggedPages = useMemo(() => {
    const pages = new Set<number>()
    for (const element of review.elements) {
      if (needsAttention(element.status)) shownPages(element).forEach((page) => pages.add(page))
    }
    return pages
  }, [review])

  const attentionCount = review.elements.filter((element) => needsAttention(element.status)).length
  const pageElements = review.elements.filter(
    (element) => shownPages(element).includes(pageNumber) && visible.has(statusGroup(element.status)),
  )
  const flaggedOnPage = review.elements.filter(
    (element) => shownPages(element).includes(pageNumber) && needsAttention(element.status),
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
    const pages = shownPages(element).length > 0 ? shownPages(element) : (container?.rendered_pages ?? [])
    if (pages.length > 0 && !pages.includes(pageNumber)) setPageNumber(pages[0])
    // A selected element should always be visible on the slide
    const group = statusGroup(element.status)
    setVisible((current) => (current.has(group) ? current : new Set(current).add(group)))
  }

  function openIssue(issue: ReviewIssue) {
    if (issue.element_id) {
      select(issue.element_id)
      return
    }
    const page = issue.details?.page
    if (typeof page === 'number') setPageNumber(page)
  }

  function openTarget(file: string) {
    if (file === run.main_file) return
    const latest = workspace.latestByFile.get(file)
    if (latest) {
      navigate(`/runs/${latest.id}`)
      return
    }
    setRequestedFile(file)
    setTranslateOpen(true)
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
        translateSlot={
          <TranslateMenu
            projectId={run.project_id}
            targets={workspace.targets}
            runs={workspace.runs}
            latestByFile={workspace.latestByFile}
            currentFile={run.main_file}
            requestedFile={requestedFile}
            open={translateOpen}
            onOpenChange={setTranslateOpen}
          />
        }
      />
      <div className="flex min-h-0 flex-1">
        {leftOpen && (
          <aside aria-label="Slides, issues, pages and files" className="w-72 shrink-0 border-r border-slate-200">
            <ReviewSidebar
              review={review}
              elementsById={elementsById}
              slideTitles={slideTitles}
              onOpenIssue={openIssue}
              elements={
                <ElementList
                  review={review}
                  elementsById={elementsById}
                  counts={counts}
                  visible={visible}
                  pageNumber={pageNumber}
                  selectedId={selectedId}
                  onToggleStatus={toggle}
                  onShowAll={() => setVisible(new Set(Object.keys(counts) as ElementStatus[]))}
                  onSelect={select}
                />
              }
              pages={
                <PageThumbnails
                  pages={review.pages}
                  pageNumber={pageNumber}
                  flaggedPages={flaggedPages}
                  onPage={setPageNumber}
                />
              }
              files={
                workspace.project ? (
                  <FileTree
                    files={workspace.project.files}
                    targets={workspace.targets}
                    latestByFile={workspace.latestByFile}
                    currentFile={run.main_file}
                    onOpenTarget={openTarget}
                  />
                ) : (
                  <p className="p-4 text-sm text-slate-500">{workspace.error ?? 'Loading files…'}</p>
                )
              }
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
