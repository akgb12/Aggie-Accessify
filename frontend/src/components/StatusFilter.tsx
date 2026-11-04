import { LEGEND_STATUSES, statusLabel } from '../status'
import type { ElementStatus } from '../types'
import StatusSwatch from './StatusSwatch'

export default function StatusFilter({
  counts,
  visible,
  onToggle,
  onShowAll,
}: {
  counts: Partial<Record<ElementStatus, number>>
  visible: Set<ElementStatus>
  onToggle: (status: ElementStatus) => void
  onShowAll: () => void
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-semibold text-slate-800">Show items that are</legend>
      <ul className="space-y-0.5">
        {LEGEND_STATUSES.map((status) => {
          const count = counts[status] ?? 0
          return (
            <li key={status}>
              <label className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1.5 hover:bg-slate-50 has-[:disabled]:cursor-default has-[:disabled]:opacity-50">
                <input
                  type="checkbox"
                  checked={visible.has(status)}
                  disabled={count === 0}
                  onChange={() => onToggle(status)}
                  className="h-4 w-4 accent-[#500000]"
                />
                <StatusSwatch status={status} size={16} />
                <span className="flex-1 text-slate-800">{statusLabel(status)}</span>
                <span className="text-sm tabular-nums text-slate-600">{count}</span>
              </label>
            </li>
          )
        })}
      </ul>
      <button type="button" onClick={onShowAll} className="mt-3 text-sm font-semibold text-brand-800 underline underline-offset-4">
        Show all
      </button>
    </fieldset>
  )
}
