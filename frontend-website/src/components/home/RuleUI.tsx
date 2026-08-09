import type { RuleItem } from '../../config/eventContent'
import { ruleIcon } from './RuleCards'

const GOLD_TERMS = [
  '1000 AlumniCoins',
  'One Problem at a Time',
  'Top 5',
  'Live Auction',
  'Wild Cards',
  'Bonus Problem Statements',
  '4-Hour Build',
  'Maximum 10 Points',
  '1 Point per 100 Coins',
  'Spend vs Save',
  'Final Score',
  'Highest Score Wins',
]

export function HighlightTitle({ text }: { text: string }) {
  const lower = text.toLowerCase()
  const term = GOLD_TERMS.find((t) => lower.includes(t.toLowerCase()))
  if (!term) return <>{text}</>
  const start = lower.indexOf(term.toLowerCase())
  const end = start + term.length
  return (
    <>
      {text.slice(0, start)}
      <span className="text-gold-bright">{text.slice(start, end)}</span>
      {text.slice(end)}
    </>
  )
}

export function RuleList({ items, twoCol = true }: { items: RuleItem[]; twoCol?: boolean }) {
  return (
    <ol className={`grid gap-2.5 ${twoCol ? 'sm:grid-cols-2' : ''}`}>
      {items.map((item, index) => {
        const Icon = ruleIcon(item.icon)
        return (
          <li
            key={`${item.title}-${index}`}
            className="group flex items-start gap-2.5 rounded-xl border border-purple/40 bg-gradient-to-br from-purple/15 via-surface/90 to-surface/60 p-3.5 shadow-glow-soft transition-all duration-200 hover:-translate-y-0.5 hover:border-purple-neon/65 hover:shadow-glow-purple"
          >
            <span
              aria-hidden="true"
              className="font-mono text-base font-bold leading-7 text-purple-neon"
            >
              {String(index + 1).padStart(2, '0')}
            </span>
            <span
              aria-hidden="true"
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-gold/40 bg-gold/15"
            >
              <Icon className="h-4 w-4 text-gold-bright" />
            </span>
            <div className="min-w-0">
              <h4 className="font-display text-sm font-bold uppercase leading-snug tracking-wide text-white xl:text-[15px]">
                <HighlightTitle text={item.title} />
              </h4>
              <p className="mt-1 text-[13px] leading-snug text-ink-muted/95 xl:text-sm">
                {item.description}
              </p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export function RuleBlock({ kicker, title }: { kicker: string; title: string }) {
  return (
    <div className="mb-4">
      <p className="mb-1.5 flex items-center gap-3 text-xs font-semibold uppercase tracking-widest-xl text-purple-neon">
        <span aria-hidden="true" className="h-px w-8 bg-purple-neon/60" />
        {kicker}
      </p>
      <h3 className="font-display text-2xl font-bold uppercase tracking-tight text-white md:text-[2rem]">
        {title}
      </h3>
    </div>
  )
}
