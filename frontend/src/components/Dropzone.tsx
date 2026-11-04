import { Upload } from 'lucide-react'
import { useState } from 'react'
import { buttonClasses, cx } from './classes'
import { Spinner } from './ui'

export default function Dropzone({
  onFiles,
  busy,
  compact = false,
}: {
  onFiles: (files: File[]) => void
  busy: boolean
  compact?: boolean
}) {
  const [dragging, setDragging] = useState(false)

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        const files = Array.from(e.dataTransfer.files)
        if (files.length > 0 && !busy) onFiles(files)
      }}
      className={cx(
        'flex flex-col items-center justify-center rounded-lg border border-dashed text-center transition-colors',
        compact ? 'px-4 py-6' : 'px-6 py-12',
        dragging ? 'border-brand-800 bg-brand-50' : 'border-slate-300 bg-slate-50',
      )}
    >
      <span
        aria-hidden
        className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-white text-slate-700 ring-1 ring-slate-200"
      >
        {busy ? <Spinner className="h-5 w-5" /> : <Upload className="h-5 w-5" />}
      </span>
      <p className="text-base font-semibold text-slate-900" aria-live="polite">
        {busy ? 'Uploading your files' : 'Drag your slides here'}
      </p>
      <p className="mt-1 text-sm text-slate-600">A PowerPoint deck (.pptx), or a .zip of a LaTeX Beamer project</p>
      <label
        className={cx(
          buttonClasses('primary'),
          'mt-5 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand-600',
          busy && 'pointer-events-none opacity-50',
        )}
      >
        Choose files
        <input
          type="file"
          multiple
          disabled={busy}
          className="sr-only"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? [])
            if (files.length > 0) onFiles(files)
            e.target.value = ''
          }}
        />
      </label>
    </div>
  )
}
