import type { ReactNode } from 'react'

// The fixed-height editor layout: toolbar on top, then an optional left rail, the main area and an optional right panel
export default function EditorFrame({
  toolbar,
  left,
  center,
  right,
}: {
  toolbar: ReactNode
  left: ReactNode | null
  center: ReactNode
  right: ReactNode | null
}) {
  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      {toolbar}
      <div className="flex min-h-0 flex-1">
        {left && (
          <aside aria-label="Project files and slides" className="w-72 shrink-0 border-r border-slate-200">
            {left}
          </aside>
        )}
        <section aria-label="Main area" className="min-w-0 flex-1">
          {center}
        </section>
        {right && (
          <aside aria-label="Inspector" className="w-80 shrink-0 overflow-auto border-l border-slate-200">
            {right}
          </aside>
        )}
      </div>
    </div>
  )
}
