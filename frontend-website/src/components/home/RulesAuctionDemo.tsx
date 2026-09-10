import { useState } from 'react'
import { ArrowRight, Check, RotateCcw } from 'lucide-react'

// Fixed illustrative bids. No production auction imports or network calls.
const frames = [
  { seconds: '45', bids: [1400, 1100, 1000, 900, 800, 700], message: 'One problem is revealed. The live screen tracks the five leading teams.', action: 'Start example' },
  { seconds: '30', bids: [1400, 1100, 1000, 900, 1150, 700], message: 'Team E raises its bid to 1,150 AC. Your team is currently outside the top five.', action: 'Place demo bid · 1,200 AC' },
  { seconds: '18', bids: [1400, 1100, 1000, 900, 1150, 1200], message: 'Your 1,200 AC bid moves you into second place. Bidding is still open.', action: 'Continue example' },
  { seconds: '05', bids: [1400, 1300, 1000, 900, 1150, 1200], message: 'Team B bids 1,300 AC. You move to third place, still inside the leading five.', action: 'Close example auction' },
  { seconds: '00', bids: [1400, 1300, 1000, 900, 1150, 1200], message: 'Time is up. The top five teams, including yours, win this same problem statement. Team D waits for the next cycle.', action: 'Replay example' },
] as const

export default function RulesAuctionDemo() {
  const [step, setStep] = useState(0)
  const frame = frames[step]
  const finished = step === frames.length - 1
  const teams = frame.bids.map((bid, index) => ({ bid, index })).sort((a, b) => b.bid - a.bid)
  const rank = teams.findIndex(team => team.index === 5)
  return <section id="rules-auction-demo" className="rulebook-demo" aria-labelledby="rulebook-demo-title" data-rulebook-reveal>
    <div className="rulebook-demo-heading"><p className="rulebook-label">Put it into practice</p><h3 id="rulebook-demo-title">A bid changes<br />the order.</h3><p>See how the leading five take shape.<br />Walk through one auction at your own pace.</p></div>
    <div className="rulebook-demo-stage">
      <div className="rulebook-demo-top"><span>Interactive example</span><span>{step + 1} / {frames.length}</span></div>
      <div className="rulebook-demo-auction"><div><span className="rulebook-label">Problem statement</span><h4>Challenge 01</h4><span className="rulebook-caption">Illustrative bids · AlumniCoins (AC)</span></div><div className={`rulebook-demo-clock ${finished ? 'is-finished' : ''}`}><strong>{frame.seconds}</strong><span>{finished ? 'Closed' : 'Seconds left'}</span></div></div>
      <div className="rulebook-demo-your-bid"><span>Your bid<strong key={frame.bids[5]}>{frame.bids[5].toLocaleString('en-IN')} <small>AC</small></strong></span><span>{finished ? 'Statement won' : rank < 5 ? `Position ${rank + 1} of 6` : 'Outside top five'}{finished && <Check size={17} aria-hidden="true" />}</span></div>
      <div className="rulebook-demo-leaders"><span className="rulebook-label">{finished ? 'Five winners · Same problem' : 'The leading five'}</span>
        <ol aria-label="Example auction ranking" className="rulebook-demo-ranks">
          {teams.map(({ index }, position) => {
            return <li key={index} style={{ transform: `translateY(${position * 100}%)` }} className={`${index === 5 ? 'is-you' : ''} ${position === 5 ? 'is-outside' : ''}`} aria-label={`${position + 1}. ${index === 5 ? 'Your team' : `Team ${String.fromCharCode(65 + index)}`}, ${frame.bids[index]} AlumniCoins${position === 5 ? ', outside top five' : ''}`}>
              <span aria-hidden="true">{String(position + 1).padStart(2, '0')}</span><span>{index === 5 ? 'Your team' : `Team ${String.fromCharCode(65 + index)}`}</span><strong>{frame.bids[index].toLocaleString('en-IN')} <small>AC</small></strong>{finished && position < 5 && <Check size={14} aria-hidden="true" />}
            </li>
          })}
        </ol>
      </div>
      <p className="rulebook-demo-status" role="status" aria-live="polite" aria-atomic="true">{frame.message}</p>
      <button className="rulebook-button" onClick={() => setStep(finished ? 0 : step + 1)}>{frame.action}{finished ? <RotateCcw size={16} aria-hidden="true" /> : <ArrowRight size={16} aria-hidden="true" />}</button>
      <p className="rulebook-demo-note">Demonstration only. Bids and time advance in steps. No real coins are used.</p>
    </div>
  </section>
}
