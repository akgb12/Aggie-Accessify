import { MousePointerClick } from 'lucide-react'
import { absoluteUrl } from '../api'
import { elementLabel, formatCost } from '../format'
import { statusColor, statusLabel } from '../status'
import type { ReviewElement } from '../types'
import StatusSwatch from './StatusSwatch'
import { Badge } from './ui'

function Heading({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">{children}</h3>
}

function PageSummary({
  pageNumber,
  flagged,
  onSelect,
}: {
  pageNumber: number
  flagged: ReviewElement[]
  onSelect: (id: string) => void
}) {
  return (
    <div className="p-4">
      <h2 className="text-base font-semibold text-slate-900">Page {pageNumber}</h2>
      {flagged.length === 0 ? (
        <p className="mt-1 flex items-start gap-2 text-sm text-slate-500">
          <MousePointerClick aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" />
          Nothing is flagged here. Click anything on the slide to inspect it.
        </p>
      ) : (
        <>
          <p className="mt-1 text-sm text-slate-500">
            {flagged.length} item{flagged.length === 1 ? '' : 's'} need attention on this page.
          </p>
          <ul className="mt-3 space-y-1">
            {flagged.map((element) => {
              const label = elementLabel(element)
              return (
                <li key={element.id}>
                  <button
                    onClick={() => onSelect(element.id)}
                    className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-slate-50"
                  >
                    <span className="mt-[7px]">
                      <StatusSwatch status={element.status} size={14} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-slate-800">{label.title}</span>
                      <span className="block truncate text-xs text-slate-400">
                        {statusLabel(element.status)} · {label.subtitle}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </div>
  )
}

function sourceLabel(source: ReviewElement['source']): string {
  if (!source?.file) return '–'
  // PowerPoint shapes are located by slide part and shape id rather than by line
  if (source.file.endsWith('.xml')) return `${source.file} · shape ${source.line_start}`
  const end = source.line_end !== source.line_start ? `–${source.line_end}` : ''
  return `${source.file}:${source.line_start}${end}`
}

export default function Inspector({
  element,
  pageNumber,
  flagged,
  onSelect,
}: {
  element: ReviewElement | null
  pageNumber: number
  flagged: ReviewElement[]
  onSelect: (id: string) => void
}) {
  if (!element) return <PageSummary pageNumber={pageNumber} flagged={flagged} onSelect={onSelect} />
  const label = elementLabel(element)
  const source = element.source
  const showAlt = element.type === 'figure' || Boolean(element.alt)

  return (
    <div className="space-y-5 p-4">
      <div>
        <h2 className="break-words text-base font-semibold leading-snug text-slate-900">{label.title}</h2>
        <p className="mt-0.5 text-sm text-slate-500">{label.subtitle}</p>
        <p className="mt-2 flex items-center gap-2 text-sm font-medium" style={{ color: statusColor(element.status) }}>
          <StatusSwatch status={element.status} size={18} />
          {statusLabel(element.status)}
        </p>
      </div>

      {element.text && element.text.length > label.title.length && (
        <blockquote className="rounded-md border-l-4 border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
          {element.text}
        </blockquote>
      )}

      {element.image_url && (
        <img
          src={absoluteUrl(element.image_url)}
          alt=""
          className="max-h-56 w-full rounded-md border border-slate-200 bg-white object-contain"
        />
      )}

      {showAlt && (
        <section>
          <Heading>Alt text</Heading>
          <textarea
            readOnly
            aria-label="Alt text"
            value={element.alt ?? ''}
            placeholder="No alt text yet"
            rows={4}
            className="block w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400"
          />
          {element.extended_description && (
            <>
              <div className="mt-3">
                <Heading>Extended description</Heading>
              </div>
              <textarea
                readOnly
                aria-label="Extended description"
                value={element.extended_description}
                rows={5}
                className="block w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              />
            </>
          )}
        </section>
      )}

      {element.issues.length > 0 && (
        <section>
          <Heading>Issues</Heading>
          <ul className="space-y-2">
            {element.issues.map((issue, index) => (
              <li key={`${issue.code}-${index}`} className="flex gap-2 text-sm text-slate-700">
                <Badge tone={issue.severity === 'error' ? 'danger' : 'warning'}>{issue.severity}</Badge>
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {element.history.length > 0 && (
        <section>
          <Heading>History</Heading>
          <ol className="relative space-y-3 border-l border-slate-200 pl-4">
            {element.history.map((entry, index) => (
              <li key={index} className="relative text-sm">
                <span
                  aria-hidden
                  className="absolute -left-[1.3rem] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-brand-600"
                />
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium text-slate-800">Round {entry.round ?? 0}</span>
                  <Badge tone={entry.by === 'model' ? 'info' : 'neutral'}>{entry.by ?? 'unknown'}</Badge>
                </div>
                {entry.change && <p className="text-slate-600">{entry.change}</p>}
                {(entry.input_tokens || entry.output_tokens) && (
                  <p className="text-xs text-slate-400">
                    {entry.input_tokens ?? 0} in · {entry.output_tokens ?? 0} out · {formatCost(entry.cost_usd ?? 0)}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      <details className="group text-sm">
        <summary className="cursor-pointer font-medium text-slate-500 hover:text-slate-800">Technical details</summary>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
          <dt className="text-slate-400">ID</dt>
          <dd className="break-all font-mono text-slate-700">{element.id}</dd>
          <dt className="text-slate-400">PDF role</dt>
          <dd>{element.role ?? '–'}</dd>
          <dt className="text-slate-400">Pages</dt>
          <dd>{element.pages.length > 0 ? element.pages.join(', ') : '–'}</dd>
          <dt className="text-slate-400">Source</dt>
          <dd className="font-mono">
            {sourceLabel(source)}
          </dd>
        </dl>
      </details>
    </div>
  )
}
