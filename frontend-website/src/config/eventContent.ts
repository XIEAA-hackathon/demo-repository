export const auctionConfig = {
  startingCoins: 5000,
  topWinners: 5,
  timerRange: '30\u201390 seconds',
  exampleTeams: 30,
  wildCardCount: 3,
  bonusStatementCount: 3,
} as const

export const eventContent = {
  brand: 'XIE Alumni Hackathon',
  presentedBy: 'XIE Alumni Committee',
  tagline: 'Bid to Build',
  heroLine: 'Choose your challenge. Bid on your confidence. Build to win.',
  date: '29 August',
  time: '10:00 AM',
  venue: 'XIE\nSeminar Hall',
  teamSize: '2\u20134 Members',
  contactPhone: '09372663183',
  contactEmail: 'xiealumni@xavier.ac.in',
  footerBlurb:
    'Teams compete for problem statements using virtual bidding coins, then build their solutions. The theme of this year\u2019s alumni hackathon: Bid to Build.',
  eventSummary:
    'XIE Alumni Hackathon unites teams of 2\u20134 to bid for real problem statements using virtual coins, then build working solutions under pressure. The boldest, sharpest bids win the right to build \u2014 and the best build wins the pot.',
  statusLabel: 'Waiting to Start',
}

export const aboutPoints = [
  {
    title: 'Bid',
    description:
      'Teams are issued virtual bidding coins. Every challenge has a floor, and every table can get crowded.',
  },
  {
    title: 'Outbid',
    description:
      'Only the leader commits coins. Go all-in on one statement or spread thin across many \u2014 your call.',
  },
  {
    title: 'Build',
    description:
      'The winning bid buys the problem statement. What you build next is what gets judged.',
  },
]

export type RuleIconKey =
  | 'coins'
  | 'eye'
  | 'gavel'
  | 'timer'
  | 'hand'
  | 'monitor'
  | 'trophy'
  | 'logout'
  | 'repeat'
  | 'layers'
  | 'file'
  | 'clock'
  | 'award'
  | 'gem'
  | 'swap'
  | 'hammer'
  | 'banknote'
  | 'trending'
  | 'scale'
  | 'wand'

export interface RuleItem {
  title: string
  description: string
  icon?: RuleIconKey
}

export const roundOneRules: RuleItem[] = [
  {
    title: '5000 AlumniCoins',
    description: 'Every team begins with 5000 AlumniCoins.',
    icon: 'coins',
  },
  {
    title: 'One Problem at a Time',
    description:
      'Only one Problem Statement is revealed at a time. Upcoming statements remain hidden until the next auction cycle.',
    icon: 'eye',
  },
  {
    title: 'Live Auction + Timer',
    description:
      'Eligible teams bid live using AlumniCoins. Each auction runs on a countdown timer of roughly 30\u201390 seconds.',
    icon: 'gavel',
  },
  {
    title: 'Top 5 Leaderboard',
    description: 'The live screen shows the Top 5 leading teams while bidding is active.',
    icon: 'monitor',
  },
  {
    title: 'Top 5 Win the Same Problem',
    description:
      'When the timer ends, the Top 5 highest-bidding teams win the SAME Problem Statement.',
    icon: 'trophy',
  },
  {
    title: 'Repeat Until Every Team Is Seated',
    description:
      'Winning teams exit that cycle. The next Problem Statement is revealed until every team is seated; in the 30-team example, 5 teams ultimately work on each statement.',
    icon: 'repeat',
  },
]

export const wildcardRules: RuleItem[] = [
  {
    title: 'After Part 1',
    description:
      'After Part 1 is completed and EVERY team has a Problem Statement, the event moves to the Wild Card Auction.',
    icon: 'clock',
  },
  {
    title: '3 Wild Cards',
    description: 'Three Wild Cards are put up for auction.',
    icon: 'wand',
  },
  {
    title: 'Use Remaining AlumniCoins',
    description: 'Teams participate in the Wild Card Auction using their remaining AlumniCoins.',
    icon: 'coins',
  },
  {
    title: 'Top 3 Highest Bidders Win',
    description: 'The Top 3 highest-bidding teams win the 3 available Wild Cards.',
    icon: 'award',
  },
  {
    title: '3 Bonus Problem Statements',
    description: 'There are 3 Bonus Problem Statements available specifically for the Wild Card winners.',
    icon: 'gem',
  },
  {
    title: 'Must Choose One',
    description: 'Each Wild Card winner MUST choose ONE of the 3 Bonus Problem Statements.',
    icon: 'hand',
  },
  {
    title: 'Switch Your Problem',
    description:
      'Winning a Wild Card lets the team switch from its originally assigned Problem Statement to a Bonus Problem Statement.',
    icon: 'swap',
  },
  {
    title: 'Proceed to Round 2',
    description: 'After choosing the new Bonus Problem Statement, the team proceeds to the 4-hour Build Round.',
    icon: 'hammer',
  },
]

export const roundTwoConfig = {
  duration: '4 Hours',
  teamSize: '2\u20134 Members',
  intro: 'Teams work on their final Problem Statement and build a functional prototype or solution.',
} as const

