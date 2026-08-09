import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { prefersReducedMotion } from '../../utils/scroll'

export default function ScrollToHash() {
  const { hash, pathname } = useLocation()

  useEffect(() => {
    if (!hash) return

    const target = document.getElementById(hash.slice(1))
    if (!target) return

    if (prefersReducedMotion()) {
      target.scrollIntoView({ block: 'start' })
    } else {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [hash, pathname])

  return null
}