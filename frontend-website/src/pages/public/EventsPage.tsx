import GlassCard from '../../components/common/GlassCard'
import StatusBadge from '../../components/common/StatusBadge'
import NeonButton from '../../components/common/NeonButton'
import { eventContent } from '../../config/eventContent'
import { CalendarDays, Clock, MapPin, Users } from 'lucide-react'

const heroDetails = [
  { icon: CalendarDays, label: 'Date', value: eventContent.date },
  { icon: Clock, label: 'Time', value: eventContent.time },
  { icon: MapPin, label: 'Venue', value: eventContent.venue },
  { icon: Users, label: 'Team Size', value: eventContent.teamSize },
]

export default function EventsPage() {
  return (
    <>
      <section className="relative overflow-hidden pt-28 pb-12" aria-labelledby="event-title">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-hex-grid opacity-50"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-20 left-1/2 h-80 w-[36rem] -translate-x-1/2 rounded-full bg-purple/25 blur-[110px]"
        />
        <div className="container-page relative">
          <GlassCard glow="purple" className="mx-auto max-w-4xl p-8 md:p-12">
            <div className="flex flex-col items-center gap-6 md:flex-row md:items-start md:justify-between">
              <div>
                <p className="font-mono text-xs font-semibold uppercase tracking-widest-xl text-purple-neon">
                  {eventContent.presentedBy}
                </p>
                <h1
                  id="event-title"
                  className="mt-3 font-display text-3xl font-bold uppercase tracking-tight text-white md:text-4xl"
                >
                  {eventContent.brand}
                </h1>
                <p className="mt-2 font-display text-lg font-semibold uppercase tracking-widest text-gold-bright">
                  {eventContent.tagline}
                </p>
              </div>
              <StatusBadge status="active" className="shrink-0">
                {eventContent.statusLabel}
              </StatusBadge>
            </div>

            <p className="mt-6 text-base leading-relaxed text-ink-muted">
              {eventContent.eventSummary}
            </p>

            <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {heroDetails.map(({ icon: Icon, label, value }) => (
                <div
                  key={label}
                  className="rounded-lg border border-white/10 bg-bg-main/60 px-4 py-3"
                >
                  <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-ink-muted">
                    <Icon aria-hidden="true" className="h-4 w-4 text-gold-bright" />
                    {label}
                  </p>
                  <p className="mt-1 font-display text-sm font-bold uppercase tracking-wide text-white">
                    {value}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-8 flex flex-col items-stretch gap-4 sm:flex-row">
              <NeonButton to="/login" size="lg" variant="primary">
                Login to Enter
              </NeonButton>
              <NeonButton to="/#rules" size="lg" variant="secondary">
                View Rules
              </NeonButton>
            </div>
          </GlassCard>
        </div>
      </section>
    </>
  )
}