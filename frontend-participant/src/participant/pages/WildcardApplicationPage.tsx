import { useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import AdvanceButton from '../components/AdvanceButton'
import WaitingState from '../components/WaitingState'
import { Button, Card, PageHeading } from '../components/ui'

export default function WildcardApplicationPage() {
  const { dashboard, service, refresh } = useParticipant()
  const [working, setWorking] = useState(false)
  if (!dashboard) return null
  const applied = Boolean(dashboard.wildcardApplication)

  const apply = async () => {
    setWorking(true)
    try {
      await service.applyForWildcard()
      await refresh()
    } finally {
      setWorking(false)
    }
  }

  return (
    <div className="stack">
      <PageHeading eyebrow="Wildcard round" title={applied ? 'Application confirmed' : 'Need another shot?'}>
        {applied ? 'You are registered for the wildcard round.' : 'Apply for the wildcard auction to compete for a replacement problem statement.'}
      </PageHeading>

      {applied ? (
        <Card className="center-card">
          <span className="confirmation-mark">✓</span>
          <h2>You&apos;re on the wildcard list</h2>
          <WaitingState text="Waiting for the organizer to reveal the wildcard problems…" />
        </Card>
      ) : (
        <Card className="center-card">
          <Button variant="gold" onClick={() => void apply()} disabled={working}>{working ? 'Applying…' : 'Apply for wildcard'}</Button>
        </Card>
      )}

      {applied && <AdvanceButton label="Waiting for wildcard problems" />}
    </div>
  )
}
