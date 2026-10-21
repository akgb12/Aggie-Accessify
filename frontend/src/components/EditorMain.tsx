import { FileText, Presentation } from 'lucide-react'
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
      <div className="w-full max-w-md">{children}</div>
    </div>
  )
}

interface Props {
  project: Project
  targets: string[]
  file: string | null
  run: Run | null
  loadError: string | null
  onSelect: (path: string) => void
  onStarted: (run: Run) => void
}

// Everything the editor can show other than a finished translation
export default function EditorMain({ project, targets, file, run, loadError, onSelect, onStarted }: Props) {
  const noTargets = whyNoTargets(project.files, targets)
  if (noTargets === 'no_tex') {
    return (
      <Centered>
        <EmptyState icon={<FileText aria-hidden className="h-6 w-6" />} title="No LaTeX source in this project">
          Only PDFs or other files were found. Use “Add files” on the left to add the Beamer source of your
          slides; a PDF alone cannot be translated.
        </EmptyState>
      </Centered>
    )
  }
  if (noTargets === 'no_beamer') {
    return (
      <Centered>
        <EmptyState icon={<Presentation aria-hidden className="h-6 w-6" />} title="No Beamer presentation found">
          None of the .tex files is a Beamer presentation (it needs a beamer document class and a document
          body). Add the right file with “Add files” on the left.
        </EmptyState>
      </Centered>
    )
  }

  if (!file) {
    return (
      <Centered>
        <h2 className="text-base font-semibold text-slate-900">Choose a presentation to translate</h2>
        <p className="mt-1 text-sm text-slate-500">This project has {targets.length} Beamer files.</p>
        <ul className="mt-3 space-y-1.5">
          {targets.map((target) => (
            <li key={target}>
              <button
                type="button"
                onClick={() => onSelect(target)}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-left font-mono text-sm hover:border-brand-400 hover:bg-brand-50"
              >
                {target}
              </button>
            </li>
          ))}
        </ul>
      </Centered>
    )
  }

  if (run && !isFinished(run.status)) {
    return (
      <Centered>
        <div role="status" aria-live="polite" className="text-center">
          <Spinner className="mx-auto h-8 w-8 text-brand-700" />
          <p className="mt-3 text-base font-semibold text-slate-900">
            {run.status === 'queued' ? 'Waiting for a worker…' : 'Making your slides accessible…'}
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Compiling, finding figures, writing descriptions and tagging the PDF. Large decks can take a few
            minutes.
          </p>
          <div className="mx-auto mt-4 h-1.5 w-64 overflow-hidden rounded-full bg-slate-100">
            <div className="animate-indeterminate h-full w-1/4 rounded-full bg-brand-600" />
          </div>
          <p className="mt-2 text-xs text-slate-400">
            <span className="capitalize">{run.effort}</span> effort · elapsed{' '}
            <Elapsed since={run.started_at ?? run.created_at} />
          </p>
        </div>
      </Centered>
    )
  }

  let notice: ReactNode = null
  if (loadError) {
    notice = (
      <Alert tone="danger" title="Could not load this translation">
        {loadError}
      </Alert>
    )
  } else if (run?.status === 'failed') {
    notice = (
      <Alert tone="danger" title="The translation failed">
        {run.error_message || 'The pipeline stopped unexpectedly. Check the worker log for details.'}
      </Alert>
    )
  } else if (run?.status === 'blocked') {
    notice = (
      <Alert tone="warning" title="This file could not be translated yet">
        Reason: {run.stop_reason.replace(/_/g, ' ') || 'pre-flight check failed'}. If files are missing, add
        them with “Add files” on the left, then translate again.
      </Alert>
    )
  }

  return (
    <Centered>
      <div className="space-y-4">
        <div>
          <p className="truncate font-mono text-sm font-medium text-slate-800" title={file}>
            {file}
          </p>
          <p className="mt-0.5 text-sm text-slate-500">
            {run ? (
              <span className="inline-flex items-center gap-2">
                <RunStatusBadge status={run.status} /> Last attempt {relativeTime(run.created_at)}
              </span>
            ) : (
              'Not translated yet. Pick an effort level and start.'
            )}
          </p>
        </div>
        {notice}
        <TranslateForm projectId={project.id} file={file} onStarted={onStarted} />
        {run && run.status === 'succeeded' && (
          <Link
            to={editorPath(project.id, file, run.id)}
            className="block text-center text-sm text-brand-700 underline"
          >
            Open the earlier translation
          </Link>
        )}
      </div>
    </Centered>
  )
}
