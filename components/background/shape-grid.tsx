"use client"

import React, { useEffect, useRef } from "react"
import "./shape-grid.css"

export interface ShapeGridProps {
  direction?: "diagonal" | "horizontal" | "vertical" | "up" | "down" | "left" | "right"
  speed?: number
  squareSize?: number
  shape?: "square" | "circle" | "triangle" | "hexagon"
  borderColor?: string
  hoverFillColor?: string
  hoverTrailAmount?: number
  className?: string
}

export function ShapeGrid({
  direction = "diagonal",
  speed = 0.3,
  squareSize = 40,
  shape = "square",
  borderColor = "#CCCCCC",
  hoverFillColor = "#FFD400",
  hoverTrailAmount = 0,
  className = "",
}: ShapeGridProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    let animationFrameId: number
    let gridOffset = { x: 0, y: 0 }

    const resizeCanvas = () => {
      if (!canvas) return
      const dpr = window.devicePixelRatio || 1
      canvas.width = canvas.offsetWidth * dpr
      canvas.height = canvas.offsetHeight * dpr
      console.log('canvas size:', canvas.width, canvas.height, canvas.offsetWidth, canvas.offsetHeight)
    }

    resizeCanvas()
    window.addEventListener("resize", resizeCanvas)

    const draw = () => {
      if (!canvas) return
      const dpr = window.devicePixelRatio || 1
      const width = canvas.offsetWidth || canvas.width / dpr
      const height = canvas.offsetHeight || canvas.height / dpr

      if (width === 0 || height === 0) {
        animationFrameId = requestAnimationFrame(draw)
        return
      }

      ctx.save()
      ctx.scale(dpr, dpr)
      ctx.clearRect(0, 0, width, height)

      // Move grid based on direction and speed
      const effSpeed = speed * 0.5
      switch (direction) {
        case "diagonal":
        case "right":
        case "down":
          gridOffset.x = (gridOffset.x + effSpeed) % squareSize
          gridOffset.y = (gridOffset.y + effSpeed) % squareSize
          break
        case "horizontal":
        case "left":
          gridOffset.x = (gridOffset.x + effSpeed) % squareSize
          break
        case "vertical":
        case "up":
          gridOffset.y = (gridOffset.y + effSpeed) % squareSize
          break
        default:
          gridOffset.x = (gridOffset.x + effSpeed) % squareSize
          gridOffset.y = (gridOffset.y + effSpeed) % squareSize
      }

      ctx.strokeStyle = borderColor
      ctx.lineWidth = 1

      const startX = -squareSize + (gridOffset.x % squareSize)
      const startY = -squareSize + (gridOffset.y % squareSize)

      ctx.beginPath()
      for (let x = startX; x < width + squareSize; x += squareSize) {
        ctx.moveTo(x, 0)
        ctx.lineTo(x, height)
      }
      for (let y = startY; y < height + squareSize; y += squareSize) {
        ctx.moveTo(0, y)
        ctx.lineTo(width, y)
      }
      ctx.stroke()

      if (shape !== "square") {
        for (let x = startX; x < width + squareSize; x += squareSize) {
          for (let y = startY; y < height + squareSize; y += squareSize) {
            ctx.beginPath()
            if (shape === "circle") {
              ctx.arc(x, y, 2, 0, Math.PI * 2)
              ctx.fillStyle = borderColor
              ctx.fill()
            }
          }
        }
      }

      ctx.restore()
      animationFrameId = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      window.removeEventListener("resize", resizeCanvas)
      cancelAnimationFrame(animationFrameId)
    }
  }, [direction, speed, squareSize, shape, borderColor, hoverFillColor, hoverTrailAmount])

  return <canvas ref={canvasRef} className={`shapegrid-canvas ${className}`} />
}

export default ShapeGrid
