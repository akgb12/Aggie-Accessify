import { ImageOff } from 'lucide-react'
import { useState } from 'react'
import { absoluteUrl } from '../api'
import { anchorToPin, bboxToRect } from '../geometry'
import { statusStyle } from '../status'
import type { ReviewElement, ReviewPage } from '../types'

interface Props {
  page: ReviewPage
  // Display size in CSS pixels; the overlay itself is drawn in PDF points so it never depends on image loading
  width: number
  height: number
  elements: ReviewElement[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export default function PageOverlay({ page, width, height, elements, selectedId, onSelect }: Props) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  const pageSize = { widthPt: page.width_points, heightPt: page.height_points }
  const space = { width: page.width_points, height: page.height_points }
  const pinRadius = page.width_points * 0.011

  return (
    <div className="relative bg-white shadow-md ring-1 ring-slate-300" style={{ width, height }}>
      {failedUrl === page.image_url ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-slate-500">
          <ImageOff aria-hidden className="h-6 w-6" />
          Could not load the page image.
        </div>
      ) : (
        <img
          src={absoluteUrl(page.image_url)}
          alt={`Rendered slide, page ${page.number}`}
          className="absolute inset-0 h-full w-full select-none"
          draggable={false}
          decoding="async"
          onError={() => setFailedUrl(page.image_url)}
        />
      )}
      <svg
        viewBox={`0 0 ${space.width} ${space.height}`}
        className="absolute inset-0 h-full w-full"
        role="group"
        aria-label="Element overlay"
      >
        {elements.map((element) => {
          const style = statusStyle(element.status)
          const selected = element.id === selectedId
          const common = { className: 'cursor-pointer', onClick: () => onSelect(element.id) }
          if (element.bbox) {
            const rect = bboxToRect(element.bbox, pageSize, space)
            return (
              <rect
                key={element.id}
                {...rect}
                {...common}
                rx={2}
                fill={style.color}
                fillOpacity={selected ? 0.28 : 0.1}
                stroke={style.color}
                strokeWidth={selected ? 3.5 : 2}
                strokeDasharray={style.dash || undefined}
                vectorEffect="non-scaling-stroke"
              >
                <title>
                  {element.id} · {style.label}
                </title>
              </rect>
            )
          }
          if (element.anchor) {
            const pin = anchorToPin(element.anchor, pageSize, space)
            return (
              <circle
                key={element.id}
                {...common}
                cx={pin.x}
                cy={pin.y}
                r={selected ? pinRadius * 1.5 : pinRadius}
                fill={style.color}
                stroke="white"
                strokeWidth={2}
                vectorEffect="non-scaling-stroke"
              >
                <title>
                  {element.id} · {style.label}
                </title>
              </circle>
            )
          }
          return null
        })}
      </svg>
    </div>
  )
}
