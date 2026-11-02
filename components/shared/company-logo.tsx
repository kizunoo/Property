"use client";
import { useState } from "react";

export function logoDomain(website?: string | null): string | null {
  if (!website) return null;
  const s = website.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "").split(/[/?#]/)[0];
  return /^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(s) ? s : null;
}

export function CompanyLogo({ name, website, size = 32 }: { name: string; website?: string | null; size?: number }) {
  const [failed, setFailed] = useState(false);
  const domain = logoDomain(website);
  const initials = (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
  const box: React.CSSProperties = { width: size, height: size, flexShrink: 0, borderRadius: 6, overflow: "hidden", display: "inline-flex", alignItems: "center", justifyContent: "center", background: "#fff", border: "1px solid rgba(128,128,128,0.35)" };
  if (!domain || failed) {
    return <span style={{ ...box, background: "rgba(128,128,128,0.18)", fontSize: Math.round(size * 0.4), fontWeight: 700 }} aria-label={name}>{initials}</span>;
  }
  return (
    <span style={box}>
      <img
        src={"https://www.google.com/s2/favicons?domain=" + encodeURIComponent(domain) + "&sz=128"}
        alt={name + " logo"}
        width={size}
        height={size}
        loading="lazy"
        referrerPolicy="no-referrer"
        style={{ width: "100%", height: "100%", objectFit: "contain" }}
        onLoad={(e) => { if ((e.currentTarget as HTMLImageElement).naturalWidth <= 16) setFailed(true); }}
        onError={() => setFailed(true)}
      />
    </span>
  );
}

