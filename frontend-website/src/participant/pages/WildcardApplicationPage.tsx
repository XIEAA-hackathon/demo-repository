import { useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import { getParticipantPermissions } from '../permissions'
import AdvanceButton from '../components/AdvanceButton'
import WaitingState from '../components/WaitingState'
import Countdown from '../components/Countdown'
import { Button, Card, PageHeading, Stat } from '../components/ui'

export default function WildcardApplicationPage() {
  const { dashboard, service, refresh } = useParticipant()
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  if (!dashboard) return null
  const applied = Boolean(dashboard.wildcardApplication)
  const permissions = getParticipantPermissions(dashboard)
  const declined = dashboard.wildcard?.status === 'declined'
  const applicationsActive = dashboard.eventState === 'WILDCARD_APPLICATION' && dashboard.wildcardApplicationsOpen

  const apply = async () => {
    setWorking(true)
    setError('')
    try {
      await service.applyForWildcard()
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Application failed.')
    } finally {
      setWorking(false)
    }
  }
  const decline = async () => {
    setWorking(true)
    setError('')
    try { await service.declineWildcard(); await refresh() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Response failed.') }
    finally { setWorking(false) }
  }

  if (!dashboard.wildcardEligible) return (
    <div className="stack"><PageHeading eyebrow="Round 1 complete" title="Your team already has a problem" />
      <Card className="center-card"><h2>Wildcard is not required</h2><p>Your Round 1 assignment is secured. Please wait for the event to continue.</p><WaitingState text="Waiting for Round 1 to close…" /></Card>
    </div>
  )

  return (
    <div className="stack">
      <PageHeading eyebrow="Wildcard · Applications" title={applied ? 'Application confirmed' : declined ? 'Response recorded' : 'Apply for a wildcard slot'}>
        {applied ? 'Your team is registered for the single wildcard slot auction.' : declined ? 'Your team declined the wildcard round.' : 'Approved teams can enter the wildcard slot auction. Your existing balance carries forward.'}
      </PageHeading>

      <div className="stats-grid bid-status-grid"><Stat label="Application time left" value={<Countdown timing={dashboard.timing} />} /><Stat label="Current balance" value={`${dashboard.wallet.balance} coins`} /></div>

      {applied ? (
        <Card className="center-card">
          <span className="confirmation-mark">✓</span>
          <h2>You&apos;re on the wildcard list</h2>
          <WaitingState text="Waiting for slot bidding to begin…" />
        </Card>
      ) : declined ? (
        <Card className="center-card"><h2>Wildcard declined</h2><WaitingState text="Waiting for the event to continue…" /></Card>
      ) : (
        <Card className="center-card">
          <div className="button-row"><Button variant="gold" onClick={() => void apply()} disabled={!permissions.isLeader || working || !applicationsActive}>{working ? 'Applying…' : 'Apply for wildcard'}</Button><Button variant="secondary" onClick={() => void decline()} disabled={!permissions.isLeader || working || !applicationsActive}>Do not apply</Button></div>
          {!dashboard.wildcardApplicationsOpen && <p className="notice">Wildcard applications are closed.</p>}
          {!permissions.isLeader && <p className="notice">Only your team leader can apply. You can continue watching the wildcard status here.</p>}
          {error && <p className="error" role="alert">{error}</p>}
        </Card>
      )}

      {applied && <AdvanceButton label="Waiting for slot bidding" />}
    </div>
  )
}
