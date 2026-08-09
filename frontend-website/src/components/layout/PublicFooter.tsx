import { Link, useLocation } from 'react-router-dom'
import { Mail, MapPin, Phone } from 'lucide-react'
import { eventContent } from '../../config/eventContent'
import { smoothScrollToTop } from '../../utils/scroll'

const footerNav = [
  { label: 'Home', to: '/' },
  { label: 'Event', to: '/event' },
  { label: 'How It Works', to: '/event' },
  { label: 'Rules', to: '/#rules' },
]

export default function PublicFooter() {
  const { pathname } = useLocation()

  const handleHomeClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (pathname === '/') {
      e.preventDefault()
      smoothScrollToTop()
    }
  }

  return (
    <footer className="border-t border-purple/25 bg-bg-secondary/60">
      <div className="container-page py-12">
        <div className="grid gap-10 md:grid-cols-3">
          <div>
            <p className="font-display text-lg font-bold uppercase tracking-widest text-white">
              XIE Alumni Committee
            </p>
            <p className="mt-1 text-sm font-semibold uppercase tracking-widest-xl text-gold-bright">
              Bid to Build
            </p>
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-ink-muted">
              {eventContent.footerBlurb}
            </p>
          </div>

          <nav aria-label="Footer">
            <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-purple-neon">
              Navigate
            </p>
            <ul className="space-y-2">
              {footerNav.map((item) => (
                <li key={item.label}>
                  <Link
                    to={item.to}
                    onClick={item.to === '/' ? handleHomeClick : undefined}
                    className="text-sm text-ink-muted transition-colors hover:text-purple-neon"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <div>
            <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-purple-neon">
              Event Contact
            </p>
            <ul className="space-y-2 text-sm text-ink-muted">
              <li className="flex items-center gap-2">
                <MapPin aria-hidden="true" className="h-4 w-4 text-gold-bright" />
                {eventContent.venue}, {eventContent.date}
              </li>
              <li>
                <a
                  href={`tel:${eventContent.contactPhone}`}
                  className="flex items-center gap-2 transition-colors hover:text-purple-neon"
                >
                  <Phone aria-hidden="true" className="h-4 w-4 text-gold-bright" />
                  {eventContent.contactPhone}
                </a>
              </li>
              <li>
                <a
                  href={`mailto:${eventContent.contactEmail}`}
                  className="flex items-center gap-2 transition-colors hover:text-purple-neon"
                >
                  <Mail aria-hidden="true" className="h-4 w-4 text-gold-bright" />
                  {eventContent.contactEmail}
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 flex flex-col items-center justify-between gap-3 border-t border-white/10 pt-6 text-xs text-ink-muted sm:flex-row">
          <p>&copy; {new Date().getFullYear()} XIE Alumni Committee. All rights reserved.</p>
          <p className="uppercase tracking-widest">Bid. Build. Win.</p>
        </div>
      </div>
    </footer>
  )
}