"use client"

import { useEffect, useRef, useState } from "react"

type CursorState = "default" | "hover" | "text" | "disabled" | "grab"

// Sharp-edged arrow pointer path, hotspot at (0,0)
const ARROW_PATH = "M0 0 L0 20 L5 15.5 L8.5 22.5 L11.5 21 L8 14 L14 14 Z"

export function CustomCursor() {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<CursorState>("default")
  const [isClicking, setIsClicking] = useState(false)
  const [isVisible, setIsVisible] = useState(false)
  const [isTouch, setIsTouch] = useState(false)

  useEffect(() => {
    const hasTouch = matchMedia("(pointer: coarse)").matches
    setIsTouch(hasTouch)
    if (hasTouch) return

    const pos = { x: 0, y: 0 }
    let raf = 0

    const move = (e: MouseEvent) => {
      pos.x = e.clientX
      pos.y = e.clientY
      if (!isVisible) setIsVisible(true)
      if (!raf) {
        raf = requestAnimationFrame(() => {
          if (wrapRef.current) {
            wrapRef.current.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0)`
          }
          raf = 0
        })
      }
    }

    const down = () => setIsClicking(true)
    const up = () => setIsClicking(false)
    const leave = () => setIsVisible(false)

    const over = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target || !target.closest) return

      if (target.closest("button:disabled, [aria-disabled='true'], [data-cursor-disabled]"))
        return setState("disabled")

      if (
        target.closest(
          "input:not([type='checkbox']):not([type='radio']):not([type='submit']):not([type='button']), textarea, [contenteditable='true']",
        )
      )
        return setState("text")

      if (target.closest("[draggable='true'], [data-cursor-grab], .resize-handle"))
        return setState("grab")

      if (target.closest("button, a, [role='button'], select, [data-cursor-hover]"))
        return setState("hover")

      setState("default")
    }

    window.addEventListener("mousemove", move)
    window.addEventListener("mousemove", over)
    window.addEventListener("mousedown", down)
    window.addEventListener("mouseup", up)
    document.addEventListener("mouseleave", leave)

    return () => {
      window.removeEventListener("mousemove", move)
      window.removeEventListener("mousemove", over)
      window.removeEventListener("mousedown", down)
      window.removeEventListener("mouseup", up)
      document.removeEventListener("mouseleave", leave)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [isVisible])

  if (isTouch) return null

  const scale = isClicking ? 0.88 : 1
  const isArrow = state === "default" || state === "hover"
  const fill = state === "hover" ? "var(--primary, #FFD400)" : "#ffffff"

  return (
    <div
      ref={wrapRef}
      aria-hidden="true"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        pointerEvents: "none",
        zIndex: 9999,
        opacity: isVisible ? 1 : 0,
        transition: "opacity 150ms ease",
      }}
    >
      {isArrow && (
        <svg
          width="28"
          height="30"
          viewBox="0 0 15 24"
          style={{
            position: "absolute",
            transform: `scale(${scale})`,
            transformOrigin: "0 0",
            transition: "transform 80ms ease",
            overflow: "visible",
          }}
        >
          {/* Hard offset shadow */}
          <path d={ARROW_PATH} fill="#000000" transform="translate(3,3)" />
          {/* Foreground arrow */}
          <path
            d={ARROW_PATH}
            fill={fill}
            stroke="#000000"
            strokeWidth="1.5"
            strokeLinejoin="miter"
          />
        </svg>
      )}

      {state === "text" && (
        <div
          style={{
            position: "absolute",
            width: 3,
            height: 22,
            background: "#000000",
            transform: `translate(-1.5px, -11px) scale(${scale})`,
            transition: "transform 80ms ease",
          }}
        />
      )}

      {state === "disabled" && (
        <svg
          width="28"
          height="30"
          viewBox="0 0 15 24"
          style={{
            position: "absolute",
            transform: `scale(${scale})`,
            transformOrigin: "0 0",
          }}
        >
          <path
            d={ARROW_PATH}
            fill="#cccccc"
            stroke="#999999"
            strokeWidth="1.5"
            strokeLinejoin="miter"
          />
        </svg>
      )}

      {state === "grab" && (
        <div
          style={{
            position: "absolute",
            width: 20,
            height: 20,
            border: "2px dashed #000000",
            transform: `translate(-10px, -10px) scale(${scale})`,
            transition: "transform 80ms ease",
          }}
        />
      )}
    </div>
  )
}
