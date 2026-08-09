import { useEffect } from 'react'
import NeonButton from '../../components/common/NeonButton'
import GlassCard from '../../components/common/GlassCard'
import { Lock } from 'lucide-react'
import { participantLoginUrl } from '../../config/env'

export default function LoginPage() {
  useEffect(() => { window.location.replace(participantLoginUrl) }, [])
  return (
    <section className="relative flex min-h-[70vh] items-center justify-center py-28">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-hex-grid opacity-40" />
      <div className="container-page relative">
        <GlassCard glow="purple" className="mx-auto max-w-md p-8 text-center">
          <span className="inline-flex h-12 w-12 items-center justify-center rounded-full border border-purple-neon/50 bg-purple/20 shadow-glow-purple"><Lock aria-hidden="true" className="h-5 w-5 text-purple-neon" /></span>
          <h1 className="mt-4 font-display text-2xl font-bold uppercase tracking-wide text-white">Opening participant login</h1>
          <p className="mt-2 text-sm text-ink-muted">You are being redirected to the secure participant portal.</p>
          <div className="mt-8"><NeonButton to={participantLoginUrl} size="lg" variant="primary" className="w-full">Continue to login</NeonButton></div>
        </GlassCard>
      </div>
    </section>
  )
}
