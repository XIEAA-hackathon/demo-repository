import { useEffect, useId, type ReactNode } from 'react'

export default function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const headingId = useId()

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby={headingId} onClick={(event) => event.stopPropagation()}>
        <header className="modal__head">
          <h2 id={headingId}>{title}</h2>
          <button type="button" className="modal__close" onClick={onClose} aria-label="Close dialog">✕</button>
        </header>
        <div className="modal__body">{children}</div>
      </div>
    </div>
  )
}