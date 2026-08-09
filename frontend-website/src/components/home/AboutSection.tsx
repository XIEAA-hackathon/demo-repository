import GlassCard from '../common/GlassCard'
import SectionHeading from '../common/SectionHeading'
import { aboutPoints } from '../../config/eventContent'

export default function AboutSection() {
  return (
    <section className="py-20" aria-labelledby="about-heading">
      <div className="container-page">
        <SectionHeading
          id="about-heading"
          eyebrow="The Concept"
          title="About Bid to Build"
          description="Teams compete for problem statements using virtual bidding coins before building their solutions. Your bid buys the challenge \u2014 your code decides the winner."
        />

        <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {aboutPoints.map((point, index) => (
            <GlassCard key={point.title} glow="purple" className="relative">
              <span
                aria-hidden="true"
                className="font-mono text-5xl font-bold text-purple-neon [text-shadow:0_0_24px_rgb(var(--purple-neon)/0.6)] drop-shadow-[0_0_4px_rgb(var(--purple-neon)/0.5)]"
              >
                0{index + 1}
              </span>
              <h3 className="mt-4 font-display text-xl font-bold uppercase tracking-wider text-white">
                {point.title}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-ink-muted">
                {point.description}
              </p>
            </GlassCard>
          ))}
        </div>
      </div>
    </section>
  )
}