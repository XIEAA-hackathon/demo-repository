import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDown, ArrowRight, Check, LockKeyhole } from 'lucide-react'
import {
  auctionConfig, evaluationCriteria, roundOneRules, roundTwoConfig,
  roundTwoSteps, royaltyScoreExample, wildcardRules,
} from '../../config/eventContent'
import type { RuleItem } from '../../config/eventContent'
import RulesAuctionDemo from './RulesAuctionDemo'
import RulesMotionBackground from './RulesMotionBackground'
import RoyaltySection from './RoyaltySection'
import './RulesSection.css'

// Presentation only. Preserve every published rule from its source of truth.
const chapters = [
  { label: 'Starting capital', title: 'Every team starts equal.', rules: roundOneRules.slice(0, 1) },
  { label: 'The reveal', title: 'One challenge. One live auction.', rules: roundOneRules.slice(1, 3) },
  { label: 'The winning five', title: 'Five teams. The same challenge.', rules: roundOneRules.slice(3, 5) },
  { label: 'The next cycle', title: 'A place for every team.', rules: roundOneRules.slice(5) },
  { label: 'The wild cards', title: 'A second chance to choose.', rules: wildcardRules },
  { label: 'The build', title: 'Four hours. Make it work.', rules: roundTwoSteps.slice(0, 3) },
  { label: 'The evaluation', title: 'Let your solution speak.', rules: roundTwoSteps.slice(3, 4) },
  { label: 'The final score', title: 'Build well. Spend wisely.', rules: roundTwoSteps.slice(4) },
]
const number = (value: number) => String(value).padStart(2, '0')

function RuleCopy({ items }: { items: RuleItem[] }) {
  return <dl className="rulebook-copy">{items.map(item => <div key={item.title}>
    <dt>{item.title}</dt><dd>{item.description}</dd>
  </div>)}</dl>
}

