import { Phone, Mail } from 'lucide-react'
import { eventContent } from '../../config/eventContent'

export default function ContactSection() {
  return (
    <section className="border-t border-purple/25 py-16" aria-labelledby="contact-heading">
      <div className="container-page">
        <p
          id="contact-heading"
          className="text-center font-mono text-xs font-semibold uppercase tracking-widest-xl text-purple-neon"
        >
          Contact
        </p>
        <h2 className="mt-3 text-center font-display text-3xl font-bold uppercase tracking-tight text-white md:text-4xl">
          Get in <span className="text-gradient-purple">Touch</span>
        </h2>

        <div className="mx-auto mt-10 grid max-w-2xl gap-5 sm:grid-cols-2">
          <a
            href={`tel:${eventContent.contactPhone}`}
            className="group rounded-xl border border-white/10 bg-surface/60 p-6 transition-colors hover:border-purple-neon/60"
          >
            <Phone
              aria-hidden="true"
              className="h-6 w-6 text-purple-neon group-hover:text-purple-bright"
            />
            <p className="mt-4 text-xs font-semibold uppercase tracking-widest text-ink-muted">
              Phone / Text
            </p>
            <p className="mt-1 font-display text-lg font-semibold text-white">
              {eventContent.contactPhone}
            </p>
          </a>

          <a
            href={`mailto:${eventContent.contactEmail}`}
            className="group rounded-xl border border-white/10 bg-surface/60 p-6 transition-colors hover:border-purple-neon/60"
          >
            <Mail
              aria-hidden="true"
              className="h-6 w-6 text-purple-neon group-hover:text-purple-bright"
            />
            <p className="mt-4 text-xs font-semibold uppercase tracking-widest text-ink-muted">
              Email
            </p>
            <p className="mt-1 break-all font-display text-lg font-semibold text-white">
              {eventContent.contactEmail}
            </p>
          </a>
        </div>
      </div>
    </section>
  )
}