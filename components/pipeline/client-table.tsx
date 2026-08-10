"use client"

import { useState, type ComponentType } from "react"
import { CheckCircle2, DollarSign, Home, Send, Tags, TrendingUp, UserRound, Percent as PercentIcon } from "lucide-react"
import { TIER_SHORT, currency, percent, type Client } from "@/lib/pipeline-data"

interface ClientTableProps {
  clients: Client[]
  onGenerateInvite: (client: Client) => void
}

function TierBadge({ tier }: { tier: Client["tier"] }) {
  const styles: Record<Client["tier"], string> = {
    TIER_1: "bg-primary text-black",
    TIER_2: "bg-black text-white",
    TIER_3: "bg-white text-black",
  }
  return (
    <span
      className={`inline-block border-2 border-black px-2.5 py-1 text-[10px] sm:text-xs font-black uppercase tracking-wider ${styles[tier]}`}
    >
      {TIER_SHORT[tier]}
    </span>
  )
}

function ColumnHeading({ icon: Icon, children }: { icon: ComponentType<{ className?: string; strokeWidth?: number }>; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon className="h-3.5 w-3.5" strokeWidth={2.5} />
      {children}
    </span>
  )
}

export function ClientTable({ clients, onGenerateInvite }: ClientTableProps) {
  const [invited, setInvited] = useState<Record<string, boolean>>({})

  function handleInvite(client: Client) {
    setInvited((prev) => ({ ...prev, [client.id]: true }))
    onGenerateInvite(client)
  }

  return (
    <div className="border-4 border-black bg-card shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] overflow-hidden">
      <div className="overflow-x-auto scrollbar-none">
        <table className="w-full min-w-[880px] border-collapse">
          <thead>
            <tr className="bg-black text-white">
              <th className="border-b-4 border-black px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
                <ColumnHeading icon={UserRound}>Client</ColumnHeading>
              </th>
              <th className="border-b-4 border-black px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
                <ColumnHeading icon={Home}>Target Property</ColumnHeading>
              </th>
              <th className="border-b-4 border-black px-4 py-3.5 text-right text-xs font-black uppercase tracking-wider sm:px-5">
                <ColumnHeading icon={DollarSign}>Property Value</ColumnHeading>
              </th>
              <th className="border-b-4 border-black px-4 py-3.5 text-right text-xs font-black uppercase tracking-wider sm:px-5">
                <ColumnHeading icon={PercentIcon}>Probability</ColumnHeading>
              </th>
              <th className="border-b-4 border-black px-4 py-3.5 text-right text-xs font-black uppercase tracking-wider sm:px-5">
                <ColumnHeading icon={TrendingUp}>Expected Value</ColumnHeading>
              </th>
              <th className="border-b-4 border-black px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
                <ColumnHeading icon={Tags}>Segment</ColumnHeading>
              </th>
              <th className="border-b-4 border-black px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
                <ColumnHeading icon={Send}>Action</ColumnHeading>
              </th>
            </tr>
          </thead>
          <tbody>
            {clients.map((client, index) => (
              <tr
                key={client.id}
                className={`border-b-2 border-black last:border-b-0 ${index % 2 === 1 ? "bg-secondary" : "bg-card"}`}
              >
                <td className="px-4 py-4 sm:px-5">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center border-2 border-black bg-black text-xs font-black text-white">
                      {client.initials}
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5 text-sm font-black leading-tight sm:text-base">
                        <UserRound className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={2.5} />
                        {client.name}
                      </div>
                      <div className="font-mono text-[11px] text-muted-foreground">
                        {client.id} · {client.agent}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-4 text-sm font-bold sm:px-5">{client.property}</td>
                <td className="px-4 py-4 text-right font-mono text-sm font-bold sm:px-5">
                  {currency(client.propertyValue)}
                </td>
                <td className="px-4 py-4 text-right sm:px-5">
                  <div className="flex items-center justify-end gap-2">
                    <div className="h-2.5 w-16 border-2 border-black bg-white sm:w-20">
                      <div className="h-full bg-black" style={{ width: `${Math.round(client.probability * 100)}%` }} />
                    </div>
                    <span className="w-10 text-right font-mono text-sm font-black">{percent(client.probability)}</span>
                  </div>
                </td>
                <td className="px-4 py-4 text-right sm:px-5">
                  <span className="border-2 border-black bg-primary px-2 py-1 font-mono text-sm font-black text-black">
                    {currency(client.expectedValue)}
                  </span>
                </td>
                <td className="px-4 py-4 sm:px-5">
                  <TierBadge tier={client.tier} />
                </td>
                <td className="px-4 py-4 sm:px-5">
                  {client.tier === "TIER_1" ? (
                    <button
                      type="button"
                      onClick={() => handleInvite(client)}
                      disabled={invited[client.id]}
                      className={`flex items-center gap-1.5 whitespace-nowrap border-2 border-black px-3 py-2 text-xs font-black uppercase tracking-wider transition-transform ${
                        invited[client.id]
                          ? "bg-white text-muted-foreground"
                          : "bg-black text-white shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none"
                      }`}
                    >
                      {invited[client.id] ? (
                        <>
                          <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={2.5} />
                          Invite Sent
                        </>
                      ) : (
                        <>
                          <Send className="h-3.5 w-3.5 text-primary" strokeWidth={2.5} />
                          Generate Invite
                        </>
                      )}
                    </button>
                  ) : (
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