function Capital({ active }: { active: boolean }) {
  const output = useRef<HTMLSpanElement>(null)
  const played = useRef(false)
  useEffect(() => {
    if (!active || played.current || !output.current) return
    played.current = true
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (preference.matches) return
    let frame = 0
    const start = performance.now()
    const finish = () => {
      cancelAnimationFrame(frame)
      if (output.current) output.current.textContent = auctionConfig.startingCoins.toLocaleString('en-IN')
    }
    const tick = (now: number) => {
      const progress = Math.min((now - start) / 850, 1)
      if (output.current) output.current.textContent = Math.round(auctionConfig.startingCoins * (1 - (1 - progress) ** 4)).toLocaleString('en-IN')
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    preference.addEventListener('change', finish)
    return () => { finish(); preference.removeEventListener('change', finish) }
  }, [active])
  return <div className="rulebook-capital" aria-label={`${auctionConfig.startingCoins} AlumniCoins per team`}>
    <span ref={output} aria-hidden="true">{auctionConfig.startingCoins.toLocaleString('en-IN')}</span>
    <span aria-hidden="true">AlumniCoins <span className="rulebook-capital-note">/ per team</span></span>
  </div>
}

function Reveal() {
  const [next, setNext] = useState(false)
  return <div className="rulebook-reveal">
    <div className="rulebook-reveal-current" aria-live="polite"><span className="rulebook-label">Revealed now</span>
      <strong key={String(next)}>Problem {next ? '02' : '01'}</strong><span>Open for bidding</span>
    </div>
    <div className="rulebook-reveal-hidden"><LockKeyhole size={19} aria-hidden="true" /><span>Upcoming statements<br />stay hidden</span></div>
    <button className="rulebook-text-button" onClick={() => setNext(!next)}>{next ? 'Reset reveal example' : 'Preview the next cycle'}<ArrowRight size={16} aria-hidden="true" /></button>
  </div>
}

function Five({ active }: { active: boolean }) {
  return <div className={`rulebook-five ${active ? 'is-active' : ''}`} aria-label="The five highest bidders receive the same problem statement">
    <div className="rulebook-five-teams" aria-hidden="true">{Array.from({ length: auctionConfig.topWinners }, (_, i) => <span key={i} style={{ transitionDelay: `${i * 70}ms` }}>{number(i + 1)}</span>)}</div>
    <div className="rulebook-five-result"><Check size={18} aria-hidden="true" /> One shared problem statement</div>
    <span className="rulebook-caption">Ranked by bid when the timer ends</span>
  </div>
}

function Cycles() {
  const [cycle, setCycle] = useState(1)
  return <div className="rulebook-cycles">
    <div className="rulebook-cycle-dots" aria-hidden="true">{Array.from({ length: auctionConfig.exampleTeams }, (_, i) => <span key={i} className={i < cycle * auctionConfig.topWinners ? 'is-seated' : ''} />)}</div>
    <p aria-live="polite"><strong>{cycle * auctionConfig.topWinners} / {auctionConfig.exampleTeams}</strong> teams seated</p>
    <button className="rulebook-text-button" onClick={() => setCycle(cycle === 6 ? 1 : cycle + 1)}>{cycle === 6 ? 'Replay seating example' : 'Reveal the next problem'}<ArrowRight size={16} aria-hidden="true" /></button>
    <span className="rulebook-caption">Illustration of the published 30-team example</span>
  </div>
}

function Wildcards() {
  const [choice, setChoice] = useState<number | null>(null)
  return <div className="rulebook-wildcards">
    <span className="rulebook-label">Explore a wild card winner’s choice</span>
    <div className="rulebook-choices">{Array.from({ length: auctionConfig.bonusStatementCount }, (_, i) => <button key={i} aria-pressed={choice === i} onClick={() => setChoice(i)}>
      <span>Bonus</span><strong>{number(i + 1)}</strong><span>{choice === i ? 'Selected' : 'Choose'} {choice === i && <Check size={13} aria-hidden="true" />}</span>
    </button>)}</div>
    <p className="rulebook-caption" aria-live="polite">{choice === null ? 'Three bonus statements. Each winner must choose one.' : `Example: Bonus ${number(choice + 1)} replaces your original statement.`}</p>
  </div>
}

function Build({ active }: { active: boolean }) {
  return <div className={`rulebook-build ${active ? 'is-active' : ''}`}>
    <div><strong>04<span>h</span></strong><span>{roundTwoConfig.teamSize}<br />One functional solution</span></div>
    <div className="rulebook-build-line" aria-hidden="true"><span /></div>
    <div className="rulebook-build-labels"><span>Final statement locked</span><span>Submit before deadline</span></div>
  </div>
}

function Score() {
  return <div className="rulebook-score">
    <span className="rulebook-label">An example, in numbers</span>
    <div className="rulebook-equation">
      <div><strong>{royaltyScoreExample.evaluationScore}</strong><span>Evaluation</span></div><span aria-label="plus">+</span>
      <div><strong>{royaltyScoreExample.royaltyBonus}</strong><span>Royalty bonus</span></div><span aria-label="equals">=</span>
      <div><strong>{royaltyScoreExample.finalScore}</strong><span>Final score</span></div>
    </div>
    <p className="rulebook-caption">{royaltyScoreExample.remainingCoins} remaining → {royaltyScoreExample.royaltyBonus} royalty points.</p>
    <p>The team with the highest Final Score wins.</p>
  </div>
}

export default function RulesSection() {
  const root = useRef<HTMLElement>(null)
  const [active, setActive] = useState(0)
  const [capitalVisible, setCapitalVisible] = useState(false)
  useEffect(() => {
    const section = root.current
    if (!section) return
    // Track chapter changes without a scroll listener or scroll interception.
    let observer: IntersectionObserver
    const observe = () => {
      observer?.disconnect()
      // Pixel margins follow viewport height; percentage root margins use width.
      const readingLine = Math.round(window.innerHeight * .3)
      observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          entry.target.classList.add('has-entered')
          const index = entry.target.getAttribute('data-chapter')
          if (index !== null) {
            setActive(Number(index))
            if (index === '0') setCapitalVisible(true)
          }
        }
      }, { rootMargin: `-${readingLine}px 0px -${window.innerHeight - readingLine - 2}px 0px`, threshold: 0 })
      section.querySelectorAll('[data-rulebook-reveal]').forEach(element => observer.observe(element))
    }
    observe()
    window.addEventListener('resize', observe)
    return () => { observer.disconnect(); window.removeEventListener('resize', observe) }
  }, [])

  return <section ref={root} id="rules" className="rulebook" aria-labelledby="rules-heading">
    <RulesMotionBackground />
    <div className="container-page">
      <header className="rulebook-intro" data-rulebook-reveal>
        <p className="rulebook-label">The rulebook</p>
        <h2 id="rules-heading">Before the bid.<br /><span>Know the game.</span></h2>
        <p>Your coins. Your challenge. Your next four hours.<br className="rulebook-desktop-break" /> Everything you need to know before you build.</p>
        <a className="rulebook-text-button" href="#rule-chapter-1">Eight chapters, one clear path<ArrowDown size={17} aria-hidden="true" /></a>
        <div className="rulebook-intro-footer"><span>01–08 / Bid to Build</span><a href="#rules-auction-demo">Try the auction example<ArrowRight size={15} aria-hidden="true" /></a></div>
      </header>
      <div className="rulebook-story">
        <aside className="rulebook-index" aria-label="Rulebook chapters">
          <div className="rulebook-counter" aria-label={`Chapter ${active + 1} of ${chapters.length}`}>
            <div className="rulebook-counter-window" aria-hidden="true"><div style={{ transform: `translateY(-${active * 1.1}em)` }}>{chapters.map((_, i) => <span key={i}>{number(i + 1)}</span>)}</div></div>
            <span aria-hidden="true">/ {number(chapters.length)}</span>
          </div>
          <p className="rulebook-index-title">{chapters[active].label}</p>
          <nav aria-label="Jump to a rule chapter">
            <div className="rulebook-track" aria-hidden="true"><span style={{ transform: `scaleY(${active / (chapters.length - 1)})` }} /></div>
            {chapters.map((chapter, i) => <a key={chapter.label} href={`#rule-chapter-${i + 1}`} aria-current={active === i ? 'step' : undefined} className={i <= active ? 'is-complete' : ''}>
              <span className="rulebook-marker" aria-hidden="true" /><span className="rulebook-nav-number">{number(i + 1)}</span><span>{chapter.label}</span>
            </a>)}
          </nav>
          <a href="#rules-auction-demo" className="rulebook-index-demo">See it in action <ArrowRight size={14} aria-hidden="true" /></a>
        </aside>
        <div className="rulebook-chapters">
          {chapters.map((chapter, i) => <article id={`rule-chapter-${i + 1}`} key={chapter.label} className={`rulebook-chapter ${i === active ? 'is-current' : ''}`} data-chapter={i} data-rulebook-reveal aria-labelledby={`rule-title-${i}`} tabIndex={-1}>
            <div className="rulebook-chapter-body">
              <p className="rulebook-label"><span>{number(i + 1)}</span> {chapter.label}</p>
              <h3 id={`rule-title-${i}`}>{chapter.title}</h3>
              {i === 0 && <Capital active={capitalVisible} />}
              {i === 1 && <Reveal />}
              {i === 2 && <Five active={active === i} />}
              {i === 3 && <Cycles />}
              {i === 4 && <Wildcards />}
              {i === 5 && <><Build active={active === i} /><p className="rulebook-build-intro">{roundTwoConfig.intro}</p></>}
              <RuleCopy items={chapter.rules} />
              {i === 6 && <><p className="rulebook-provisional">Evaluation criteria · To be finalized</p><RuleCopy items={evaluationCriteria} /></>}
              {i === 7 && <Score />}
            </div>
          </article>)}
        </div>
      </div>
      <RulesAuctionDemo />
      <RoyaltySection />
      <footer className="rulebook-finale" data-rulebook-reveal>
        <p className="rulebook-label">08 / 08 · You know the rules.</p>
        <h3>{['BID.', 'BUILD.', 'WIN.'].map(word => <span key={word}><span>{word}</span></span>)}</h3>
        <Link className="rulebook-button" to="/event">Enter the Event<ArrowRight size={18} aria-hidden="true" /></Link>
        <p className="rulebook-final-note">Rules are temporary and subject to final organizer review.</p>
      </footer>
    </div>
  </section>
}
