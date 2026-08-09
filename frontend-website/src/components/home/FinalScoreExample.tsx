import { Award, Crown, Equal, Plus, Trophy } from 'lucide-react'
import { royaltyScoreExample } from '../../config/eventContent'

const formulaParts = [
  {
    label: 'Alumni Evaluation Score',
    value: royaltyScoreExample.evaluationScore,
    icon: Award,
  },
  { label: 'Royalty Bonus', value: royaltyScoreExample.royaltyBonus, icon: Crown },
  { label: 'Final Score', value: royaltyScoreExample.finalScore, icon: Trophy, final: true },
]

export default function FinalScoreExample({ className = '' }: { className?: string }) {
  return (
    <div className={`overflow-hidden rounded-xl border border-purple/40 bg-gradient-to-br from-purple/15 via-surface/90 to-bg-secondary/80 shadow-glow-soft ${className}`}>
      <p className="border-b border-purple/25 px-3 py-2 text-center text-[10px] font-semibold uppercase tracking-widest-xl text-purple-neon">
        Final Score Formula
      </p>

      <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-center gap-1.5 px-2.5 py-3 text-center">
        {formulaParts.map((part, index) => {
          const Icon = part.icon
          return (
            <div key={part.label} className="contents">
              {index > 0 && (
                <span className="flex justify-center text-gold-bright" aria-hidden="true">
                  {index === 1 ? <Plus className="h-4 w-4" /> : <Equal className="h-4 w-4" />}
                </span>
              )}
              <div className="min-w-0 rounded-lg border border-white/10 bg-bg-secondary/55 px-1.5 py-2.5">
                <Icon className="mx-auto h-4 w-4 text-purple-neon" aria-hidden="true" />
                <p className="mt-1 flex min-h-7 items-center justify-center text-[8px] font-semibold uppercase leading-tight tracking-wide text-ink-muted sm:text-[9px]">
                  {part.label}
                </p>
                <p className={`mt-0.5 font-mono text-lg font-bold ${part.final ? 'text-gold-bright' : 'text-purple-neon'}`}>
                  {part.value}
                </p>
              </div>
            </div>
          )
        })}
      </div>

      <p className="border-t border-purple/25 px-3 py-2 text-center text-[11px] uppercase tracking-wide text-ink-muted">
        Remaining Coins: <span className="font-mono font-bold text-purple-neon">{royaltyScoreExample.remainingCoins}</span>
        <span className="mx-2 text-gold-bright" aria-hidden="true">&rarr;</span>
        Royalty Bonus: <span className="font-mono font-bold text-purple-neon">{royaltyScoreExample.royaltyBonus}</span>
      </p>

      <p className="flex items-center justify-center gap-2 border-t border-purple/25 px-3 py-2 text-center font-display text-[11px] font-bold uppercase tracking-wide text-white">
        <Trophy className="h-4 w-4 shrink-0 text-gold-bright" aria-hidden="true" />
        <span>
          The team with the <span className="text-gold-bright">highest final score</span> wins!
        </span>
      </p>
    </div>
  )
}
