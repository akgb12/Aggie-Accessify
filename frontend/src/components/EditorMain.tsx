import { FileText, MousePointerClick, Presentation } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { editorPath, whyNoTargets } from '../editorState'
import { formatDuration, relativeTime } from '../format'
import { isFinished } from '../status'
import type { Project, Run } from '../types'
import TranslateForm from './TranslateForm'
import { Alert, EmptyState, RunStatusBadge, Spinner } from './ui'

function Elapsed({ since }: { since: string }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  return <>{formatDuration(now - new Date(since).getTime())}</>
}

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center overflow-auto bg-slate-50 p-6">
      <div className="w-full max-w-lg">{children}</div>
    </div>
  )
}

interface Props {
  project: Project
  targets: string[]
  file: string | null
  run: Run | null
  loadError: string | null
  onStarted: (run: Run) => void
}

// Everything the editor can show other than a finished translation
export default function EditorMain({ project, targets, file, run, loadError, onStarted }: Props) {
  const noTargets = whyNoTargets(project.files, targets)
  if (noTargets === 'no_tex') {
    return (
      <Centered>
        <EmptyState icon={<FileText aria-hidden className="h-6 w-6" />} title="No slide decks in this project">
          Only PDFs or other files were found. Use Add files on the left to add a PowerPoint (.pptx) deck or the
          LaTeX source of your Beamer slides. A PDF alone cannot be made accessible here.
        </EmptyState>
      </Centered>
    )
  }
  if (noTargets === 'no_beamer') {
    return (
      <Centered>
        <EmptyState icon={<Presentation aria-hidden className="h-6 w-6" />} title="No Beamer presentation found">
          None of the .tex files is a Beamer presentation, which needs the beamer document class and a document
          body. Add the right file with Add files on the left.
        </EmptyState>
      </Centered>
    )
  }

  if (!file) {
    return (
      <Centered>
        <EmptyState icon={<MousePointerClick aria-hidden className="h-6 w-6" />} title="Choose a slide deck">
          Select a deck in the file list on the left to make it accessible or to review the last run.
        </EmptyState>
      </Centered>
    )
  }

  if (run && !isFinished(run.status)) {
    return (
      <Centered>
        <div role="status" aria-live="polite" className="text-center">
          <Spinner className="mx-auto h-8 w-8 text-brand-800" />
          <p className="mt-4 text-lg font-semibold text-slate-900">
            {run.status === 'queued' ? 'Waiting to start' : 'Making your slides accessible'}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Describing figures, fixing titles and reading order, and checking that nothing visible changed. Large
            decks take a few minutes. You can leave this page and come back.
          </p>
          <div className="mx-auto mt-5 h-1.5 w-64 overflow-hidden rounded-full bg-slate-200">
            <div className="animate-indeterminate h-full w-1/4 rounded-full bg-brand-800" />
          </div>
          <p className="mt-3 text-sm text-slate-600">
            <span className="capitalize">{run.effort}</span> effort · <Elapsed since={run.started_at ?? run.created_at} />{' '}
            elapsed
          </p>
        </div>
      </Centered>
    )
  }

  let notice: ReactNode = null
  if (loadError) {
    notice = (
      <Alert tone="danger" title="This run could not be loaded">
        {loadError}
      </Alert>
    )
  } else if (run?.status === 'failed') {
    notice = (
      <Alert tone="danger" title="The last run failed">
        {run.error_message || 'It stopped unexpectedly. Try again, and contact the team if it fails again.'}
      </Alert>
    )
  } else if (run?.status === 'blocked') {
    notice = (
      <Alert tone="warning" title="Some files are needed first">
        Reason: {run.stop_reason.replace(/_/g, ' ') || 'the first checks did not pass'}. If files are missing, add
        them with Add files on the left, then start again.
      </Alert>
    )
  }

  return (
    <Centered>
      <div className="space-y-5 rounded-lg border border-slate-200 bg-white p-6">
        <div>
          <h1 className="truncate text-xl font-semibold text-slate-900" title={file}>
            {file.split('/').pop()}
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            {run ? (
              <span className="inline-flex items-center gap-2">
                <RunStatusBadge status={run.status} /> Last run {relativeTime(run.created_at)}
              </span>
            ) : (
              'Not made accessible yet. Choose an effort, then start.'
            )}
          </p>
        </div>
        {notice}
        <TranslateForm projectId={project.id} file={file} onStarted={onStarted} />
        {run && run.status === 'succeeded' && (
          <Link
            to={editorPath(project.id, file, run.id)}
            className="block text-center text-sm font-semibold text-brand-800 underline underline-offset-4"
          >
            Open the last finished run
          </Link>
        )}
      </div>
    </Centered>
  )
}
