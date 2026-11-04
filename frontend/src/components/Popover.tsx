import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Popover as Root, PopoverContent, PopoverTrigger } from '@/components/kit/popover'
import { cx } from './classes'

// A labelled button that opens a panel. Built on Radix, so focus moves into the panel, Escape and
// outside clicks close it, and focus returns to the button.
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
  function setOpen(next: boolean) {
    setInnerOpen(next)
    onOpenChange?.(next)
  }

  return (
    <Root open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        className={cx(
          'inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-semibold transition-colors',
          buttonClassName ?? 'text-slate-800 hover:bg-slate-100 data-[state=open]:bg-slate-100',
        )}
      >
        {icon}
        {label}
        <ChevronDown aria-hidden className="h-4 w-4 opacity-70" />
      </PopoverTrigger>
      <PopoverContent
        align={align === 'right' ? 'end' : 'start'}
        sideOffset={6}
        className={cx('rounded-lg p-4 text-sm', width)}
      >
        {children}
      </PopoverContent>
    </Root>
  )
}
