import type { HTMLAttributes, ReactNode } from 'react'

type Status = 'waiting' | 'active' | 'completed' | 'warning' | 'danger'

interface StatusBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  status: Status
  children?: ReactNode
}

const dotStyles: Record<Status, string> = {
  waiting: 'bg-[rgb(var(--text-muted))]',
  active: 'bg-purple-neon animate-pulse',
  completed: 'bg-success',
  warning: 'bg-gold-bright',
  danger: 'bg-danger',
}

const ringStyles: Record<Status, string> = {
  waiting: 'border-white/15 text-ink-muted',
  active: 'border-purple-neon/60 text-white',
  completed: 'border-success/50 text-success',
  warning: 'border-gold/50 text-gold-bright',
  danger: 'border-danger/50 text-danger',
}

export default function StatusBadge({
  status,
  className = '',
  children,
  ...rest
}: StatusBadgeProps) {
  return (
    <span
      className={[
        'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-widest',
        ringStyles[status],
        className,
      ].join(' ')}
      {...rest}
    >
      <span
        aria-hidden="true"
        className={`h-2 w-2 rounded-full ${dotStyles[status]}`}
      />
      {children ?? status}
    </span>
  )
}