export const roundTwoSteps: RuleItem[] = [
  {
    title: 'Final PS Confirmed',
    description: 'Teams lock in their final Problem Statement before the Build Round begins.',
    icon: 'file',
  },
  {
    title: '4-Hour Build',
    description: 'Teams receive 4 hours to build their prototype / solution using creativity, strategy and teamwork.',
    icon: 'hammer',
  },
  {
    title: 'Prototype Submission',
    description: 'Teams must submit their prototype / solution before the deadline.',
    icon: 'clock',
  },
  {
    title: 'Alumni Evaluation',
    description: "Alumni experts evaluate each team's solution based on the finalized criteria.",
    icon: 'award',
  },
  {
    title: 'Scoring Begins',
    description: 'Evaluation scores are calculated and combined with the Royalty Bonus.',
    icon: 'scale',
  },
  {
    title: 'Final Score Ready',
    description: "Evaluation Score + Royalty Bonus produces the team's Final Score.",
    icon: 'trophy',
  },
]

export const evaluationCriteria: RuleItem[] = [
  { title: 'Innovation', description: 'Uniqueness and creativity of the idea.', icon: 'wand' },
  { title: 'Functionality', description: 'How effectively the solution works.', icon: 'hammer' },
  { title: 'Impact', description: 'Potential real-world relevance and value.', icon: 'trending' },
  { title: 'Technology', description: 'Use of technology and implementation.', icon: 'monitor' },
  { title: 'Presentation', description: 'Clarity, demo and team presentation.', icon: 'award' },
  {
    title: 'Teamwork & Execution',
    description: 'How effectively the team collaborated and executed the solution.',
    icon: 'layers',
  },
]

export const eventFlowSteps: RuleItem[] = [
  { title: 'Registration', description: 'Teams register for the event.', icon: 'file' },
  { title: '5000 AlumniCoins', description: 'Every team receives 5000 AlumniCoins.', icon: 'coins' },
  {
    title: 'Round 1 Part 1 \u2014 Problem Statement Auction',
    description: 'Top 5 teams win the same Problem Statement. Repeat until all teams have a PS.',
    icon: 'gavel',
  },
  {
    title: 'Round 1 Part 2 \u2014 Wild Card Auction',
    description: 'The Top 3 bidders win 3 Wild Cards and choose from 3 Bonus Problem Statements.',
    icon: 'wand',
  },
  { title: 'Round 2 \u2014 4-Hour Build', description: 'Teams build their solution / prototype.', icon: 'hammer' },
  { title: 'Alumni Evaluation', description: 'Alumni experts evaluate solutions based on the finalized criteria.', icon: 'award' },
  { title: 'Royalty Bonus', description: '1 point for every 100 AlumniCoins remaining.', icon: 'trending' },
  { title: 'Final Score', description: 'Evaluation Score + Royalty Bonus.', icon: 'scale' },
  { title: 'Results & Winners', description: 'Highest Final Score wins the event.', icon: 'trophy' },
]

export const royaltyHowItWorks: RuleItem[] = [
  {
    title: 'Save Your Coins',
    description: 'Unused AlumniCoins remain with the team after the auctions.',
    icon: 'banknote',
  },
  {
    title: '1 Point per 100 Coins',
    description: 'Earn 1 Royalty Point for every 100 AlumniCoins remaining.',
    icon: 'trending',
  },
  {
    title: 'Maximum 10 Points',
    description: 'The Royalty Bonus is capped at 10 points.',
    icon: 'trophy',
  },
  {
    title: 'Spend vs Save',
    description: 'Spending more improves auction chances, while saving more increases the possible Royalty Bonus.',
    icon: 'scale',
  },
  {
    title: 'Final Score',
    description: 'Evaluation Score + Royalty Bonus = Final Score.',
    icon: 'award',
  },
  {
    title: 'Highest Score Wins',
    description: 'The team with the highest Final Score wins the event.',
    icon: 'trophy',
  },
]

export const royaltyScoreExample = {
  evaluationScore: '78.0',
  remainingCoins: '580 AC',
  royaltyBonus: '5.8',
  finalScore: '83.8',
} as const

export const auctionRoundCard = {
  eyebrow: 'Bid to Build',
  badge: 'Round 1',
  title: 'Problem Statement Auction',
  chips: ['Top 5 Win', '5000 AlumniCoins'],
  footer: 'Bid to Build',
}

export const wildcardCardText = {
  eyebrow: 'Round 1 \u2014 Part 2',
  title: 'Wild Card Auction',
  lines: ['Top Bidders Win', 'Bonus Problem Statements', 'Switch Your Challenge'],
  chip: 'Limited Wild Cards',
  footer: 'Bid to Build',
}

export interface FaqItem {
  question: string
  answer: string
}

export const faqItems: FaqItem[] = [
  {
    question: 'What do we win?',
    answer:
      'Winning teams take the spotlight, bragging rights, and the final prize pot. Judging is based on the built solution, not the size of your bid.',
  },
  {
    question: 'What happens if we lose a bid?',
    answer:
      'Nothing. Losing bids cost no coins \u2014 your virtual balance stays intact and you are free to bid on another challenge.',
  },
  {
    question: 'How is the winner decided?',
    answer:
      'After the build, judges score each delivered solution on impact, craft, and execution. The top-scoring solution wins.',
  },
  {
    question: 'Do we need to be present all day?',
    answer:
      'Key moments \u2014 challenge reveal, bidding rounds, coding window, and results \u2014 are on the timeline. Plan to be present for each phase.',
  },
  {
    question: 'Who can participate?',
    answer:
      'XIE alumni. Form a team of 2\u20134 members and register through the event page before the deadline.',
  },
]
