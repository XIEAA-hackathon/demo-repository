import { useEffect, useRef } from 'react'

const VIDEO_URL = 'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260328_065045_c44942da-53c6-4804-b734-f9e07fc22e08.mp4'

export default function RulesMotionBackground() {
  const rootRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const root = rootRef.current
    const video = videoRef.current
    if (!root || !video) return

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    let animationFrame = 0
    let replayTimer = 0
    let opacity = 0
    let isVisible = false
    let isReady = video.readyState >= HTMLMediaElement.HAVE_METADATA
    let fadingOut = false

    const setOpacity = (value: number) => {
      opacity = value
      video.style.opacity = String(value)
    }

    const fadeTo = (target: number, duration: number) => {
      cancelAnimationFrame(animationFrame)
      const startOpacity = opacity
      const startedAt = performance.now()

      const tick = (now: number) => {
        const progress = Math.min((now - startedAt) / duration, 1)
        setOpacity(startOpacity + (target - startOpacity) * progress)
        if (progress < 1) animationFrame = requestAnimationFrame(tick)
      }

      animationFrame = requestAnimationFrame(tick)
    }

    const playWhenVisible = () => {
      if (!isVisible || document.hidden || !isReady) return
      window.clearTimeout(replayTimer)

      if (reducedMotion.matches) {
        cancelAnimationFrame(animationFrame)
        video.pause()
        setOpacity(1)
        return
      }

      fadingOut = false
      fadeTo(1, 500)
      void video.play().catch(() => undefined)
    }

    const handleReady = () => {
      isReady = true
      playWhenVisible()
    }

    const handleTimeUpdate = () => {
      if (reducedMotion.matches || fadingOut || !video.duration) return
      if (video.duration - video.currentTime <= 0.5) {
        fadingOut = true
        fadeTo(0, 500)
      }
    }

    const handleEnded = () => {
      setOpacity(0)
      replayTimer = window.setTimeout(() => {
        video.currentTime = 0
        playWhenVisible()
      }, 100)
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        cancelAnimationFrame(animationFrame)
        video.pause()
      } else {
        playWhenVisible()
      }
    }

    const handleMotionPreference = () => {
      if (reducedMotion.matches) {
        cancelAnimationFrame(animationFrame)
        video.pause()
        setOpacity(1)
      } else {
        playWhenVisible()
      }
    }

    const observer = new IntersectionObserver(([entry]) => {
      isVisible = entry.isIntersecting
      if (isVisible) {
        playWhenVisible()
      } else {
        cancelAnimationFrame(animationFrame)
        video.pause()
        setOpacity(0)
      }
    }, { rootMargin: '160px 0px' })

    observer.observe(root)
    video.addEventListener('loadedmetadata', handleReady)
    video.addEventListener('canplay', handleReady)
    video.addEventListener('timeupdate', handleTimeUpdate)
    video.addEventListener('ended', handleEnded)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    reducedMotion.addEventListener('change', handleMotionPreference)

    return () => {
      observer.disconnect()
      cancelAnimationFrame(animationFrame)
      window.clearTimeout(replayTimer)
      video.pause()
      video.removeEventListener('loadedmetadata', handleReady)
      video.removeEventListener('canplay', handleReady)
      video.removeEventListener('timeupdate', handleTimeUpdate)
      video.removeEventListener('ended', handleEnded)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      reducedMotion.removeEventListener('change', handleMotionPreference)
    }
  }, [])

  return <div ref={rootRef} className="rulebook-motion" aria-hidden="true">
    <div className="rulebook-motion-viewport">
      <video ref={videoRef} className="rulebook-motion-video" muted playsInline preload="metadata">
        <source src={VIDEO_URL} type="video/mp4" />
      </video>
      <div className="rulebook-motion-scrim" />
    </div>
  </div>
}
