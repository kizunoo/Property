"use client"

import { useEffect, useRef, useState } from "react"
import { ChevronDown, LogOut, UserCircle2 } from "lucide-react"

export function AgentMenu() {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [])

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-3 border-2 border-black bg-white px-3 py-2 text-left shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] sm:px-4"
      >
        <div className="flex h-8 w-8 items-center justify-center border-2 border-black bg-primary text-xs font-black">
          RD
        </div>
        <div className="text-xs font-black uppercase tracking-wider sm:text-sm">R. Delgado — Senior Agent</div>
        <ChevronDown
          className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          strokeWidth={3}
        />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-full z-20 mt-3 w-56 border-4 border-black bg-white shadow-[6px_6px_0px_0px_rgba(0,0,0,1)]"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2.5 border-b-2 border-black px-4 py-3 text-left text-xs font-black uppercase tracking-wider transition-colors hover:bg-black hover:text-white sm:text-sm"
          >
            <UserCircle2 className="h-4 w-4" strokeWidth={2.5} />
            Profile
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2.5 px-4 py-3 text-left text-xs font-black uppercase tracking-wider transition-colors hover:bg-black hover:text-white sm:text-sm"
          >
            <LogOut className="h-4 w-4" strokeWidth={2.5} />
            Log Out
          </button>
        </div>
      ) : null}
    </div>
  )
}
