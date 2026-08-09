import type { ReactNode } from 'react'

export default function WaitingState({ label = 'Waiting', text }: { label?: string; text?: ReactNode }) {
  return (
    <div role="status" aria-label={label} className="waiting-state">
      <span className="waiting-indicator"><span /><span /><span /></span>
      {text && <p className="waiting-state__text">{text}</p>}
    </div>
  )
}