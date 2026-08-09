interface SectionHeadingProps {
  id?: string
  eyebrow?: string
  title: string
  description?: string
  align?: 'left' | 'center'
}

export default function SectionHeading({
  id,
  eyebrow,
  title,
  description,
  align = 'left',
}: SectionHeadingProps) {
  const alignClass = align === 'center' ? 'text-center mx-auto' : 'text-left'
  return (
    <div className={`max-w-2xl ${alignClass}`} id={id}>
      {eyebrow && (
        <p className="mb-3 flex items-center gap-3 text-xs font-semibold uppercase tracking-widest-xl text-purple-neon">
          {align === 'left' && <span className="h-px w-8 bg-purple-neon/60" aria-hidden="true" />}
          {eyebrow}
        </p>
      )}
      <h2 className="font-display text-3xl font-bold uppercase tracking-tight text-white md:text-4xl">
        {title}
      </h2>
      {description && (
        <p className="mt-4 text-base leading-relaxed text-ink-muted">{description}</p>
      )}
    </div>
  )
}