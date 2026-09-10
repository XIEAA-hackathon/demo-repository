import { useParticipant } from '../ParticipantContext'
import ResultCard from '../components/ResultCard'
import WaitingState from '../components/WaitingState'
import { Card, PageHeading, Stat } from '../components/ui'
import RoundOneComplete from '../components/RoundOneComplete'

export default function RoundResultPage() {
  const { dashboard } = useParticipant()
  if (!dashboard) return null
  if (dashboard.round1Assigned) return <RoundOneComplete dashboard={dashboard} />
  const settlement = dashboard.roundOneSettlement
  const bid = settlement?.bidAmount ?? 0
  const secured = settlement?.won ?? false

  return (
    <div className="stack round-result">
      <PageHeading eyebrow="Round 1 completed" title={secured ? 'Problem secured' : 'Bidding complete'} />
      {secured ? (
        <div className="result-wrap">
          <ResultCard teamName={dashboard.team.name} problem={dashboard.currentProblem} winningBid={bid} balance={dashboard.wallet.balance} />
          <p className="success result-note">Final result received from the event server. The winning bid is reflected in your wallet.</p>
        </div>
      ) : (
        <Card className="center-card">
          <span className="confirmation-mark confirmation-mark--muted">×</span>
          <h2>Your team did not secure this problem.</h2>
          <div className="stats-grid"><Stat label="Coins deducted" value="0 coins" /><Stat label="Remaining balance" value={`${dashboard.wallet.balance} coins`} /></div>
          <WaitingState text="Waiting for the organizer to open the next stage…" />
        </Card>
      )}
    </div>
  )
}
