import { ListFilter, Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { containerLabel, elementLabel } from '../format'
import { needsAttention, statusGroup, statusLabel } from '../status'
import type { ElementStatus, Review, ReviewElement } from '../types'
import { cx } from './classes'
import Popover from './Popover'
import StatusFilter from './StatusFilter'
import StatusSwatch from './StatusSwatch'

interface Props {
  review: Review
  elementsById: Map<string, ReviewElement>
  counts: Partial<Record<ElementStatus, number>>
  visible: Set<ElementStatus>
  pageNumber: number
  selectedId: string | null
  onToggleStatus: (status: ElementStatus) => void
  onShowAll: () => void
  onSelect: (id: string) => void
}

export default function ElementList({
  review,
  elementsById,
  counts,
  visible,
  pageNumber,
  selectedId,
  onToggleStatus,
  onShowAll,
  onSelect,
}: Props) {
  const [scope, setScope] = useState<'page' | 'all'>('page')
  const [query, setQuery] = useState('')
  const list = useRef<HTMLDivElement>(null)

  // Keep the selected row in view inside this list without moving anything else
  useEffect(() => {
    list.current?.querySelector<HTMLElement>('[aria-current="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [selectedId])

  const { groups, hidden } = useMemo(() => {
    const byContainer = new Map<string, ReviewElement[]>()
    for (const element of review.elements) {
      const key = element.id.split('/')[0]
      const items = byContainer.get(key) ?? []
      items.push(element)
      byContainer.set(key, items)
    }
    const needle = query.trim().toLowerCase()
    const result: { id: string; title: string; elements: ReviewElement[] }[] = []
    let hiddenCount = 0
    for (const container of review.containers) {
      if (scope === 'page' && !container.rendered_pages.includes(pageNumber)) continue
      const all = byContainer.get(container.id) ?? []
      hiddenCount += all.filter((element) => !visible.has(statusGroup(element.status))).length
      const elements = all.filter((element) => {
        if (!visible.has(statusGroup(element.status))) return false
        if (!needle) return true
        return `${element.text ?? ''} ${element.type} ${element.alt ?? ''} ${elementLabel(element).subtitle}`
          .toLowerCase()
          .includes(needle)
      })
      if (elements.length === 0) continue
      const titleElement = container.title_element_id ? elementsById.get(container.title_element_id) : null
      result.push({ id: container.id, title: titleElement?.text ?? '', elements })
    }
    return { groups: result, hidden: hiddenCount }
  }, [review, elementsById, visible, scope, pageNumber, query])

  const hiddenStatuses = Object.keys(counts).length - visible.size

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-2 border-b border-slate-100 p-2.5">
        <label className="relative block">
          <span className="sr-only">Search elements</span>
          <Search aria-hidden className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search slides"
            className="h-9 w-full rounded-md border border-slate-300 pl-8 pr-3 text-sm placeholder:text-slate-400"
          />
        </label>
        <div className="flex items-center justify-between">
          <div role="group" aria-label="Scope" className="flex gap-1 text-sm">
            {(['page', 'all'] as const).map((value) => (
              <button
                key={value}
                aria-pressed={scope === value}
                onClick={() => setScope(value)}
                className={cx(
                  'whitespace-nowrap rounded-md px-2.5 py-1',
                  scope === value ? 'bg-slate-100 font-semibold text-slate-900' : 'text-slate-600 hover:bg-slate-100',
                )}
              >
                {value === 'page' ? `Page ${pageNumber}` : 'All slides'}
              </button>
            ))}
          </div>
          <Popover
            align="right"
            width="w-64"
            label={
              <>
                Filter
                {hiddenStatuses > 0 && (
                  <span className="rounded-md bg-slate-100 px-1.5 text-xs text-slate-800">{hiddenStatuses}</span>
                )}
              </>
            }
            icon={<ListFilter aria-hidden className="h-4 w-4" />}
            buttonClassName="whitespace-nowrap text-slate-600 hover:bg-slate-100 !px-2 !py-1"
          >
            <StatusFilter counts={counts} visible={visible} onToggle={onToggleStatus} onShowAll={onShowAll} />
          </Popover>
        </div>
      </div>
      <div ref={list} className="min-h-0 flex-1 overflow-auto p-2">
        {groups.length === 0 && (
          <div className="p-3 text-sm text-slate-500">
            <p>
              {query.trim()
                ? 'Nothing matches your search.'
                : hidden > 0
                  ? `Nothing needs attention ${scope === 'page' ? 'on this page' : 'here'}.`
                  : 'No elements here.'}
            </p>
            {hidden > 0 && (
              <button onClick={onShowAll} className="mt-2 font-medium text-brand-700 underline hover:text-brand-800">
                Show all {hidden} hidden element{hidden === 1 ? '' : 's'}
              </button>
            )}
          </div>
        )}
        {groups.map((group) => (
          <section key={group.id} className="mb-2">
            <h3 className="sticky top-0 z-10 truncate bg-white px-2 py-1 text-xs font-semibold text-slate-500">
              {containerLabel(group.id)}
              {group.title && <span className="ml-1 font-normal text-slate-400">· {group.title}</span>}
            </h3>
            <ul>
              {group.elements.map((element) => {
                const label = elementLabel(element)
                const flagged = needsAttention(element.status)
                // The slide is already named by the group header, so show only what is extra
                const context = label.subtitle.replace(/^[^·]*(?: · )?/, '')
                return (
                  <li key={element.id}>
                    <button
                      onClick={() => onSelect(element.id)}
                      aria-current={element.id === selectedId}
                      className={cx(
                        'flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left',
                        element.id === selectedId ? 'bg-brand-50 ring-1 ring-brand-200' : 'hover:bg-slate-50',
                      )}
                    >
                      <span className="mt-[7px]">
                        <StatusSwatch status={element.status} size={14} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm text-slate-800">{label.title}</span>
                        <span className="block truncate text-xs text-slate-400">
                          {flagged && <span className="font-medium text-slate-600">{statusLabel(element.status)}</span>}
                          {flagged && context && ' · '}
                          {context}
                        </span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}
