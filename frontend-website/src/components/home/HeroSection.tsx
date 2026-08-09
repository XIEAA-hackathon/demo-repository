import NeonButton from '../common/NeonButton'
import { eventContent } from '../../config/eventContent'

export default function HeroSection() {
  return (
    <section className="relative overflow-hidden" aria-label="Hero">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-hex-grid opacity-60"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-32 left-1/2 h-[36rem] w-[36rem] -translate-x-1/2 rounded-full bg-purple/30 blur-[120px]"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute right-[-10rem] top-40 h-72 w-72 rounded-full bg-purple-neon/20 blur-[100px]"
      />

      <div className="container-page relative flex min-h-[calc(100vh-4rem)] flex-col items-center justify-center py-20 text-center">
        <p className="mb-4 font-mono text-xs font-semibold uppercase tracking-widest-xl text-purple-neon">
          Presented by {eventContent.presentedBy}
        </p>

        <h1 className="sr-only">XIE Alumni Hackathon &mdash; Bid to Build</h1>

        <div
          aria-hidden="true"
          className="flex flex-col font-display text-[clamp(3.5rem,13vw,9rem)] font-bold uppercase leading-[0.85] tracking-tight"
        >
          <span className="text-gradient-purple">Bid</span>
          <span className="text-gradient-gold">To</span>
          <span className="text-white [text-shadow:0_0_36px_rgb(var(--purple-neon)/0.55)]">
            Build
          </span>
        </div>

        <div className="mt-6 h-px w-40 bg-gradient-to-r from-transparent via-gold/70 to-transparent" />

        <p className="mt-6 max-w-md text-base font-medium leading-relaxed text-ink-muted sm:text-lg">
          {eventContent.heroLine}
        </p>

        <div className="mt-10 flex flex-col items-stretch gap-4 sm:flex-row">
          <NeonButton to="/event" size="lg" variant="primary">
            Enter Event
          </NeonButton>
          <NeonButton to="/#timeline" size="lg" variant="secondary">
            View Timeline
          </NeonButton>
        </div>

        <div className="mt-16 flex flex-wrap items-center justify-center gap-x-10 gap-y-4 font-mono text-xs uppercase tracking-widest text-ink-muted">
          <span>{eventContent.date}</span>
          <span aria-hidden="true" className="text-gold-bright">&#9670;</span>
          <span>{eventContent.time}</span>
          <span aria-hidden="true" className="text-gold-bright">&#9670;</span>
          <span>{eventContent.venue}</span>
        </div>
      </div>
    </section>
  )
}