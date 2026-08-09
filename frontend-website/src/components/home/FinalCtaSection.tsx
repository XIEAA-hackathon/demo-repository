import NeonButton from '../common/NeonButton'
import { eventContent } from '../../config/eventContent'

export default function FinalCtaSection() {
  return (
    <section className="relative overflow-hidden py-24" aria-label="Call to action">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-hex-grid opacity-40"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-1/2 h-80 w-[36rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-purple/25 blur-[110px]"
      />
      <div className="container-page relative text-center">
        <p className="font-mono text-xs font-semibold uppercase tracking-widest-xl text-gold-bright">
          {eventContent.date} &middot; {eventContent.time} &middot; {eventContent.venue}
        </p>
        <h2 className="mt-5 font-display text-4xl font-bold uppercase tracking-tight text-white sm:text-5xl md:text-6xl">
          Ready to <span className="text-gradient-purple">Bid?</span>
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-ink-muted">
          {eventContent.presentedBy} welcomes you to the table. Register your team and claim
          your first stack of virtual coins.
        </p>
        <div className="mt-10">
          <NeonButton to="/event" size="lg" variant="gold">
            Enter the Event
          </NeonButton>
        </div>
      </div>
    </section>
  )
}