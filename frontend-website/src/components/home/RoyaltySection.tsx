import { royaltyHowItWorks } from '../../config/eventContent'
import { RuleBlock, RuleList } from './RuleUI'
import { RoyaltyCard } from './RuleCards'

export default function RoyaltySection() {
  return (
    <section className="py-10 md:py-12" aria-labelledby="royalty-heading">
      <div className="container-page">
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,0.34fr)_minmax(0,0.66fr)] lg:gap-6">
          <div className="flex justify-center lg:-mt-3">
            <RoyaltyCard />
          </div>
          <div>
            <RuleBlock kicker="The Twist" title="Royalty Bonus" />
            <RuleList items={royaltyHowItWorks} />
          </div>
        </div>
      </div>
    </section>
  )
}
