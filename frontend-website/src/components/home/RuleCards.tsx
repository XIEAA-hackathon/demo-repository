import type { LucideIcon } from 'lucide-react'
import {
  ArrowLeftRight,
  Award,
  Banknote,
  Clock,
  Coins,
  Eye,
  FileText,
  Gavel,
  Gem,
  Hammer,
  Hand,
  Layers,
  LogOut,
  Monitor,
  Repeat,
  Scale,
  Timer,
  TrendingUp,
  Trophy,
  WandSparkles,
} from 'lucide-react'
import type { RuleIconKey } from '../../config/eventContent'
import evaluationImg from './evaluation.png'
import round1Img from './round1.png'
import round2Img from './round2.png'
import royaltyImg from './royalty.png'
import wildcardImg from './wildcard.png'

const iconMap: Partial<Record<RuleIconKey, LucideIcon>> = {
  coins: Coins,
  eye: Eye,
  gavel: Gavel,
  timer: Timer,
  hand: Hand,
  monitor: Monitor,
  trophy: Trophy,
  logout: LogOut,
  repeat: Repeat,
  layers: Layers,
  file: FileText,
  clock: Clock,
  award: Award,
  gem: Gem,
  swap: ArrowLeftRight,
  hammer: Hammer,
  banknote: Banknote,
  trending: TrendingUp,
  scale: Scale,
  wand: WandSparkles,
}

export function ruleIcon(key?: RuleIconKey): LucideIcon {
  return (key && iconMap[key]) || Coins
}

function CardImage({
  src,
  alt,
  emphasized = false,
  compact = false,
  matchDesktopHeight = false,
  wideDesktop = false,
}: {
  src: string
  alt: string
  emphasized?: boolean
  compact?: boolean
  matchDesktopHeight?: boolean
  wideDesktop?: boolean
}) {
  const widthClass = matchDesktopHeight
    ? 'w-[88%] max-w-[20rem] lg:h-full lg:w-full lg:max-w-[27rem]'
    : wideDesktop
    ? 'w-[88%] max-w-[20rem] lg:w-full lg:max-w-[27rem]'
    : compact
    ? 'w-[88%] max-w-[20rem]'
    : `w-[92%] sm:w-full ${emphasized ? 'max-w-[30rem]' : 'max-w-[28rem]'}`

  return (
    <div className={`relative mx-auto ${widthClass}`}>
      <div
        aria-hidden="true"
        className="absolute -inset-3 rounded-[2.5rem] bg-gold/15 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="absolute -inset-1.5 rounded-[2rem] bg-purple-neon/20 blur-xl"
      />
      <img
        src={src}
        alt={alt}
        loading="lazy"
        className={`relative w-full object-contain drop-shadow-[0_0_32px_rgba(0,0,0,0.55)] ${matchDesktopHeight ? 'h-auto lg:h-full lg:max-h-full' : 'h-auto'}`}
      />
    </div>
  )
}

export function AuctionCard() {
  return <CardImage src={round1Img} alt="Round 1 Problem Statement Auction card" />
}

export function WildCardCard() {
  return <CardImage src={wildcardImg} alt="Wild Card Auction card" />
}

export function RoundTwoCard() {
  return <CardImage src={round2Img} alt="Round 2 build process card" emphasized />
}

export function EvaluationCard() {
  return (
    <CardImage
      src={evaluationImg}
      alt="Evaluation criteria and final score card"
      matchDesktopHeight
    />
  )
}

export function RoyaltyCard() {
  return <CardImage src={royaltyImg} alt="Royalty Bonus card" wideDesktop />
}
