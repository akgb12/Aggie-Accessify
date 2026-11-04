import {
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Info,
  LoaderCircle,
  TriangleAlert,
} from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { buttonClasses, cx } from './classes'
import type { ButtonSize, ButtonVariant } from './classes'

export type Tone = 'neutral' | 'brand' | 'success' | 'info' | 'warning' | 'danger'

const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'bg-slate-50 text-slate-700 ring-slate-200',
  brand: 'bg-brand-50 text-brand-800 ring-brand-200',
  success: 'bg-green-50 text-success ring-green-200',
  info: 'bg-blue-50 text-info ring-blue-200',
  warning: 'bg-amber-50 text-warning ring-amber-200',
  danger: 'bg-red-50 text-danger ring-red-200',
}

export function PageContainer({ children }: { children: ReactNode }) {
  // Standard centered page width for pages that scroll normally
  return <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-8 sm:py-10">{children}</div>
}

export function Badge({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: Tone
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={cx(
        'inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-semibold ring-1 ring-inset',
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <LoaderCircle aria-hidden className={cx('h-4 w-4 animate-spin', className)} />
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  icon?: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cx(buttonClasses(variant, size), className)}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  )
}

export function Card({
  title,
  description,
  action,
  children,
  className,
  flush = false,
}: {
  title?: ReactNode
  description?: ReactNode
  action?: ReactNode
  children?: ReactNode
  className?: string
  flush?: boolean
}) {
  return (
    <section className={cx('rounded-lg border border-slate-200 bg-white', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4">
          <div>
            {title && <h2 className="text-base font-semibold text-slate-900">{title}</h2>}
            {description && <p className="mt-0.5 text-sm text-slate-600">{description}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={flush ? 'pt-3' : 'px-5 pb-5 pt-3'}>{children}</div>
    </section>
  )
}

const ALERT_STYLES: Record<
  'info' | 'success' | 'warning' | 'danger',
  { box: string; icon: ReactNode }
> = {
  info: { box: 'border-blue-200 bg-blue-50 text-slate-900 [&_svg]:text-info', icon: <Info className="h-5 w-5" /> },
  success: {
    box: 'border-green-200 bg-green-50 text-slate-900 [&_svg]:text-success',
    icon: <CircleCheck className="h-5 w-5" />,
  },
  warning: {
    box: 'border-amber-200 bg-amber-50 text-slate-900 [&_svg]:text-warning',
    icon: <TriangleAlert className="h-5 w-5" />,
  },
  danger: {
    box: 'border-red-200 bg-red-50 text-slate-900 [&_svg]:text-danger',
    icon: <CircleAlert className="h-5 w-5" />,
  },
}

export function Alert({
  tone = 'info',
  title,
  children,
  action,
}: {
  tone?: 'info' | 'success' | 'warning' | 'danger'
  title?: ReactNode
  children?: ReactNode
  action?: ReactNode
}) {
  const style = ALERT_STYLES[tone]
  return (
    <div
      role={tone === 'danger' ? 'alert' : 'status'}
      className={cx('flex gap-3 rounded-lg border p-3 text-sm', style.box)}
    >
      <span aria-hidden className="mt-0.5 shrink-0">
        {style.icon}
      </span>
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={title ? 'mt-0.5' : ''}>{children}</div>}
      </div>
      {action}
    </div>
  )
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center rounded-lg bg-slate-50 px-6 py-12 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-white text-slate-600 ring-1 ring-slate-200">
        {icon}
      </div>
      <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
      {children && <p className="mt-1 max-w-md text-sm text-slate-600">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function Breadcrumbs({ items }: { items: { label: string; to?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-2">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-slate-600">
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} className="flex items-center gap-1">
            {index > 0 && <ChevronRight aria-hidden className="h-3.5 w-3.5" />}
            {item.to ? (
              <Link to={item.to} className="rounded underline-offset-4 hover:text-brand-800 hover:underline">
                {item.label}
              </Link>
            ) : (
              <span aria-current="page" className="font-medium text-slate-700">
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  )
}

export function PageHeader({
  title,
  subtitle,
  actions,
  breadcrumbs,
  display = false,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  breadcrumbs?: { label: string; to?: string }[]
  // Fixed page titles use the brand display face; names people typed stay in the body face
  display?: boolean
}) {
  return (
    <div className="mb-8">
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} />}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1
            className={cx(
              'text-slate-900',
              display ? 'font-display-caps text-3xl' : 'truncate text-2xl font-semibold tracking-tight',
            )}
          >
            {title}
          </h1>
          {subtitle && <p className="mt-2 max-w-2xl text-base text-slate-600">{subtitle}</p>}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    </div>
  )
}

const METER_COLORS = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
}

export function Meter({
  value,
  label,
  tone,
}: {
  value: number | null
  label: string
  tone: 'success' | 'warning' | 'danger'
}) {
  const clamped = value === null ? 0 : Math.max(0, Math.min(100, value))
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
      className="h-2 w-full overflow-hidden rounded-full bg-slate-100"
    >
      <div className={cx('h-full rounded-full', METER_COLORS[tone])} style={{ width: `${clamped}%` }} />
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx('animate-pulse rounded-lg bg-slate-100', className)} />
}

export function RunStatusBadge({ status }: { status: string }) {
  const tones: Record<string, Tone> = {
    queued: 'neutral',
    running: 'info',
    succeeded: 'success',
    failed: 'danger',
    blocked: 'warning',
  }
  const labels: Record<string, string> = {
    queued: 'Queued',
    running: 'Running',
    succeeded: 'Done',
    failed: 'Failed',
    blocked: 'Needs files',
  }
  return (
    <Badge tone={tones[status] ?? 'neutral'}>
      {(status === 'running' || status === 'queued') && <Spinner className="h-3 w-3" />}
      {labels[status] ?? status}
    </Badge>
  )
}
