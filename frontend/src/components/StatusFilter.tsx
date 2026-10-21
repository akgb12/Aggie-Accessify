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
      <legend className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">
        Show elements that are
      </legend>
      <ul className="space-y-0.5">
        {LEGEND_STATUSES.map((status) => {
          const count = counts[status] ?? 0
          return (
            <li key={status}>
              <label className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 hover:bg-slate-50 has-[:disabled]:cursor-default has-[:disabled]:opacity-40">
                <input
                  type="checkbox"
                  checked={visible.has(status)}
                  disabled={count === 0}
                  onChange={() => onToggle(status)}
                  className="h-3.5 w-3.5 accent-[#500000]"
                />
                <StatusSwatch status={status} size={16} />
                <span className="flex-1 text-slate-800">{statusLabel(status)}</span>
                <span className="text-xs tabular-nums text-slate-400">{count}</span>
              </label>
            </li>
          )
        })}
      </ul>
      <button type="button" onClick={onShowAll} className="mt-2 text-sm font-medium text-brand-700 hover:underline">
        Show all
      </button>
    </fieldset>
  )
}
