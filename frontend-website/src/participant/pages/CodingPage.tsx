import { useEffect, useState, type FormEvent } from 'react'
import { useParticipant } from '../ParticipantContext'
import { getParticipantPermissions } from '../permissions'
import Countdown from '../components/Countdown'
import { Button, Card, CoinBalance, PageHeading, Stat } from '../components/ui'
import AllocatedLab from '../components/AllocatedLab'

export default function CodingPage() {
  const { dashboard, service, refresh } = useParticipant()
  const [url, setUrl] = useState('')
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [working, setWorking] = useState(false)
  useEffect(() => { setUrl(dashboard?.submission?.repositoryUrl ?? '') }, [dashboard?.submission?.repositoryUrl])
  if (!dashboard) return null
  const permissions = getParticipantPermissions(dashboard)
  const submitted = Boolean(dashboard.submission)
  const finalProblem = dashboard.finalProblem ?? dashboard.currentProblem
  const submissionsActive = dashboard.eventState === 'CODING' && dashboard.submissionsOpen

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setWorking(true); setMessage(null)
    try {
      await service.submitGitHubRepository(url)
      await refresh()
      setMessage({ type: 'success', text: submitted ? 'Repository URL updated.' : 'Repository submitted for judging.' })
    } catch (cause) {
      setMessage({ type: 'error', text: cause instanceof Error ? cause.message : 'Submission failed.' })
    } finally { setWorking(false) }
  }

  return (
    <div className="stack coding-page">
      <PageHeading eyebrow="Coding round" title="Build and submit your solution">Your coding timer and repository submission stay together here.</PageHeading>
      <Card className="challenge-card submission-problem">
        <p className="eyebrow">Final problem</p>
        {finalProblem && <small>Problem #{String(finalProblem.number).padStart(2, '0')}</small>}
        <h2>{finalProblem?.title ?? 'Problem assignment pending'}</h2>
        <p>{finalProblem?.description}</p>
        <AllocatedLab dashboard={dashboard} />
      </Card>
      <div className="stats-grid">
        <Stat label="Time remaining" value={<Countdown timing={dashboard.timing} showHours />} />
        <Stat label="Team coins" value={<CoinBalance value={dashboard.wallet.balance} />} />
        <Stat label="Submission status" value={submitted ? 'Submitted' : 'Not submitted'} />
      </div>
      <Card className="repository-submission">
        <p className="eyebrow">Repository submission</p>
        <h2>{submitted ? 'Repository on record' : 'Submit your GitHub repository'}</h2>
        {dashboard.submission && <div className="repository-record"><a className="text-link" href={dashboard.submission.repositoryUrl} target="_blank" rel="noreferrer">{dashboard.submission.repositoryUrl}</a><dl><div><dt>Submitted</dt><dd>{new Date(dashboard.submission.submittedAt).toLocaleString()}</dd></div><div><dt>Updated</dt><dd>{dashboard.submission.updatedAt ? new Date(dashboard.submission.updatedAt).toLocaleString() : 'Not updated'}</dd></div><div><dt>Submitted by</dt><dd>{dashboard.submission.submittedByName ?? 'Team leader'}</dd></div></dl></div>}
        <form className="form" onSubmit={submit}>
          <label className={!permissions.canSubmitRepository ? 'is-locked' : ''}><span>GitHub repository URL</span><input type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://github.com/team/project" disabled={!permissions.canSubmitRepository} required pattern="https://github.com/.*" title="Enter a valid GitHub repository URL" /></label>
          <Button type="submit" disabled={!permissions.canSubmitRepository || working || !finalProblem}>{working ? 'Saving…' : submitted ? 'Update repository' : 'Submit repository'}</Button>
          {!submissionsActive && <p className="notice">Repository submissions are closed. Any saved URL remains on record.</p>}
          {submissionsActive && !permissions.isLeader && <p className="notice">Only your team leader can submit or update the final repository.</p>}
          {message && <p className={message.type === 'success' ? 'success' : 'error'} role="status">{message.text}</p>}
        </form>
      </Card>
    </div>
  )
}
