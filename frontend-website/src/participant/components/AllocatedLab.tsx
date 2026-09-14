import type { ParticipantDashboard } from '../types'

export default function AllocatedLab({ dashboard }: { dashboard: ParticipantDashboard }) {
  if (!dashboard.labAllocationReady) return null
  const missing = dashboard.labAllocationStatus === 'UNAVAILABLE'
  return <div className="allocated-lab" role="status"><span>{dashboard.lab ? 'Allocated Lab' : 'Lab allocation'}</span><strong>{dashboard.lab?.name || (missing ? 'Lab assignment unavailable' : 'Allocation pending')}</strong></div>
}
