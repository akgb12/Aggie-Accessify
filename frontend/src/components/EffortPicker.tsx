import { useId } from 'react'
import { RadioGroup, RadioGroupItem } from '@/components/kit/radio-group'
import type { DefaultEffort } from '../types'
import { cx } from './classes'

const EFFORTS: { value: DefaultEffort; label: string; hint: string }[] = [
  { value: 'low', label: 'Low', hint: 'Up to one repair round. Fastest and cheapest.' },
  { value: 'medium', label: 'Medium', hint: 'Up to three repair rounds. Recommended for most decks.' },
  { value: 'high', label: 'High', hint: 'Up to five repair rounds, for long or diagram heavy decks.' },
]

// Choose how hard the run tries; a radio group, so arrow keys move between options
export default function EffortPicker({
  value,
  onChange,
  label = 'Effort',
  compact = false,
}: {
  value: DefaultEffort
  onChange: (value: DefaultEffort) => void
  label?: string
  compact?: boolean
}) {
  const id = useId()
  return (
    <div>
      <p id={`${id}-label`} className="text-sm font-semibold text-slate-800">
        {label}
      </p>
      <RadioGroup
        aria-labelledby={`${id}-label`}
        value={value}
        onValueChange={(next) => onChange(next as DefaultEffort)}
        className="mt-2 gap-0 overflow-hidden rounded-md border border-slate-300"
      >
        {EFFORTS.map((option) => (
          <label
            key={option.value}
            htmlFor={`${id}-${option.value}`}
            className={cx(
              'flex cursor-pointer items-start gap-3 border-b border-slate-200 px-3 last:border-b-0',
              compact ? 'py-2' : 'py-2.5',
              value === option.value ? 'bg-brand-50' : 'hover:bg-slate-50',
            )}
          >
            <RadioGroupItem
              id={`${id}-${option.value}`}
              value={option.value}
              className="mt-0.5 border-slate-300 shadow-none"
            />
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-slate-900">{option.label}</span>
              <span className="block text-sm text-slate-600">{option.hint}</span>
            </span>
          </label>
        ))}
      </RadioGroup>
    </div>
  )
}
