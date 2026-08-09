import type { HTMLAttributes } from 'react'

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  glow?: 'purple' | 'gold' | 'none'
}

const glowStyles = {
  purple: 'border-purple/30 hover:border-purple-neon/60 shadow-glow-soft',
  gold: 'border-gold/30 hover:border-gold/60 shadow-glow-soft',
  none: 'border-white/10',
}

export default function GlassCard({
  glow = 'purple',
  className = '',
  children,
  ...rest
}: GlassCardProps) {
  return (
    <div
      className={[
        'rounded-xl border bg-surface/70 backdrop-blur-sm p-6 transition-colors duration-200',
        glowStyles[glow],
        className,
      ].join(' ')}
      {...rest}
    >
      {children}
    </div>
  )
}
