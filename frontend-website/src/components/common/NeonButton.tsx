import type { ButtonHTMLAttributes } from 'react'
import { Link } from 'react-router-dom'

type Variant = 'primary' | 'secondary' | 'gold' | 'danger'
type Size = 'sm' | 'md' | 'lg'

interface NeonButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  to?: string
}

const variantStyles: Record<Variant, string> = {
  primary:
    'bg-purple text-white border-purple-neon/60 hover:bg-purple-bright shadow-glow-purple hover:shadow-glow-purple-lg',
  secondary:
    'bg-transparent text-ink-main border-purple-bright/40 hover:border-purple-neon hover:bg-purple/10',
  gold: 'bg-gold text-black border-gold-bright hover:bg-gold-bright shadow-glow-gold',
  danger:
    'bg-transparent text-[rgb(var(--danger))] border-danger/50 hover:bg-danger/10 hover:border-danger',
}

const sizeStyles: Record<Size, string> = {
  sm: 'px-4 py-2 text-xs',
  md: 'px-6 py-3 text-sm',
  lg: 'px-8 py-4 text-sm md:text-base',
}

export default function NeonButton({
  variant = 'primary',
  size = 'md',
  to,
  className = '',
  children,
  ...rest
}: NeonButtonProps) {
  const classes = [
    'inline-flex items-center justify-center gap-2 rounded-lg border font-semibold uppercase tracking-widest transition-all duration-200 select-none',
    variantStyles[variant],
    sizeStyles[size],
    className,
  ].join(' ')

  if (to) {
    return (
      <Link to={to} className={classes}>
        {children}
      </Link>
    )
  }

  return (
    <button type="button" className={classes} {...rest}>
      {children}
    </button>
  )
}
