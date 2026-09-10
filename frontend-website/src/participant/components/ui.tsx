import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react'

export function Card({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`card ${className}`} {...props} />
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'gold'
}

export function Button({ variant = 'primary', className = '', type = 'button', ...props }: ButtonProps) {
  return <button type={type} className={`button button--${variant} ${className}`} {...props} />
}

export function PageHeading({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <header className="page-heading">
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      {children && <p className="page-heading__copy">{children}</p>}
    </header>
  )
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Card className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </Card>
  )
}

export function Avatar({ name, size = 'md' }: { name: string; size?: 'sm' | 'md' | 'lg' }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
  return <span className={`avatar avatar--${size}`} aria-hidden="true">{initials}</span>
}

export function CoinBalance({ value, label = 'Coins' }: { value: number; label?: string }) {
  return (
    <span className="coin-balance" title={label}>
      <span className="coin-balance__coin" aria-hidden="true">🪙</span>
      <strong>{value.toLocaleString()}</strong>
      <small>{label}</small>
    </span>
  )
}

export function EmptyState({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <Card className="empty-state">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      {children && <p className="muted">{children}</p>}
    </Card>
  )
}
