import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/kit/tabs'
import type { Review, ReviewElement, ReviewIssue } from '../types'
import IssueList from './IssueList'

export type SidebarTab = 'elements' | 'issues' | 'pages' | 'files'

interface Props {
  elements: ReactNode
  pages: ReactNode
  files: ReactNode
  review: { issues: ReviewIssue[]; elements: ReviewElement[]; source_format: Review['source_format'] }
  elementsById: Map<string, ReviewElement>
  slideTitles: Map<string, string>
  onOpenIssue: (issue: ReviewIssue) => void
}

const SEVERITY_ORDER = ['veto', 'error', 'warning', 'info']

const TAB_CLASS =
  'h-full flex-1 rounded-none border-0 border-b-2 border-transparent px-1 text-sm font-semibold text-slate-600 shadow-none hover:text-slate-900 data-[state=active]:border-brand-800 data-[state=active]:text-slate-900 data-[state=active]:shadow-none'

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

  return (
    <Tabs value={tab} onValueChange={(next) => setTab(next as SidebarTab)} className="flex h-full min-h-0 flex-col gap-0">
      <TabsList
        aria-label="Side panel"
        className="h-11 w-full shrink-0 rounded-none border-b border-slate-200 bg-white p-0"
      >
        <TabsTrigger value="elements" className={TAB_CLASS}>
          {review.source_format === 'docx' ? 'Sections' : 'Slides'}
        </TabsTrigger>
        <TabsTrigger value="issues" className={TAB_CLASS}>
          Issues
          <span className="rounded-md bg-slate-100 px-1.5 text-xs tabular-nums text-slate-800">{issues.length}</span>
        </TabsTrigger>
        <TabsTrigger value="pages" className={TAB_CLASS}>
          Pages
        </TabsTrigger>
        <TabsTrigger value="files" className={TAB_CLASS}>
          Files
        </TabsTrigger>
      </TabsList>
      <TabsContent value="elements" className="min-h-0">
        {elements}
      </TabsContent>
      <TabsContent value="issues" className="min-h-0">
        <IssueList issues={issues} elementsById={elementsById} slideTitles={slideTitles} onOpen={onOpenIssue} />
      </TabsContent>
      <TabsContent value="pages" className="min-h-0">
        {pages}
      </TabsContent>
      <TabsContent value="files" className="min-h-0">
        {files}
      </TabsContent>
    </Tabs>
  )
}
