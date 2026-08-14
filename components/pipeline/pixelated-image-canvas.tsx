"use client"

import { useEffect, useRef, useState } from "react"
import { Building2 } from "lucide-react"

interface PixelatedImageCanvasProps {
  src?: string
  alt: string
  className?: string
  containerHeightClass?: string
  showCreditBadge?: boolean
  borderBottomOnly?: boolean
  disablePixelation?: boolean
}

export function PixelatedImageCanvas({
  src,
  alt,
  className = "",
  containerHeightClass = "h-48 sm:h-52",
  showCreditBadge = false,
  borderBottomOnly = true,
  disablePixelation = false,
}: PixelatedImageCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [error, setError] = useState(false)
  const imgRef = useRef<HTMLImageElement | null>(null)

  // progressRef: 0 = unhovered, 1 = hovered
  const progressRef = useRef<number>(disablePixelation ? 1 : 0)
  const animFrameRef = useRef<number | null>(null)

  /**
   * Renders a frame for interpolation value t in [0, 1].
   * - t = 0 (unhovered): Grayscale = 1.0, Pixelation scale = minScale (blocky, pixelated, desaturated)
   * - t = 1 (hovered): Grayscale = 0.0, Pixelation scale = 1.0 (depixelated, sharp, full color)
   * - 0 < t < 1: Smooth transition depixelating and revealing full color.
   */
  const renderFrame = (t: number) => {
    const canvas = canvasRef.current
    const container = containerRef.current
    const img = imgRef.current
    if (!canvas || !container || !img) return

    const rect = container.getBoundingClientRect()
    const width = Math.floor(rect.width) || 400
    const height = Math.floor(rect.height) || 250

    if (width === 0 || height === 0) return

    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width
      canvas.height = height
    }

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const clampedT = disablePixelation ? 1 : Math.max(0, Math.min(1, t))

    // Grayscale ramp: 1.0 at rest (t=0) down to 0.0 on hover (t=1)
    const grayscale = disablePixelation ? 0 : 1.0 - clampedT

    // Scale factor: minScale (pixelated) at rest (t=0) up to 1.0 (sharp) on hover (t=1)
    const minScale = 0.08
    const scale = disablePixelation ? 1.0 : minScale + (1.0 - minScale) * clampedT

    ctx.save()
    ctx.clearRect(0, 0, width, height)

    // Calculate aspect-fill object-cover crop coordinates
    const imgAspect = img.width / img.height
    const targetAspect = width / height
    let sx = 0
    let sy = 0
    let sw = img.width
    let sh = img.height

    if (imgAspect > targetAspect) {
      sw = Math.floor(img.height * targetAspect)
      sx = Math.floor((img.width - sw) / 2)
    } else {
      sh = Math.floor(img.width / targetAspect)
      sy = Math.floor((img.height - sh) / 2)
    }

    // Apply contrast/grayscale filter
    ctx.filter = `grayscale(${grayscale.toFixed(2)}) contrast(1.25)`

    if (scale < 0.98) {
      // Pixelated phase (at rest or mid-transition): draw to small offscreen canvas & stretch back with smoothing OFF
      const smallWidth = Math.max(2, Math.floor(width * scale))
      const smallHeight = Math.max(2, Math.floor(height * scale))

      const offscreen = document.createElement("canvas")
      offscreen.width = smallWidth
      offscreen.height = smallHeight
      const offCtx = offscreen.getContext("2d")

      if (offCtx) {
        // Step 1: Crop image to offscreen canvas
        offCtx.drawImage(img, sx, sy, sw, sh, 0, 0, smallWidth, smallHeight)

        // Step 2: Scale offscreen canvas back to full size with blocky pixelation
        ctx.imageSmoothingEnabled = false
        ctx.drawImage(offscreen, 0, 0, smallWidth, smallHeight, 0, 0, width, height)
      } else {
        ctx.imageSmoothingEnabled = true
        ctx.drawImage(img, sx, sy, sw, sh, 0, 0, width, height)
      }
    } else {
      // Fully depixelated state (hovered): 100% full resolution sharp draw
      ctx.imageSmoothingEnabled = true
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, width, height)
    }

    ctx.restore()
  }

  useEffect(() => {
    if (!src) {
      setError(true)
      return
    }

    setError(false)

    // Robust image loader with CORS anonymous retry
    let cancelled = false
    const loadImage = (url: string, anonymous: boolean) => {
      const img = new Image()
      if (anonymous) {
        img.crossOrigin = "anonymous"
      }
      img.src = url

      img.onload = () => {
        if (cancelled) return
        imgRef.current = img
        setError(false)
        progressRef.current = 0
        renderFrame(0)
      }

      img.onerror = () => {
        if (cancelled) return
        if (anonymous) {
          // Retry with cache buster query if anonymous fails
          const retryUrl = url + (url.includes("?") ? "&" : "?") + "cors_retry=" + Date.now()
          loadImage(retryUrl, true)
        } else {
          setError(true)
        }
      }
    }

    loadImage(src, true)

    return () => {
      cancelled = true
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src])

  const animateTo = (target: number) => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)

    const startTime = performance.now()
    const startVal = progressRef.current
    // Adjust duration proportionally if reversing mid-transition
    const distance = Math.abs(target - startVal)
    const baseDuration = 800 // ms smooth depixelation animation
    const duration = Math.max(250, baseDuration * distance)

    const step = (now: number) => {
      const elapsed = now - startTime
      const p = Math.min(1, elapsed / duration)
      // Ease in-out quadratic interpolation
      const easeP = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2
      const current = startVal + (target - startVal) * easeP

      progressRef.current = current
      renderFrame(current)

      if (p < 1) {
        animFrameRef.current = requestAnimationFrame(step)
      } else {
        progressRef.current = target
        renderFrame(target) // Force exact target state (0.0 or 1.0)
      }
    }

    animFrameRef.current = requestAnimationFrame(step)
  }

  const handleMouseEnter = () => animateTo(1)
  const handleMouseLeave = () => animateTo(0)

  // Re-render frame on container resize
  useEffect(() => {
    const handleResize = () => renderFrame(progressRef.current)
    window.addEventListener("resize", handleResize)
    return () => window.removeEventListener("resize", handleResize)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (error || !src) {
    return (
      <div
        className={`stripes-diagonal relative flex ${containerHeightClass} w-full items-center justify-center bg-white rounded-none ${
          borderBottomOnly ? "border-b-4 border-black" : "border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]"
        }`}
      >
        <div className="relative z-10 flex h-16 w-16 items-center justify-center border-4 border-black bg-primary shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] rounded-none">
          <Building2 className="h-8 w-8 text-black" strokeWidth={2.5} />
        </div>
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className={`group relative w-full overflow-hidden bg-black rounded-none ${containerHeightClass} ${
        borderBottomOnly ? "border-b-4 border-black" : "border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]"
      } ${className}`}
    >
      <canvas ref={canvasRef} className="block h-full w-full cursor-pointer rounded-none" aria-label={alt} />
      {showCreditBadge && (
        <span className="absolute bottom-2.5 right-2.5 rounded-none border-2 border-black bg-black px-2.5 py-1 text-[9px] font-black uppercase tracking-wider text-primary shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
          Photos via Pexels
        </span>
      )}
    </div>
  )
}
