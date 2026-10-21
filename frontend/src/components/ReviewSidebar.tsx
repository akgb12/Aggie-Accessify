import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { ReviewElement, ReviewIssue } from '../types'
import { cx } from './classes'
import IssueList from './IssueList'

export type SidebarTab = 'elements' | 'issues' | 'pages' | 'files'

interface Props {
  elements: ReactNode
  pages: ReactNode
  files: ReactNode
  review: { issues: ReviewIssue[]; elements: ReviewElement[] }
  elementsById: Map<string, ReviewElement>
  slideTitles: Map<string, string>
  onOpenIssue: (issue: ReviewIssue) => void
}

const SEVERITY_ORDER = ['veto', 'error', 'warning', 'info']

export default function ReviewSidebar({
  elements,
  pages,
  files,
  review,
  elementsById,
  slideTitles,
  onOpenIssue,
}: Props) {
  const [tab, setTab] = useState<SidebarTab>('elements')
  const issues = useMemo(() => {
    const all = [...review.issues, ...review.elements.flatMap((element) => element.issues)]
    return all.sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity))
  }, [review])

  const tabs: { id: SidebarTab; label: string; count?: number }[] = [
    { id: 'elements', label: 'Slides' },
    { id: 'issues', label: 'Issues', count: issues.length },
    { id: 'pages', label: 'Pages' },
    { id: 'files', label: 'Files' },
  ]

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div role="tablist" aria-label="Sidebar" className="flex shrink-0 border-b border-slate-200">
        {tabs.map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={cx(
              'flex-1 whitespace-nowrap border-b-2 px-1.5 py-2 text-[13px] font-medium',
              tab === item.id ? 'border-brand-700 text-brand-800' : 'border-transparent text-slate-500 hover:text-slate-800',
            )}
          >
            {item.label}
            {item.count !== undefined && (
              <span className="ml-1 rounded-full bg-slate-100 px-1.5 text-[11px] text-slate-600">{item.count}</span>
            )}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1">
        {tab === 'elements' && elements}
        {tab === 'issues' && <IssueList issues={issues} elementsById={elementsById} slideTitles={slideTitles} onOpen={onOpenIssue} />}
        {tab === 'pages' && pages}
        {tab === 'files' && files}
      </div>
    </div>
  )
}
