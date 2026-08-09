export const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function smoothScrollToTop() {
  if (prefersReducedMotion()) {
    window.scrollTo({ top: 0 })
  } else {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}