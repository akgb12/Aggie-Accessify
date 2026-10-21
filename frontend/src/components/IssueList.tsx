import { useState } from 'react'
import { containerLabel, elementLabel } from '../format'
import { groupIssues, issueWhere, severityWord } from '../issues'
import type { IssueGroup } from '../issues'
import type { ReviewElement, ReviewIssue } from '../types'
import { Badge } from './ui'

const PREVIEW = 12

function GroupView({
  group,
  elementsById,
  slideTitles,
  defaultOpen,
  onOpen,
}: {
  group: IssueGroup
  elementsById: Map<string, ReviewElement>
  slideTitles: Map<string, string>
  defaultOpen: boolean
  onOpen: (issue: ReviewIssue) => void
}) {
  const [showAll, setShowAll] = useState(false)
  const shown = showAll ? group.issues : group.issues.slice(0, PREVIEW)
  return (
    <details open={defaultOpen} className="group border-b border-slate-100">
      <summary className="flex cursor-pointer items-start gap-2 px-3 py-2.5 hover:bg-slate-50">
        <Badge tone={group.severity === 'info' ? 'neutral' : group.severity === 'warning' ? 'warning' : 'danger'}>
          {severityWord(group.severity)}
        </Badge>
        <span className="min-w-0 flex-1 text-sm font-medium text-slate-800">{group.title}</span>
        <span className="rounded-full bg-slate-100 px-1.5 text-xs tabular-nums text-slate-600">{group.issues.length}</span>
      </summary>
      <div className="px-3 pb-3">
        <p className="mb-2 text-sm text-slate-500">{group.explanation}</p>
        <ul className="space-y-0.5">
          {shown.map((issue, index) => {
            const element = issue.element_id ? elementsById.get(issue.element_id) : null
            const where = issueWhere(issue)
            const label = element ? elementLabel(element) : null
            const slideId = issue.element_id?.split('/')[0]
            const slide = slideId ? `${containerLabel(slideId)}${slideTitles.get(slideId) ? ` · ${slideTitles.get(slideId)}` : ''}` : null
            const clickable = Boolean(issue.element_id) || typeof issue.details?.page === 'number'
            return (
              <li key={`${issue.code}-${index}`}>
                <button
                  type="button"
                  disabled={!clickable}
                  onClick={() => onOpen(issue)}
                  className="flex w-full flex-col rounded-md px-2 py-1 text-left text-sm hover:bg-slate-100 disabled:cursor-default disabled:hover:bg-transparent"
                >
                  <span className="truncate text-slate-700">{label?.title ?? where ?? issue.message}</span>
                  {(slide || where) && (
                    <span className="truncate text-xs text-slate-400">
                      {[slide, label ? where : null].filter(Boolean).join(' · ') || where}
                    </span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
        {!showAll && group.issues.length > PREVIEW && (
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="mt-1 px-2 text-sm font-medium text-brand-700 hover:underline"
          >
            Show all {group.issues.length}
          </button>
        )}
      </div>
    </details>
  )
}

export default function IssueList({
  issues,
  elementsById,
  slideTitles,
  onOpen,
}: {
  issues: ReviewIssue[]
  elementsById: Map<string, ReviewElement>
  slideTitles: Map<string, string>
  onOpen: (issue: ReviewIssue) => void
}) {
  const groups = groupIssues(issues)
  if (groups.length === 0) return <p className="p-4 text-sm text-slate-500">No issues found.</p>
  return (
    <div className="h-full overflow-auto">
      {groups.map((group, index) => (
        <GroupView
          key={group.code}
          group={group}
          elementsById={elementsById}
          slideTitles={slideTitles}
          defaultOpen={index === 0}
          onOpen={onOpen}
        />
      ))}
    </div>
  )
}
