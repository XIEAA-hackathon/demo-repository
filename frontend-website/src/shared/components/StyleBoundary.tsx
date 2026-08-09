import { useCallback, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

interface StyleBoundaryProps {
  children: ReactNode
  rootClassName: string
  styles: string
}

export default function StyleBoundary({ children, rootClassName, styles }: StyleBoundaryProps) {
  const [shadowRoot, setShadowRoot] = useState<ShadowRoot | null>(null)
  const setHost = useCallback((host: HTMLDivElement | null) => {
    setShadowRoot(host ? (host.shadowRoot ?? host.attachShadow({ mode: 'open' })) : null)
  }, [])

  return (
    <div ref={setHost} style={{ display: 'block', minHeight: '100vh', width: '100%' }}>
      {shadowRoot ? createPortal(
        <>
          <style>{styles}</style>
          <div className={rootClassName}>{children}</div>
        </>,
        shadowRoot,
      ) : null}
    </div>
  )
}
