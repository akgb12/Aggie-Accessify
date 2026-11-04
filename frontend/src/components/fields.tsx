import { Eye, EyeOff } from 'lucide-react'
import { useId, useState } from 'react'
import type { InputHTMLAttributes, ReactNode } from 'react'
import { cx } from './classes'

const INPUT =
  'block h-10 w-full rounded-md border bg-white px-3 text-base text-slate-900 transition-colors placeholder:text-slate-400 hover:border-slate-500 focus-visible:border-brand-800 disabled:bg-slate-50 disabled:text-slate-500 sm:text-sm'

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  hint?: string
  // A problem with this field, shown under it and announced with the field
  error?: string | null
}

function describedBy(id: string, hint?: string, error?: string | null): string | undefined {
  const ids = [error ? `${id}-error` : null, hint ? `${id}-hint` : null].filter(Boolean)
  return ids.length > 0 ? ids.join(' ') : undefined
}

function FieldText({ id, hint, error }: { id: string; hint?: string; error?: string | null }): ReactNode {
  return (
    <>
      {error && (
        <p id={`${id}-error`} className="mt-1.5 text-sm font-medium text-danger">
          {error}
        </p>
      )}
      {hint && (
        <p id={`${id}-hint`} className="mt-1.5 text-sm text-slate-600">
          {hint}
        </p>
      )}
    </>
  )
}

export function TextField({ label, hint, error, className, ...rest }: FieldProps) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-semibold text-slate-800">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, hint, error)}
        className={cx('mt-1.5', INPUT, error ? 'border-danger' : 'border-slate-300', className)}
        {...rest}
      />
      <FieldText id={id} hint={hint} error={error} />
    </div>
  )
}

export function PasswordField({ label, hint, error, className, ...rest }: FieldProps) {
  const id = useId()
  const [shown, setShown] = useState(false)
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-semibold text-slate-800">
        {label}
      </label>
      <div className="relative mt-1.5">
        <input
          id={id}
          type={shown ? 'text' : 'password'}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, hint, error)}
          className={cx(INPUT, 'pr-11', error ? 'border-danger' : 'border-slate-300', className)}
          {...rest}
        />
        <button
          type="button"
          onClick={() => setShown(!shown)}
          aria-label={shown ? 'Hide password' : 'Show password'}
          aria-pressed={shown}
          className="absolute inset-y-1 right-1 flex w-9 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900"
        >
          {shown ? <EyeOff aria-hidden className="h-4 w-4" /> : <Eye aria-hidden className="h-4 w-4" />}
        </button>
      </div>
      <FieldText id={id} hint={hint} error={error} />
    </div>
  )
}
