import { useState } from 'react'
import { NavLink, Link, useLocation } from 'react-router-dom'
import { Menu, X, LogIn } from 'lucide-react'
import { smoothScrollToTop } from '../../utils/scroll'

const navItems = [
  { label: 'Home', to: '/' },
  { label: 'Event', to: '/event' },
  { label: 'Timeline', to: '/#timeline' },
  { label: 'Rules', to: '/#rules' },
  { label: 'How It Works', to: '/event' },
]

export default function PublicNavbar() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()

  const handleHomeClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (pathname === '/') {
      e.preventDefault()
      smoothScrollToTop()
    }
  }

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-purple/25 bg-bg-main/80 backdrop-blur-md">
      <nav className="container-page flex h-16 items-center justify-between gap-4" aria-label="Primary">
        <Link
          to="/"
          className="flex items-center gap-3"
          onClick={(e) => {
            setOpen(false)
            handleHomeClick(e)
          }}
        >
          <span
            aria-hidden="true"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-purple-neon/50 bg-purple/20 font-display text-lg font-bold text-purple-neon shadow-glow-purple"
          >
            X
          </span>
          <span className="leading-tight">
            <span className="block font-display text-sm font-bold uppercase tracking-widest text-white">
              XIE Alumni Hackathon
            </span>
            <span className="block text-[10px] font-semibold uppercase tracking-widest-xl text-gold-bright">
              Bid to Build
            </span>
          </span>
        </Link>

        <ul className="hidden items-center gap-1 lg:flex">
          {navItems.map((item) => (
            <li key={item.label}>
              <NavLink
                to={item.to}
                onClick={item.to === '/' ? handleHomeClick : undefined}
                className="rounded-md px-3 py-2 text-sm font-medium uppercase tracking-wider text-ink-muted transition-colors hover:text-purple-neon"
              >
                {item.label}
              </NavLink>
            </li>
          ))}
          <li className="ml-2">
            <Link
              to="/login"
              className="inline-flex items-center gap-2 rounded-lg border border-purple-neon/60 bg-purple/20 px-4 py-2 text-sm font-semibold uppercase tracking-widest text-white shadow-glow-purple transition-all hover:bg-purple/40"
            >
              <LogIn aria-hidden="true" className="h-4 w-4" />
              Login
            </Link>
          </li>
        </ul>

        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-purple/40 text-ink-main lg:hidden"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
        </button>
      </nav>

      <div
        id="mobile-nav"
        className={`border-t border-purple/25 bg-bg-main/95 backdrop-blur-md lg:hidden ${
          open ? 'block' : 'hidden'
        }`}
      >
        <ul className="container-page flex flex-col gap-1 py-4">
          {navItems.map((item) => (
            <li key={item.label}>
              <NavLink
                to={item.to}
                onClick={(e) => {
                  setOpen(false)
                  if (item.to === '/') handleHomeClick(e)
                }}
                className="block rounded-md px-3 py-3 text-sm font-medium uppercase tracking-wider text-ink-muted hover:bg-purple/10 hover:text-purple-neon"
              >
                {item.label}
              </NavLink>
            </li>
          ))}
          <li className="mt-2">
            <Link
              to="/login"
              className="flex items-center justify-center gap-2 rounded-lg border border-purple-neon/60 bg-purple/20 px-4 py-3 text-sm font-semibold uppercase tracking-widest text-white shadow-glow-purple"
              onClick={() => setOpen(false)}
            >
              <LogIn aria-hidden="true" className="h-4 w-4" />
              Login
            </Link>
          </li>
        </ul>
      </div>
    </header>
  )
}