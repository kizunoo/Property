import type { RefObject } from "react"

interface WrappedRetroProps {
  contentRef: RefObject<HTMLDivElement | null>
  onDownloadImage: () => void
  onShareOnX: () => void
}

export function WrappedRetro({ contentRef, onDownloadImage, onShareOnX }: WrappedRetroProps) {
  return (
    <div className="min-h-screen bg-white text-black flex justify-center px-4 sm:px-6 lg:px-8 py-6 sm:py-10 lg:py-10">
      <div ref={contentRef} className="w-full max-w-[1200px] flex flex-col gap-6">
        <header className="flex justify-between items-center py-4 sm:py-5 mb-4 sm:mb-5 border-b-2 border-black">
          <div className="flex items-center gap-2">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="black"
              strokeWidth="3"
              strokeLinecap="square"
              strokeLinejoin="miter"
              className="w-6 h-6"
            >
              <rect x="3" y="3" width="18" height="18" rx="0" ry="0"></rect>
              <path d="M9 3v18"></path>
              <path d="M15 9h-6"></path>
            </svg>
            <div className="font-[family-name:var(--font-space-grotesk)] font-black text-xl sm:text-2xl tracking-tight">
              1UI<span className="text-black">.dev</span>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3 bg-white border-2 border-black py-1 px-3 sm:px-4 text-sm font-bold shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
            <img
              src="/images/jessin.png"
              alt="User"
              className="w-7 h-7 sm:w-8 sm:h-8 object-cover border-2 border-black"
            />
            <span className="hidden sm:inline">Jess&apos;s 2025</span>
            <span className="sm:hidden">Jess</span>
            <svg viewBox="0 0 24 24" fill="black" className="w-4 h-4">
              <path d="M7 10l5 5 5-6z"></path>
            </svg>
          </div>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 auto-rows-auto gap-4 sm:gap-6">
          <div className="md:col-span-2 bg-white rounded-none p-6 sm:p-8 relative overflow-hidden flex flex-col justify-end min-h-[380px] border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
            <div className="absolute top-0 left-0 w-full h-full">
              <div
                className="w-full h-full"
                style={{
                  backgroundImage: `repeating-linear-gradient(
                  45deg,
                  transparent,
                  transparent 10px,
                  rgba(0,0,0,0.03) 10px,
                  rgba(0,0,0,0.03) 20px
                )`,
                }}
              ></div>
            </div>
            <div className="relative z-10">
              <div className="text-xl sm:text-2xl font-black mb-2 border-2 border-black inline-block px-3 py-1 bg-white">
                Your Year Wrapped
              </div>
              <div className="font-[family-name:var(--font-space-grotesk)] text-7xl sm:text-8xl lg:text-[120px] font-black leading-[0.8] tracking-tighter text-black -ml-1 sm:-ml-1.5">
                2025
              </div>
              <div className="mt-6 bg-white border-4 border-black p-4 sm:p-5 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                <p className="text-sm sm:text-base font-bold">
                  You&apos;re in the top 1% of UI creators this year. You didn&apos;t just design; you shipped.
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-none p-6 sm:p-8 flex flex-col justify-between min-h-[380px] border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
            <div>
              <div className="text-xs sm:text-sm uppercase tracking-wider font-black mb-2 border-b-2 border-black pb-1">
                Total Components Used
              </div>
              <div className="font-[family-name:var(--font-space-grotesk)] text-5xl sm:text-6xl font-black leading-none mb-0 text-black">
                1,492
              </div>
            </div>

            <div className="mt-8">
              <div className="text-xs sm:text-sm uppercase tracking-wider font-black mb-2 border-b-2 border-black pb-1">
                Lines of Code Copied
              </div>
              <div className="font-[family-name:var(--font-space-grotesk)] text-4xl sm:text-5xl font-black leading-none text-black mb-3">
                84.5k
              </div>
              <div className="inline-flex items-center gap-1 bg-black text-white px-3 py-1 text-xs font-black border-2 border-black">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="w-3 h-3">
                  <path d="M18 15l-6-6-6 6"></path>
                </svg>
                +240% vs 2024
              </div>
            </div>
          </div>

          <div className="bg-white text-black rounded-none p-6 sm:p-8 flex flex-col justify-between min-h-[320px] sm:min-h-[380px] border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
            <div className="flex justify-between items-start mb-6">
              <span className="bg-black text-white px-5 py-2.5 text-sm font-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                Design Persona
              </span>
              <svg viewBox="0 0 24 24" fill="black" className="w-6 h-6">
                <circle cx="5" cy="12" r="2"></circle>
                <circle cx="12" cy="12" r="2"></circle>
                <circle cx="19" cy="12" r="2"></circle>
              </svg>
            </div>

            <div className="text-center flex-1 flex flex-col justify-center">
              <div className="w-20 h-20 sm:w-24 sm:h-24 bg-black flex items-center justify-center mx-auto mb-6 border-4 border-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#fff"
                  strokeWidth="2"
                  strokeLinecap="square"
                  strokeLinejoin="miter"
                  className="w-10 h-10 sm:w-12 sm:h-12"
                >
                  <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                  <polyline points="2 17 12 22 22 17"></polyline>
                  <polyline points="2 12 12 17 22 12"></polyline>
                </svg>
              </div>
              <div className="text-sm font-black uppercase mb-2 tracking-wide border-2 border-black inline-block px-2 py-1 mx-auto">
                You are a
              </div>
              <div className="font-[family-name:var(--font-space-grotesk)] text-3xl sm:text-[36px] font-black leading-tight tracking-tight mb-6">
                System
                <br />
                Architect
              </div>
            </div>

            <div className="text-sm leading-relaxed font-bold border-t-4 border-black pt-5">
              Consistency is your currency. You love atomic design and reusable tokens.
            </div>
          </div>

          <div className="bg-white rounded-none p-6 sm:p-8 min-h-[320px] sm:min-h-[380px] border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
            <div className="flex justify-between items-center mb-6 border-b-4 border-black pb-4">
              <h3 className="font-[family-name:var(--font-space-grotesk)] text-xl sm:text-2xl font-black">
                Top Tech Stack
              </h3>
              <span className="text-xs sm:text-sm font-black">Based on exports</span>
            </div>

            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-4 p-3 bg-white rounded-none border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                <div className="w-10 h-10 bg-black flex items-center justify-center flex-shrink-0 border-2 border-black">
                  <span className="text-white font-black text-sm">R</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between mb-1">
                    <div className="font-black text-sm sm:text-base">React</div>
                    <div className="text-xs font-black">68%</div>
                  </div>
                  <div className="h-2 w-full bg-white border-2 border-black overflow-hidden">
                    <div className="h-full bg-black" style={{ width: "68%" }}></div>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-4 p-3 bg-white rounded-none border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                <div className="w-10 h-10 bg-black flex items-center justify-center flex-shrink-0 border-2 border-black">
                  <span className="text-white font-black text-sm">T</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between mb-1">
                    <div className="font-black text-sm sm:text-base">Tailwind CSS</div>
                    <div className="text-xs font-black">82%</div>
                  </div>
                  <div className="h-2 w-full bg-white border-2 border-black overflow-hidden">
                    <div className="h-full bg-black" style={{ width: "82%" }}></div>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-4 p-3 bg-white rounded-none border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                <div className="w-10 h-10 bg-black flex items-center justify-center flex-shrink-0 border-2 border-black">
                  <span className="text-white font-black text-sm">TS</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between mb-1">
                    <div className="font-black text-sm sm:text-base">TypeScript</div>
                    <div className="text-xs font-black">54%</div>
                  </div>
                  <div className="h-2 w-full bg-white border-2 border-black overflow-hidden">
                    <div className="h-full bg-black" style={{ width: "54%" }}></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-none p-6 sm:p-8 relative overflow-hidden min-h-[320px] sm:min-h-[380px] border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
            <div className="absolute top-0 left-0 w-full h-full opacity-10">
              <div
                className="w-full h-full"
                style={{
                  backgroundImage: `repeating-linear-gradient(
                  0deg,
                  transparent,
                  transparent 20px,
                  rgba(0,0,0,0.1) 20px,
                  rgba(0,0,0,0.1) 21px
                ), repeating-linear-gradient(
                  90deg,
                  transparent,
                  transparent 20px,
                  rgba(0,0,0,0.1) 20px,
                  rgba(0,0,0,0.1) 21px
                )`,
                }}
              ></div>
            </div>
            <div className="relative z-10 h-full flex flex-col justify-between">
              <div>
                <div className="font-black text-xs sm:text-sm uppercase mb-1 border-2 border-black inline-block px-2 py-1">
                  Top Category
                </div>
                <div className="font-[family-name:var(--font-space-grotesk)] text-3xl sm:text-[32px] font-black leading-none mt-4">
                  Dashboards
                </div>
              </div>

              <div>
                <div className="font-black text-sm mb-3 border-b-2 border-black pb-2">Favorite Palette</div>
                <div className="flex gap-2">
                  <div className="w-12 h-12 border-4 border-black bg-black"></div>
                  <div className="w-12 h-12 border-4 border-black bg-white"></div>
                  <div className="w-12 h-12 border-4 border-black bg-black"></div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-none p-5 sm:p-6 min-h-[320px] sm:min-h-[380px] border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] flex flex-col">
            <div className="text-xs sm:text-sm uppercase tracking-wider font-black mb-2 border-b-2 border-black pb-2">
              Peak Productivity
            </div>
            <div className="text-2xl sm:text-[28px] font-black text-black mb-1">Tuesday, 10 PM</div>
            <div className="text-sm font-bold mb-5">You are a night owl.</div>

            <div className="grid grid-cols-7 gap-1.5 mt-auto">
              {[...Array(28)].map((_, i) => {
                const isActive = [1, 3, 4, 7, 8, 9, 10, 11, 14, 15, 18, 22, 25, 26].includes(i)
                return (
                  <div key={i} className={`aspect-square border-2 border-black ${isActive ? "bg-black" : "bg-white"}`}></div>
                )
              })}
            </div>
          </div>

          <div className="md:col-span-2 lg:col-span-4 bg-white rounded-none p-6 sm:p-8 lg:p-12 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6 min-h-[200px] sm:min-h-[240px] border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
            <div>
              <h3 className="font-[family-name:var(--font-space-grotesk)] text-2xl sm:text-3xl font-black mb-2">
                Share your 2025 Wrapped
              </h3>
              <p className="text-black font-bold text-sm sm:text-base">
                Show the world what you&apos;ve built with 1UI.dev
              </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 w-full sm:w-auto">
              <button
                onClick={onDownloadImage}
                className="bg-white text-black border-4 border-black px-6 py-3 sm:py-4 font-black text-sm sm:text-base transition-transform hover:translate-x-1 hover:translate-y-1 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:shadow-none whitespace-nowrap"
              >
                Download Image
              </button>
              <button
                onClick={onShareOnX}
                className="bg-black text-white px-6 py-3 sm:py-4 font-black text-sm sm:text-base transition-transform hover:translate-x-1 hover:translate-y-1 flex items-center justify-center gap-2 border-4 border-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:shadow-none whitespace-nowrap"
              >
                Share on
                <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"></path>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
