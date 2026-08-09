import GlassCard from '../common/GlassCard'
import SectionHeading from '../common/SectionHeading'
import { CalendarDays, Clock, MapPin, Users } from 'lucide-react'
import { eventContent } from '../../config/eventContent'

const details = [
  { icon: CalendarDays, label: 'Date', value: eventContent.date },
  { icon: Clock, label: 'Time', value: eventContent.time },
  { icon: MapPin, label: 'Venue', value: eventContent.venue },
  { icon: Users, label: 'Team Size', value: eventContent.teamSize },
]

export default function EventDetailsSection() {
  return (
    <section className="py-20" aria-labelledby="details-heading">
      <div className="container-page">
        <SectionHeading
          id="details-heading"
          eyebrow="The Night"
          title="Event Details"
          align="center"
        />

        <div className="mx-auto mt-12 grid max-w-4xl grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {details.map(({ icon: Icon, label, value }) => (
            <GlassCard key={label} glow="gold" className="text-center">
              <Icon
                aria-hidden="true"
                className="mx-auto h-6 w-6 text-gold-bright"
              />
              <p className="mt-4 text-xs font-semibold uppercase tracking-widest text-ink-muted">
                {label}
              </p>
              <p className="mt-1 font-display text-lg font-bold uppercase tracking-wide text-white">
                {value}
              </p>
            </GlassCard>
          ))}
        </div>
      </div>
    </section>
  )
}