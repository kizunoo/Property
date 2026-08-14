import type { Metadata, Viewport } from 'next'
import { Space_Grotesk, Space_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { CustomCursor } from '@/components/cursor/custom-cursor'
import { ShapeGrid } from '@/components/background/shape-grid'
import './globals.css'

const _spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-space-grotesk",
})
const _spaceMono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-space-mono",
})

export const metadata: Metadata = {
  title: 'PIPELINE // Client Priority Console',
  description:
    'Internal B2B console for real estate agents to prioritize clients by Expected Value — buy probability x target property value.',
  generator: 'v0.app',
}

export const viewport: Viewport = {
  themeColor: '#ffffff',
  colorScheme: 'light',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${_spaceGrotesk.variable} ${_spaceMono.variable} bg-background`}>
      <body className="font-sans antialiased">
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: -1,
            pointerEvents: "none",
            opacity: 1,
          }}
        >
          <ShapeGrid
            direction="diagonal"
            speed={0.3}
            squareSize={40}
            shape="square"
            borderColor="#000000"
            hoverFillColor="#FFD400"
            hoverTrailAmount={0}
          />
        </div>
        <div className="crt-overlay">
          <div className="crt-scanlines" />
          <div className="crt-vignette" />
          <div className="crt-flicker" />
        </div>
        <CustomCursor />
        {children}
        <Analytics />
      </body>
    </html>
  )
}
