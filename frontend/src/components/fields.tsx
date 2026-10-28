import { Eye, EyeOff } from 'lucide-react'
import { useId, useState } from 'react'
import type { InputHTMLAttributes } from 'react'
import { cx } from './classes'

const INPUT =
  'block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 disabled:bg-slate-50 disabled:text-slate-500'

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  hint?: string
}

export function TextField({ label, hint, className, ...rest }: FieldProps) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        aria-describedby={hint ? `${id}-hint` : undefined}
        className={cx('mt-1', INPUT, className)}
        {...rest}
      />
      {hint && (
        <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">
          {hint}
        </p>
      )}
    </div>
  )
}

export function PasswordField({ label, hint, className, ...rest }: FieldProps) {
  const id = useId()
  const [shown, setShown] = useState(false)
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <div className="relative mt-1">
        <input
          id={id}
          type={shown ? 'text' : 'password'}
          aria-describedby={hint ? `${id}-hint` : undefined}
          className={cx(INPUT, 'pr-10', className)}
          {...rest}
        />
        <button
          type="button"
          onClick={() => setShown(!shown)}
          aria-label={shown ? 'Hide password' : 'Show password'}
          aria-pressed={shown}
          className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-700"
        >
          {shown ? <EyeOff aria-hidden className="h-4 w-4" /> : <Eye aria-hidden className="h-4 w-4" />}
        </button>
      </div>
      {hint && (
        <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">
          {hint}
        </p>
      )}
    </div>
  )
}
