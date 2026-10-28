import { X } from 'lucide-react'
import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { cx } from './classes'

// A native modal dialog: the browser traps focus, makes the page behind inert and handles Escape
export default function Modal({
  title,
  onClose,
  children,
  className,
  bare = false,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  className?: string
  bare?: boolean
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const element = dialog.current
    const opener = document.activeElement as HTMLElement | null
    if (element && !element.open) element.showModal()
    return () => opener?.focus?.()
  }, [])

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === dialog.current) onClose()
      }}
      className={cx(
        'm-auto w-[calc(100%-2rem)] rounded-xl border border-slate-200 bg-white p-0 text-slate-900 shadow-xl backdrop:bg-slate-900/40',
        className ?? 'max-w-md',
      )}
    >
      <div className={cx('flex items-center justify-between gap-3', bare ? 'hidden' : 'px-5 pt-4')}>
        <h2 id={titleId} className="text-base font-semibold">
          {title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
        >
          <X aria-hidden className="h-4 w-4" />
        </button>
      </div>
      {bare && (
        <h2 id={titleId} className="sr-only">
          {title}
        </h2>
      )}
      {children}
    </dialog>
  )
}
