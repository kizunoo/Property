import { Building2, MapPin } from "lucide-react"
import { PROPERTIES, currency, type Property } from "@/lib/pipeline-data"

const STATUS_STYLES: Record<Property["status"], string> = {
  LISTED: "bg-white text-black",
  PENDING: "bg-black text-white",
  "UNDER OFFER": "bg-primary text-black",
}

function PropertyCard({ property }: { property: Property }) {
  return (
    <div className="flex flex-col border-4 border-black bg-card shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
      <div className="stripes-diagonal relative flex h-36 items-center justify-center border-b-4 border-black bg-white sm:h-40">
        <div className="relative z-10 flex h-16 w-16 items-center justify-center border-4 border-black bg-black">
          <Building2 className="h-7 w-7 text-primary" strokeWidth={2.5} />
        </div>
      </div>
      <div className="flex flex-1 flex-col gap-3 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-lg font-bold leading-tight tracking-tight sm:text-xl">{property.name}</h3>
          <span
            className={`shrink-0 border-2 border-black px-2 py-1 text-[10px] font-black uppercase tracking-wider ${STATUS_STYLES[property.status]}`}
          >
            {property.status}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-bold text-muted-foreground sm:text-sm">
          <MapPin className="h-3.5 w-3.5 shrink-0" strokeWidth={2.5} />
          {property.address}
        </div>
        <div className="mt-auto border-t-2 border-black pt-3">
          <div className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Property Value</div>
          <div className="font-mono text-2xl font-black leading-none sm:text-3xl">{currency(property.value)}</div>
        </div>
      </div>
    </div>
  )
}

export function PropertyCards() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-3">
      {PROPERTIES.map((property) => (
        <PropertyCard key={property.id} property={property} />
      ))}
    </div>
  )
}
