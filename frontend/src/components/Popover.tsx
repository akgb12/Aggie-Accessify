import { ChevronDown } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { cx } from './classes'

export default function Popover({
  label,
  icon,
  children,
  align = 'right',
  buttonClassName,
  width = 'w-72',
  open: controlledOpen,
  onOpenChange,
}: {
  label: ReactNode
  icon?: ReactNode
  children: ReactNode
  align?: 'left' | 'right'
  buttonClassName?: string
  width?: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  const [innerOpen, setInnerOpen] = useState(false)
  const open = controlledOpen ?? innerOpen
  const setOpen = useCallback(
    (next: boolean) => {
      setInnerOpen(next)
      onOpenChange?.(next)
    },
    [onOpenChange],
  )
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [open, setOpen])

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen(!open)}
        className={cx(
          'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium',
          buttonClassName ?? 'text-slate-700 hover:bg-slate-100',
        )}
      >
        {icon}
        {label}
        <ChevronDown aria-hidden className="h-3.5 w-3.5 opacity-70" />
      </button>
      {open && (
        <div
          role="dialog"
          className={cx(
            'absolute z-40 mt-1 rounded-lg border border-slate-200 bg-white p-3 text-sm shadow-lg',
            width,
            align === 'right' ? 'right-0' : 'left-0',
          )}
        >
          {children}
        </div>
      )}
    </div>
  )
}
