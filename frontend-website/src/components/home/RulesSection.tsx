import SectionHeading from '../common/SectionHeading'
import { CircleAlert, Info } from 'lucide-react'
import {
  auctionConfig,
  evaluationCriteria,
  roundOneRules,
  roundTwoConfig,
  roundTwoSteps,
  wildcardRules,
} from '../../config/eventContent'
import { RuleBlock, RuleList } from './RuleUI'
import FinalScoreExample from './FinalScoreExample'
import {
  AuctionCard,
  EvaluationCard,
  RoundTwoCard,
  WildCardCard,
  ruleIcon,
} from './RuleCards'

function RoundTwoSection() {
  const DurationIcon = ruleIcon('timer')
  const TeamIcon = ruleIcon('layers')

  return (
    <div className="mt-16 rounded-2xl border border-purple/35 bg-gradient-to-b from-purple/10 via-surface/70 to-bg-secondary/70 p-5 shadow-glow-soft md:p-7 lg:mt-20">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div>
          <RuleBlock kicker="Round 2" title="The Build" />
          <p className="max-w-2xl text-sm leading-relaxed text-ink-muted md:text-base">
            {roundTwoConfig.intro}
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-3">
          <div className="min-w-36 rounded-xl border border-gold/30 bg-bg-secondary/70 px-4 py-3">
            <dt className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-purple-neon">
              <DurationIcon className="h-4 w-4" aria-hidden="true" /> Duration
            </dt>
            <dd className="mt-1 font-display text-lg font-bold uppercase text-gold-bright">{roundTwoConfig.duration}</dd>
          </div>
          <div className="min-w-36 rounded-xl border border-gold/30 bg-bg-secondary/70 px-4 py-3">
            <dt className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-purple-neon">
              <TeamIcon className="h-4 w-4" aria-hidden="true" /> Team Size
            </dt>
            <dd className="mt-1 font-display text-lg font-bold uppercase text-gold-bright">{roundTwoConfig.teamSize}</dd>
          </div>
        </dl>
      </div>

      <div className="mt-8 grid items-center gap-8 lg:grid-cols-[minmax(0,0.45fr)_minmax(0,0.55fr)] lg:gap-6">
        <div className="flex justify-center">
          <RoundTwoCard />
        </div>
        <div>
          <RuleBlock kicker="The Build Process" title="How It Works" />
          <RuleList items={roundTwoSteps} />
        </div>
      </div>
    </div>
  )
}

function EvaluationSection() {
  return (
    <div className="mt-16 grid items-stretch gap-8 lg:mt-20 lg:grid-cols-[minmax(0,0.6fr)_minmax(0,0.4fr)] lg:gap-4">
      <div className="flex min-w-0 flex-col">
        <div>
          <RuleBlock kicker="Evaluation Criteria" title="To Be Finalized" />
          <RuleList items={evaluationCriteria} />
        </div>
        <FinalScoreExample className="mt-4" />
      </div>
      <div className="flex items-center justify-center lg:h-full">
        <EvaluationCard />
      </div>
    </div>
  )
}

export default function RulesSection() {
  return (
    <section id="rules" className="py-12 md:py-14" aria-labelledby="rules-heading">
      <div className="container-page">
        <SectionHeading
          id="rules-heading"
          eyebrow="The Fine Print"
          title="Rules of the Table"
          align="center"
        />

        {/* Section A: Round 1 Problem Statement Auction */}
        <div className="mt-9 grid items-center gap-8 lg:mt-10 lg:grid-cols-12 lg:gap-6">
          <div className="flex justify-center lg:col-span-5">
            <AuctionCard />
          </div>
          <div className="lg:col-span-7">
            <RuleBlock kicker="Round 1" title="Problem Statement Auction" />
            <RuleList items={roundOneRules} />
          </div>
        </div>

        {/* Section B: Wild Card Auction */}
        <div className="mt-16 grid items-center gap-8 lg:mt-20 lg:grid-cols-12 lg:gap-6">
          <div className="flex justify-center lg:order-2 lg:col-span-5">
            <WildCardCard />
          </div>
          <div className="lg:order-1 lg:col-span-7">
            <RuleBlock kicker={'Round 1 \u2014 Part 2'} title="Wild Card Auction" />
            <RuleList items={wildcardRules} />
            <p className="mt-4 flex items-center gap-2 text-xs uppercase tracking-widest text-ink-muted">
              <Info aria-hidden="true" className="h-4 w-4 shrink-0 text-purple-neon" />
              <span>
                Presentation: {auctionConfig.wildCardCount} Wild Cards &middot;{' '}
                {auctionConfig.bonusStatementCount} Bonus Problem Statements
              </span>
            </p>
          </div>
        </div>

        {/* Section C: Round 2 Build */}
        <RoundTwoSection />

        {/* Section D: Evaluation Criteria */}
        <EvaluationSection />

        <p className="mx-auto mt-8 flex max-w-3xl items-center gap-2 text-xs uppercase tracking-widest text-ink-muted">
          <CircleAlert aria-hidden="true" className="h-4 w-4 shrink-0 text-gold-bright" />
          Rules are temporary and subject to final organizer review.
        </p>
      </div>
    </section>
  )
}
