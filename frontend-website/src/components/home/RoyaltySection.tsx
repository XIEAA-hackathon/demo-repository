import { royaltyHowItWorks } from '../../config/eventContent'

export default function RoyaltySection() {
  return (
    <section className="rulebook-royalty" aria-labelledby="royalty-heading">
      <header className="rulebook-royalty-header">
        <h3 id="royalty-heading">Royalty <span>Bonus.</span></h3>
        <p>Unused AlumniCoins become Royalty Points, rewarding teams that balance confidence at auction with restraint.</p>
      </header>

      <div className="rulebook-royalty-panel">
        <ol>
          {royaltyHowItWorks.map((rule, index) => (
            <li key={rule.title}>
              <span aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
              <div>
                <h4>{rule.title}</h4>
                <p>{rule.description}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
