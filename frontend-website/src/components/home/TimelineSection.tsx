import SectionHeading from '../common/SectionHeading'
import { eventFlowSteps } from '../../config/eventContent'
import { ruleIcon } from './RuleCards'

export default function TimelineSection() {
  return (
    <section
      id="timeline"
      className="scroll-mt-24 py-12 md:py-16"
      aria-labelledby="timeline-heading"
    >
      <div className="container-page">
        <SectionHeading
          id="timeline-heading"
          eyebrow="Bid to Build"
          title="The Complete Event Flow"
          align="center"
        />

        <ol className="mx-auto mt-9 max-w-6xl overflow-hidden rounded-2xl border border-purple/45 bg-surface/65 shadow-glow-soft">
          {eventFlowSteps.map((stage, index) => {
            const Icon = ruleIcon(stage.icon)
            const [phase, detail] = stage.title.split(' \u2014 ')
            const isFinal = index === eventFlowSteps.length - 1

            return (
              <li
                key={stage.title}
                className={`grid grid-cols-[3.75rem_minmax(0,1fr)] items-center border-b px-3 py-3.5 last:border-b-0 md:grid-cols-[5rem_minmax(14rem,0.85fr)_minmax(0,1.15fr)] md:gap-5 md:px-5 ${
                  isFinal
                    ? 'border-gold/40 bg-gradient-to-r from-gold/12 via-purple/12 to-gold/8'
                    : 'border-purple/25 bg-gradient-to-r from-purple/10 via-surface/85 to-bg-secondary/60'
                }`}
              >
                <span
                  className={`row-span-2 font-mono text-2xl font-bold md:row-span-1 md:text-3xl ${
                    isFinal ? 'text-gold-bright' : 'text-purple-neon'
                  }`}
                  aria-hidden="true"
                >
                  {String(index + 1).padStart(2, '0')}
                </span>

                <div className="flex min-w-0 items-center gap-3">
                  <span
                    aria-hidden="true"
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border md:h-11 md:w-11 ${
                      isFinal
                        ? 'border-gold/55 bg-gold/15 shadow-glow-soft'
                        : 'border-purple-neon/45 bg-purple/15'
                    }`}
                  >
                    <Icon className={`h-5 w-5 md:h-6 md:w-6 ${isFinal ? 'text-gold-bright' : 'text-purple-neon'}`} />
                  </span>
                  <h3 className={`font-display text-sm font-bold uppercase leading-snug tracking-wide md:text-base ${isFinal ? 'text-gold-bright' : 'text-white'}`}>
                    {phase}
                    {detail && <span className="block text-gold-bright">{detail}</span>}
                  </h3>
                </div>

                <p className="col-start-2 mt-2 text-[13px] leading-relaxed text-ink-muted md:col-start-3 md:mt-0 md:text-sm">
                  {stage.description}
                </p>
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}
