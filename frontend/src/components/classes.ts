export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'destructive'
export type ButtonSize = 'sm' | 'md'

// Flat buttons: maroon only for the main action, a darker press state, no drop shadows
export function buttonClasses(variant: ButtonVariant = 'secondary', size: ButtonSize = 'md') {
  return cx(
    'inline-flex items-center justify-center gap-2 rounded-md font-semibold transition-colors',
    'active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50',
    size === 'sm' ? 'h-8 px-3 text-sm' : 'h-9 px-4 text-sm',
    variant === 'primary' && 'bg-brand-800 text-white hover:bg-brand-700 active:bg-brand-900',
    variant === 'secondary' &&
      'border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 active:bg-slate-100',
    variant === 'ghost' && 'text-slate-700 hover:bg-slate-100 active:bg-slate-200',
    variant === 'danger' && 'text-danger hover:bg-red-50 active:bg-red-100',
    variant === 'destructive' && 'bg-danger text-white hover:bg-red-800 active:bg-red-900',
  )
}
