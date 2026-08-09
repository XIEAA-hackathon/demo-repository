import { Outlet } from 'react-router-dom'
import PublicNavbar from '../components/layout/PublicNavbar'
import PublicFooter from '../components/layout/PublicFooter'
import ContactSection from '../components/layout/ContactSection'
import ScrollToHash from '../components/common/ScrollToHash'
import ScrollToTop from '../components/common/ScrollToTop'

export default function PublicLayout() {
  return (
    <div className="min-h-screen flex flex-col relative">
      <ScrollToTop />
      <ScrollToHash />
      <PublicNavbar />
      <main className="flex-1 pt-16">
        <Outlet />
      </main>
      <ContactSection />
      <PublicFooter />
    </div>
  )
}