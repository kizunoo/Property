"""scripts/fetch_robot_images.py  (reference for PHASE 11; place unchanged)

For each robot in data/real/robots_catalog.csv: opens the manufacturer's own product page, reads its og:image
(the page's main product picture), downloads it to public/robots/<sku>.<ext>, and writes a REVIEW SHEET
(data/real/robot_images_review.html) so a human confirms every picture is the right model BEFORE it is used.
It never edits the catalog unless you pass --apply with the SKUs you approved.

  python scripts/fetch_robot_images.py                        # download + review sheet
  python scripts/fetch_robot_images.py --only PUDU-MT1        # one robot
  python scripts/fetch_robot_images.py --override PUDU-T300=https://...   # use a page/image URL you found yourself
  python scripts/fetch_robot_images.py --apply SKU1,SKU2      # write image_url=/robots/<file> into the CSV for approved SKUs
  python scripts/fetch_robot_images.py --selftest             # offline tests
Images are the manufacturers' product photos: fine for an internal tool; get the distributor's or manufacturer's
permission before showing them to outside companies in the portal.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

UA = "Mozilla/5.0 (compatible; internal-catalog-build)"
MIN_BYTES, MAX_BYTES = 5_000, 5_000_000

# ADAPT-ME: candidate OFFICIAL product pages per SKU (first one that gives an image wins).
# Pages shared by a variant family (T600 / T600 Underride, CC1 / CC1 Pro, MT1 / MT1 Vac) may show a sibling:
# the review sheet is there to catch that. Put the right URL in --override when it does.
PAGES: dict[str, list[str]] = {
    "PUDU-T300": ["https://www.pudurobotics.com/products/pudut300", "https://www.pudurobotics.com/products/t300"],
    "PUDU-T600": ["https://www.pudurobotics.com/products/pudut600"],
    "PUDU-T600-UR": ["https://www.pudurobotics.com/products/pudut600"],
    "PUDU-FLASHBOT-MAX": ["https://www.pudurobotics.com/products/flashbot-new", "https://www.pudurobotics.com/products/flashbotmax", "https://www.pudurobotics.com/products/flashbot-max"],
    "PUDU-CC1": ["https://www.pudurobotics.com/products/puduCC1", "https://www.pudurobotics.com/products/cc1"],
    "PUDU-CC1-PRO": ["https://www.pudurobotics.com/products/cc1-pro", "https://www.pudurobotics.com/products/cc1-pro-disc", "https://www.pudurobotics.com/products/cc1pro"],
    "PUDU-MT1": ["https://www.pudurobotics.com/products/mt1"],
    "PUDU-MT1-VAC": ["https://www.pudurobotics.com/products/mt1vac", "https://www.pudurobotics.com/products/mt1-vac"],
    "KEENON-W3": ["https://www.keenon.com/en/product/W3"],
    "KEENON-C40": ["https://www.keenon.com/en/product/C40"],
    "GAUSIUM-VAC40": ["https://gausium.com/specs/vacuum-40/", "https://gausium.com/specs/vacuum-40"],
    "GAUSIUM-PHANTAS": ["https://gausium.com/specs/phantas/"],
    "GAUSIUM-BEETLE": ["https://gausium.com/specs/beetle/"],
    "GAUSIUM-MARVEL": ["https://gausium.com/specs/marvel/"],
    "GAUSIUM-SCRUBBER-75": ["https://gausium.com/specs/scrubber-75/"],
    "GAUSIUM-SCRUBBER-50": ["https://gausium.com/specs/scrubber50/"],
    "MIR-250": ["https://mobile-industrial-robots.com/products/robots/mir250", "https://mobile-industrial-robots.com/solutions/robots/mir250/"],
    "MIR-600": ["https://mobile-industrial-robots.com/products/robots/mir600", "https://mobile-industrial-robots.com/solutions/robots/mir600/"],
    "MIR-1350": ["https://mobile-industrial-robots.com/products/robots/mir1350", "https://mobile-industrial-robots.com/solutions/robots/mir1350/"],
    "MIR-1200-PJ": ["https://mobile-industrial-robots.com/products/robots/mir1200-pallet-jack"],
}

# Lower-case words that appear in an image address when the picture is of that model.
HINTS = {
    "PUDU-T300":           ["pudut300", "t300"],
    "PUDU-T600":           ["pudut600", "t600"],
    "PUDU-T600-UR":        ["t600-ur", "t600ur", "underride", "under-ride"],
    "PUDU-FLASHBOT-MAX":   ["flashbot-max", "flashbotmax", "flashbot"],
    "PUDU-CC1":            ["puducc1", "cc1"],
    "PUDU-CC1-PRO":        ["cc1-pro", "cc1pro"],
    "PUDU-MT1":            ["mt1"],
    "PUDU-MT1-VAC":        ["mt1-vac", "mt1vac"],
    "KEENON-W3":           ["w3", "butlerbot"],
    "KEENON-C40":          ["c40", "kleenbot"],
    "GAUSIUM-VAC40":       ["vac40", "vac-40", "vacuum40", "vacuum-40"],
    "GAUSIUM-PHANTAS":     ["phantas"],
    "GAUSIUM-BEETLE":      ["beetle"],
    "GAUSIUM-MARVEL":      ["marvel"],
    "GAUSIUM-SCRUBBER-75": ["scrubber-75", "scrubber75", "75p"],
    "GAUSIUM-SCRUBBER-50": ["scrubber-50", "scrubber50", "50-pro", "50pro"],
    "MIR-250":             ["mir250"],
    "MIR-600":             ["mir600"],
    "MIR-1350":            ["mir1350"],
    "MIR-1200-PJ":         ["mir1200", "pallet-jack", "palletjack"],
}

ALLOWED_HOST_SUFFIXES = (
    "pudurobotics.com", "pudutech.com",      # incl. cdn.pudutech.com, www.pudurobotics.com, www.pudutech.com
    "keenon.com", "keenon.cn",               # incl. storage.keenon.cn, www.keenon.com
    "gausium.com",
    "storyblok.com",                         # MiR's own site serves images from here
    "mobile-industrial-robots.com", "mir-robots.com",
)

JUNK = re.compile(
    r"(logo|favicon|icon|sprite|avatar|qrcode|qr-|wechat|whatsapp|facebook|linkedin|"
    r"youtube|twitter|instagram|arrow|loading|placeholder|opengraph|og-image|share)",
    re.I,
)
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".avif"}
UNSAFE_CHARS = re.compile(r"""[\s"'`$\\<>|^{}\x00-\x1f]""")


class _Meta(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        key = (a.get("property") or a.get("name") or "").lower()
        if key in ("og:image", "og:image:url", "twitter:image") and a.get("content"):
            self.found.setdefault(key, a["content"])


def find_image_url(page_html: str, page_url: str) -> str | None:
    p = _Meta()
    try:
        p.feed(page_html)
    except Exception:
        pass
    raw = p.found.get("og:image") or p.found.get("og:image:url") or p.found.get("twitter:image")
    return urllib.parse.urljoin(page_url, html.unescape(raw)) if raw else None


def sniff_ext(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None  # svg, html error pages, etc. are refused


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(MAX_BYTES + 1)


def _get_curl(url: str, timeout: int = 20) -> bytes:
    """Same as _get but through curl, which uses the operating system's certificate store (Windows Schannel).
    Use when Python's own TLS check fails but your browser opens the site. Verification stays ON."""
    import subprocess
    r = subprocess.run(["curl", "-sSL", "--fail", "--max-time", str(timeout), "--max-filesize", str(MAX_BYTES),
                        "-A", UA, url], capture_output=True)
    if r.returncode != 0:
        raise OSError(f"curl exit {r.returncode}")
    return r.stdout


def shrink(data: bytes, ext: str, max_width: int) -> bytes:
    """Downscale wide images (the app serves files as-is). Needs Pillow; without it the original is kept."""
    if not max_width:
        return data
    try:
        import io
        from PIL import Image
    except ImportError:
        return data
    im = Image.open(io.BytesIO(data))
    if im.width <= max_width:
        return data
    im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    if ext == "jpg":
        im.convert("RGB").save(buf, "JPEG", quality=85, optimize=True)
    elif ext == "png":
        im.save(buf, "PNG", optimize=True)
    else:
        im.save(buf, "WEBP", quality=85)
    return buf.getvalue()


def fetch_one(sku: str, pages: list[str], out_dir: Path, get=_get, max_width: int = 0) -> dict:
    """Returns a manifest row. status is 'ok' or a short reason; nothing is invented."""
    last = "no page tried"
    for page in pages:
        try:
            if page.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")):
                img_url = page  # an --override that is already an image URL
            else:
                img_url = find_image_url(get(page).decode("utf-8", "ignore"), page)
                if not img_url:
                    last = "page has no og:image"
                    continue
            data = get(img_url)
        except Exception as e:
            last = f"fetch failed ({type(e).__name__})"
            continue
        ext = sniff_ext(data)
        if not ext:
            last = "not a jpg/png/webp image"
            continue
        if not (MIN_BYTES <= len(data) <= MAX_BYTES):
            last = f"image size {len(data)} bytes out of range"
            continue
        data = shrink(data, ext, max_width)
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{sku.lower()}.{ext}"
        (out_dir / fname).write_bytes(data)
        return {"sku": sku, "status": "ok", "file": fname, "page_url": page, "image_url": img_url, "bytes": len(data)}
    return {"sku": sku, "status": last, "file": "", "page_url": pages[0] if pages else "", "image_url": "", "bytes": 0}


def mark_duplicates(rows: list[dict], out_dir: Path) -> int:
    """Identical files for different robots mean a generic site image, not the model. They are marked so --apply skips them."""
    import hashlib
    groups: dict[str, list[dict]] = {}
    for m in rows:
        if m["status"] == "ok" and m["file"]:
            groups.setdefault(hashlib.sha256((out_dir / m["file"]).read_bytes()).hexdigest(), []).append(m)
    n = 0
    for g in groups.values():
        if len(g) > 1:
            for m in g:
                m["status"] = f"same file as {len(g) - 1} other robot(s): likely a generic site image, not this model"
            n += len(g)
    return n


def scan_folder(skus: list[str], out_dir: Path) -> list[dict]:
    """No network: build the manifest from files you saved by hand as <sku-lowercase>.jpg/.png/.webp in public/robots/."""
    rows = []
    for sku in skus:
        f = next((out_dir / f"{sku.lower()}.{e}" for e in ("jpg", "jpeg", "png", "webp") if (out_dir / f"{sku.lower()}.{e}").exists()), None)
        if f is None:
            rows.append({"sku": sku, "status": "no file found", "file": "", "page_url": "", "image_url": "", "bytes": 0})
            continue
        data = f.read_bytes()
        ok = sniff_ext(data) is not None and MIN_BYTES <= len(data) <= MAX_BYTES
        rows.append({"sku": sku, "status": "ok" if ok else "file is not a usable jpg/png/webp image", "file": f.name,
                     "page_url": "manual download", "image_url": "", "bytes": len(data)})
    return rows


_IMG_RE = re.compile(r"""(?:https?:)?//[^\s"'<>()\\]+?\.(?:jpe?g|png|webp)(?:\?[^\s"'<>()\\]*)?|(?<=["'(=])/[^\s"'<>()\\]+?\.(?:jpe?g|png|webp)""", re.I)


def decode_next_image(u: str) -> str:
    """https://site/_next/image?url=<encoded real url>&w=... -> the real url."""
    if "/_next/image" in u:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("url")
        if q:
            return q[0]
    return u


SKIP_WORDS = ("logo", "icon", "favicon", "sprite", "avatar", "float")


def list_page_images(page_html: str, page_url: str, sku: str = "") -> list[str]:
    """All image URLs found in a page (img src, srcset, JSON blobs), those mentioning the model first.
    Use it to pick the real product photo when og:image is only a generic site image, then pass it as --override SKU=<url>."""
    found: list[str] = []
    for m in _IMG_RE.finditer(html.unescape(page_html).replace("\\/", "/")):
        u = decode_next_image(urllib.parse.urljoin(page_url, m.group(0)))
        if u not in found:
            found.append(u)
    tokens = [t for t in re.split(r"[-_ ]+", sku.lower()) if len(t) >= 2 and t not in ("ur", "pj")]
    found.sort(key=lambda u: 0 if tokens and any(t in u.lower() for t in tokens) else 1)
    return found


def probe_url(url: str, get=_get) -> dict:
    """Load the link the way a visitor would and check it really is a picture. Nothing is saved."""
    try:
        data = get(url)
    except Exception as e:
        return {"ok": False, "why": f"fetch failed ({type(e).__name__})"}
    if not sniff_ext(data):
        return {"ok": False, "why": "not a jpg/png/webp image"}
    if not (MIN_BYTES <= len(data) <= MAX_BYTES):
        return {"ok": False, "why": f"image size {len(data)} bytes out of range"}
    return {"ok": True, "why": "ok", "bytes": len(data)}


def resolve_url(sku: str, pages: list[str], get=_get) -> dict:
    """Finds the image LINK for a robot (an --override that is already an image link, else the page's og:image)."""
    last = "no page tried"
    for page in pages:
        try:
            if page.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")):
                img = page
            else:
                img = find_image_url(get(page).decode("utf-8", "ignore"), page)
                if not img:
                    last = "page has no og:image"
                    continue
        except Exception as e:
            last = f"fetch failed ({type(e).__name__})"
            continue
        if not img.lower().startswith("https://"):
            last = "image link is not https"
            continue
        pr = probe_url(img, get)
        if pr["ok"]:
            return {"sku": sku, "status": "ok", "page_url": page, "image_url": img, "bytes": pr["bytes"]}
        last = pr["why"]
    return {"sku": sku, "status": last, "page_url": pages[0] if pages else "", "image_url": "", "bytes": 0}


def mark_duplicate_urls(rows: list[dict]) -> int:
    """The same link for several robots is a generic site image, not the model. Those are marked so --apply-urls skips them."""
    groups: dict[str, list[dict]] = {}
    for m in rows:
        if m["status"] == "ok" and m["image_url"]:
            groups.setdefault(m["image_url"], []).append(m)
    n = 0
    for g in groups.values():
        if len(g) > 1:
            for m in g:
                m["status"] = f"same link as {len(g) - 1} other robot(s): likely a generic site image, not this model"
            n += len(g)
    return n


def write_url_review(rows: list[dict], catalog: dict[str, dict], out: Path) -> None:
    cards = []
    for m in rows:
        c = catalog.get(m["sku"], {})
        spec = " | ".join(x for x in (c.get("dimensions"), f"{c.get('weight_kg')} kg" if c.get("weight_kg") else "") if x)
        if m["status"] == "ok":
            pic = f'<img src="{html.escape(m["image_url"])}" referrerpolicy="no-referrer" alt="{html.escape(m["sku"])}">'
        else:
            pic = f'<div class="miss">NO APPROVED IMAGE<br>{html.escape(m["status"])}</div>'
        link = f'<br><a href="{html.escape(m["image_url"])}">{html.escape(m["image_url"])}</a>' if m.get("image_url") else ""
        cards.append(
            f'<div class="card">{pic}<h3>{html.escape(c.get("name", m["sku"]))}</h3>'
            f'<p><b>{html.escape(m["sku"])}</b><br>{html.escape(c.get("manufacturer", ""))} &middot; {html.escape(c.get("category", ""))}<br>{html.escape(spec)}</p>'
            f'<p class="src">Page: <a href="{html.escape(m["page_url"])}">{html.escape(m["page_url"])}</a>{link}</p></div>'
        )
    out.write_text(
        "<!doctype html><meta charset='utf-8'><title>Robot image links review</title>"
        "<style>body{font-family:system-ui;margin:16px}.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}"
        ".card{border:1px solid #ccc;border-radius:8px;padding:10px}img{width:100%;height:200px;object-fit:contain;background:#f4f4f4}"
        ".miss{height:200px;display:flex;align-items:center;justify-content:center;background:#fee;text-align:center;padding:6px}.src{font-size:11px;word-break:break-all}</style>"
        "<h1>Is each picture the right robot?</h1><p>These load straight from the manufacturer, exactly as the app will show them. "
        "Check the model name and shape against the spec line. Approve with --apply-urls SKU1,SKU2.</p>"
        f"<div class='g'>{''.join(cards)}</div>",
        encoding="utf-8",
    )


def apply_urls(csv_path: Path, manifest: list[dict], approved: set[str]) -> int:
    rows, fields = read_catalog(csv_path)
    if "image_url" not in fields:
        raise SystemExit("catalog has no image_url column")
    ok = {m["sku"]: m["image_url"] for m in manifest if m["status"] == "ok" and m["image_url"].startswith("https://")}
    n = 0
    for r in rows:
        if r["sku_code"] in approved and r["sku_code"] in ok:
            r["image_url"] = ok[r["sku_code"]]
            n += 1
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return n


def check_links(rows: list[dict], get=_get) -> list[str]:
    """Returns the SKUs whose image_url no longer loads as a picture. Run before every demo."""
    bad = []
    for r in rows:
        u = (r.get("image_url") or "").strip()
        if u.startswith("https://") and not probe_url(u, get)["ok"]:
            bad.append(r["sku_code"])
    return bad


def manufacturer(sku: str) -> str:
    return sku.split("-")[0]


def family(sku: str) -> str:
    """PUDU-CC1-PRO -> PUDU-CC1, PUDU-T600-UR -> PUDU-T600 (variants may share a photo)."""
    return "-".join(sku.split("-")[:2])


def unwrap_next_image(url: str) -> str:
    """https://host/_next/image?url=%2Fa.png&w=640 -> https://host/a.png (if still wrapped)."""
    p = urlsplit(url)
    if p.path.endswith("/_next/image"):
        inner = parse_qs(p.query).get("url", [""])[0]
        inner = unquote(inner)
        if inner.startswith("https://"):
            return inner
        if inner.startswith("/"):
            return urlunsplit((p.scheme, p.netloc, inner, "", ""))
    return url


def norm_key(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, "", ""))


def _hint_hits(path: str, hints: list[str]) -> int:
    """Length of the longest hint found in path, 0 if none. 'w3' must not sit inside 'w300'."""
    best = 0
    for h in hints:
        if re.search(r"(?<![a-z0-9])" + re.escape(h.lower()) + r"(?![0-9])", path):
            best = max(best, len(h))
    return best


def _host_ok(host: str | None, suffixes=ALLOWED_HOST_SUFFIXES) -> bool:
    host = (host or "").lower().rstrip(".")
    if not host or re.fullmatch(r"[0-9.:\[\]]+", host) or host == "localhost":
        return False
    return any(host == s or host.endswith("." + s) for s in suffixes)


def safe_override_arg(sku: str, url: str) -> str | None:
    """Text for the picker's copy button, or None if the address must not be copied."""
    if UNSAFE_CHARS.search(url) or not url.startswith("https://"):
        return None
    if not _host_ok(urlsplit(url).hostname):
        return None
    return '--override "%s=%s"' % (sku, url)


def parse_override(value: str, known_skus: set[str]) -> tuple[str, str]:
    """
    Validate one --override value BEFORE anything is fetched.
    returns (sku, url) or raises ValueError with a short message (exit code 2 in the script).
    """
    if "=" not in value:
        raise ValueError("expected SKU=URL")
    sku, url = value.split("=", 1)
    sku, url = sku.strip().upper(), url.strip()
    if sku not in known_skus:
        raise ValueError("unknown SKU: %s" % sku)
    if UNSAFE_CHARS.search(url):
        raise ValueError("address contains characters that are not allowed")
    p = urlsplit(url)
    if p.scheme != "https":
        raise ValueError("address must start with https://")
    if not _host_ok(p.hostname):
        raise ValueError("host not allowed: %s (add it to ALLOWED_HOST_SUFFIXES if it is the "
                         "manufacturer's own)" % p.hostname)
    return sku, url


def rank_candidates(per_sku: dict[str, list[str]], hints: dict[str, list[str]] = HINTS, keep: int = 12) -> dict[str, dict]:
    clean, hidden_global = {}, {}
    for sku, urls in per_sku.items():
        seen, hid = {}, []
        for raw in urls:
            u = unwrap_next_image(raw.strip())
            p = urlsplit(u)
            ext = os.path.splitext(p.path.lower())[1]
            if p.scheme != "https":
                hid.append((u, "not https"))
            elif ext and ext not in IMG_EXT:
                hid.append((u, "not a picture file (%s)" % ext))
            elif JUNK.search(p.path):
                hid.append((u, "logo, icon or social image"))
            else:
                seen.setdefault(norm_key(u), u)
        clean[sku], hidden_global[sku] = seen, hid

    sharers, pool = {}, {}
    for sku, seen in clean.items():
        m = manufacturer(sku)
        for k, u in seen.items():
            sharers.setdefault((m, k), set()).add(sku)
            pool.setdefault(m, {}).setdefault(k, u)

    out = {}
    for sku in clean:
        m = manufacturer(sku)
        mine = hints.get(sku, [])
        others = [h for s, hs in hints.items() if s != sku and manufacturer(s) == m for h in hs]
        scored, hidden = [], list(hidden_global[sku])
        for k, u in pool.get(m, {}).items():
            path = urlsplit(u).path.lower()
            own = _hint_hits(path, mine)
            oth = _hint_hits(path, others)
            on_page = k in clean[sku]
            if not own and not on_page:
                continue
            if oth > own:
                hidden.append((u, "looks like another model"))
                continue
            fams = {family(s) for s in sharers[(m, k)]}
            if not own and len(fams) >= 2:
                hidden.append((u, "site-wide (on %d model pages)" % len(sharers[(m, k)])))
                continue
            tags, score = [], 0
            if own:
                tags.append("name match")
                score += 50 + own
            if on_page:
                tags.append("on its page")
                score += 10
                if len(sharers[(m, k)]) == 1:
                    tags.append("only on its page")
                    score += 5
            ext = os.path.splitext(path)[1]
            if ext in (".webp", ".png", ".jpg", ".jpeg"):
                score += 2
            scored.append((u, score, tags))
        scored.sort(key=lambda t: -t[1])
        shown = scored[:keep]
        hidden += [(u, "beyond the top %d" % keep) for u, _, _ in scored[keep:]]
        out[sku] = {"shown": shown, "hidden": hidden}
    return out


def candidate_counts(result: dict[str, dict]) -> list[str]:
    return ["%s: %d shown, %d hidden" % (s, len(r["shown"]), len(r["hidden"]))
            for s, r in result.items()]


def write_picker(items: dict[str, list[str]], catalog: dict[str, dict], out: Path, ranked: dict[str, dict] | None = None) -> None:
    """One section per robot with every candidate picture loaded from the manufacturer. Click 'copy' under the right one."""
    secs = []
    if ranked is None:
        for sku, urls in items.items():
            c = catalog.get(sku, {})
            spec = " | ".join(x for x in (c.get("dimensions"), f"{c.get('weight_kg')} kg" if c.get("weight_kg") else "") if x)
            tiles = "".join(
                f'<div class="t"><img loading="lazy" referrerpolicy="no-referrer" src="{html.escape(u)}" alt="">'
                f'<button data-cmd="{html.escape("--override " + sku + "=" + u)}">copy</button>'
                f'<span>{html.escape(u.rsplit("/", 1)[-1][:42])}</span></div>'
                for u in urls
            ) or "<p>No candidate pictures found on this page. Ask the supplier for a photo.</p>"
            secs.append(f'<h2>{html.escape(c.get("name", sku))} <small>{html.escape(sku)} &middot; {html.escape(spec)}</small></h2><div class="g">{tiles}</div>')
    else:
        for sku in items:
            c = catalog.get(sku, {})
            spec = " | ".join(x for x in (c.get("dimensions"), f"{c.get('weight_kg')} kg" if c.get("weight_kg") else "") if x)
            r = ranked.get(sku, {"shown": [], "hidden": []})
            shown = r.get("shown", [])
            hidden = r.get("hidden", [])

            shown_tiles = []
            for u, score, tags in shown:
                cmd = safe_override_arg(sku, u)
                if cmd is not None:
                    btn = f'<button data-cmd="{html.escape(cmd)}">copy</button>'
                else:
                    btn = '<span class="not-copyable">not copyable</span>'
                tags_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in tags)
                tags_div = f'<div class="tags">{tags_html}</div>' if tags_html else ""
                shown_tiles.append(
                    f'<div class="t"><img loading="lazy" referrerpolicy="no-referrer" src="{html.escape(u)}" alt="">'
                    f'{btn}{tags_div}'
                    f'<span>{html.escape(u.rsplit("/", 1)[-1][:42])}</span></div>'
                )

            tiles = "".join(shown_tiles) or "<p>No candidate pictures shown for this model.</p>"

            hidden_section = ""
            if hidden:
                hidden_tiles = "".join(
                    f'<div class="t muted"><img loading="lazy" referrerpolicy="no-referrer" src="{html.escape(u)}" alt="">'
                    f'<div class="why">{html.escape(reason)}</div>'
                    f'<span>{html.escape(u.rsplit("/", 1)[-1][:42])}</span></div>'
                    for u, reason in hidden
                )
                hidden_section = f'<details><summary>{len(hidden)} hidden candidates</summary><div class="g">{hidden_tiles}</div></details>'

            secs.append(
                f'<h2>{html.escape(c.get("name", sku))} <small>{html.escape(sku)} &middot; {html.escape(spec)} &middot; {len(shown)} shown, {len(hidden)} hidden</small></h2>'
                f'<div class="g">{tiles}</div>{hidden_section}'
            )

    out.write_text(
        "<!doctype html><meta charset='utf-8'><title>Pick the right robot picture</title>"
        "<style>body{font-family:system-ui;margin:16px}h2 small{font-weight:400;color:#666;font-size:13px}"
        ".g{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px;margin-bottom:24px}"
        ".t{border:1px solid #ddd;border-radius:6px;padding:6px;font-size:11px;word-break:break-all}"
        "img{width:100%;height:130px;object-fit:contain;background:#f4f4f4}button{display:block;margin:4px 0;width:100%}"
        ".tag{display:inline-block;background:#eef;border:1px solid #ccd;border-radius:3px;padding:1px 4px;font-size:9px;margin:2px 2px 0 0}"
        ".tags{margin-bottom:3px}.why{color:#888;font-size:10px;margin:3px 0}.muted{opacity:0.6}"
        ".not-copyable{display:block;margin:4px 0;font-size:10px;color:#c00;font-weight:bold}"
        "details{margin-top:8px}details summary{cursor:pointer;font-size:12px;color:#555;margin-bottom:8px}</style>"
        "<h1>Pick the picture that shows THIS robot</h1><p>Product shots on a plain background are best. Skip logos, diagrams and people. "
        "Click copy, then paste the flag into a note; send me one line per robot.</p>" + "".join(secs) +
        "<script>document.addEventListener('click',function(e){var c=e.target.dataset&&e.target.dataset.cmd;if(c){navigator.clipboard.writeText(c);e.target.textContent='copied'}})</script>",
        encoding="utf-8",
    )


def read_catalog(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return list(r), list(r.fieldnames or [])


def write_review(rows: list[dict], catalog: dict[str, dict], out: Path, img_rel: str) -> None:
    cards = []
    for m in rows:
        c = catalog.get(m["sku"], {})
        spec = " | ".join(x for x in (c.get("dimensions"), f"{c.get('weight_kg')} kg" if c.get("weight_kg") else "") if x)
        if m["status"] == "ok":
            pic = f'<img src="{html.escape(img_rel + "/" + m["file"])}" alt="{html.escape(m["sku"])}">'
        else:
            pic = f'<div class="miss">NO IMAGE<br>{html.escape(m["status"])}</div>'
        cards.append(
            f'<div class="card">{pic}<h3>{html.escape(c.get("name", m["sku"]))}</h3>'
            f'<p><b>{html.escape(m["sku"])}</b><br>{html.escape(c.get("manufacturer", ""))} &middot; {html.escape(c.get("category", ""))}<br>{html.escape(spec)}</p>'
            f'<p class="src">Source: <a href="{html.escape(m["page_url"])}">{html.escape(m["page_url"])}</a></p></div>'
        )
    out.write_text(
        "<!doctype html><meta charset='utf-8'><title>Robot images review</title>"
        "<style>body{font-family:system-ui;margin:16px}.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}"
        ".card{border:1px solid #ccc;border-radius:8px;padding:10px}img{width:100%;height:200px;object-fit:contain;background:#f4f4f4}"
        ".miss{height:200px;display:flex;align-items:center;justify-content:center;background:#fee;text-align:center}.src{font-size:11px;word-break:break-all}</style>"
        "<h1>Is each picture the right robot?</h1><p>Check the model name and shape against the spec line. Approve with --apply SKU1,SKU2.</p>"
        f"<div class='g'>{''.join(cards)}</div>",
        encoding="utf-8",
    )


def apply_images(csv_path: Path, manifest: list[dict], approved: set[str], web_prefix: str = "/robots") -> int:
    rows, fields = read_catalog(csv_path)
    if "image_url" not in fields:
        raise SystemExit("catalog has no image_url column")
    ok = {m["sku"]: m["file"] for m in manifest if m["status"] == "ok"}
    n = 0
    for r in rows:
        if r["sku_code"] in approved and r["sku_code"] in ok:
            r["image_url"] = f"{web_prefix}/{ok[r['sku_code']]}"
            n += 1
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/real/robots_catalog.csv")
    ap.add_argument("--out", default="public/robots")
    ap.add_argument("--review", default="data/real/robot_images_review.html")
    ap.add_argument("--manifest", default="data/real/robot_images_manifest.json")
    ap.add_argument("--only")
    ap.add_argument("--override", action="append", default=[], help="SKU=URL (page or direct image)")
    ap.add_argument("--apply", help="comma-separated approved SKUs to write into image_url")
    ap.add_argument("--curl", action="store_true", help="fetch through curl (OS certificate store); try this if every fetch fails with a TLS error")
    ap.add_argument("--max-width", type=int, default=900, help="downscale wider images (needs Pillow: pip install pillow); 0 keeps originals")
    ap.add_argument("--urls", action="store_true", help="LINK MODE (no downloads): find and test each robot's image link, write a review sheet that loads them from the manufacturer")
    ap.add_argument("--apply-urls", help="comma-separated approved SKUs: write their https image link into image_url")
    ap.add_argument("--check", action="store_true", help="test every image_url already in the catalog; exit 1 if any no longer loads")
    ap.add_argument("--pick", metavar="SKUS", help="comma-separated SKUs (or MISSING for every robot without an approved link): build a picture picker from each product page")
    ap.add_argument("--scan", action="store_true", help="no network: build the review sheet from files already in the output folder")
    ap.add_argument("--list-images", metavar="SKU", help="print image URLs found on that robot's product page (to choose an --override)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()

    cat_path, out_dir, man_path = Path(a.catalog), Path(a.out), Path(a.manifest)
    rows, _ = read_catalog(cat_path)
    catalog = {r["sku_code"]: r for r in rows}

    overrides = {}
    for o in a.override:
        try:
            sku, url = parse_override(o, set(catalog))
            overrides[sku] = url
        except ValueError as e:
            print(f"--override error: {e}", file=sys.stderr)
            return 2

    if a.apply:
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
        n = apply_images(cat_path, manifest, {s.strip() for s in a.apply.split(",") if s.strip()})
        print(f"image_url written for {n} robots. Re-run the importer to load them.")
        return 0

    if a.list_images:
        getter = _get_curl if a.curl else _get
        for page in PAGES.get(a.list_images, []):
            try:
                urls = list_page_images(getter(page).decode("utf-8", "ignore"), page, a.list_images)
            except Exception as e:
                print(f"{page}: fetch failed ({type(e).__name__})")
                continue
            print(f"{page}: {len(urls)} image URLs (model-matching first)")
            for u in urls[:30]:
                print("  ", u)
        return 0

    getter = _get_curl if a.curl else _get
    url_man = Path("data/real/robot_image_urls.json")
    if a.pick:
        if a.pick.upper() == "MISSING":
            prev_m = {m["sku"]: m for m in json.loads(url_man.read_text(encoding="utf-8"))} if url_man.exists() else {}
            want = [k for k in catalog if prev_m.get(k, {}).get("status") != "ok"]
        else:
            want = [x.strip() for x in a.pick.split(",") if x.strip()]
        items: dict[str, list[str]] = {}
        for sku in want:
            pages = [overrides[sku]] if sku in overrides else PAGES.get(sku, [])
            urls: list[str] = []
            for page in pages:
                try:
                    found = list_page_images(getter(page).decode("utf-8", "ignore"), page, sku)
                except Exception as e:
                    print(f"{sku}: {page} fetch failed ({type(e).__name__})")
                    continue
                urls += [u for u in found if u not in urls and not any(w in u.rsplit("/", 1)[-1].lower() for w in SKIP_WORDS)]
            items[sku] = urls
            print(f"{sku}: {len(items[sku])} candidate pictures")
        ranked = rank_candidates(items)
        for line in candidate_counts(ranked):
            print(line)
        write_picker(items, catalog, Path("data/real/robot_image_picker.html"), ranked=ranked)
        print("Open data/real/robot_image_picker.html, click copy under the right picture for each robot.")
        return 0
    if a.check:
        bad = check_links(rows, getter)
        have = sum(1 for r in rows if (r.get("image_url") or "").startswith("https://"))
        print(f"{have - len(bad)}/{have} image links load.", ("BROKEN: " + ", ".join(bad)) if bad else "")
        return 1 if bad else 0
    if a.apply_urls:
        n = apply_urls(cat_path, json.loads(url_man.read_text(encoding="utf-8")), {x.strip() for x in a.apply_urls.split(",") if x.strip()})
        print(f"image_url (https link) written for {n} robots. Re-run the importer to load them.")
        return 0
    if a.urls:
        prev = {m["sku"]: m for m in json.loads(url_man.read_text(encoding="utf-8"))} if url_man.exists() else {}
        todo = [a.only] if a.only else list(catalog)
        for sku in todo:
            pages = [overrides[sku]] if sku in overrides else PAGES.get(sku, [])
            m = resolve_url(sku, pages, getter) if pages else {"sku": sku, "status": "no product page configured", "page_url": "", "image_url": "", "bytes": 0}
            prev[sku] = m
            print(("OK   " if m["status"] == "ok" else "MISS ") + sku + ("" if m["status"] == "ok" else f" - {m['status']}"))
            time.sleep(1.0)
        final = [prev[x] for x in catalog if x in prev]
        d = mark_duplicate_urls(final)
        if d:
            print(f"WARNING: {d} robots share one image link and are marked as not approved (generic images).")
        url_man.parent.mkdir(parents=True, exist_ok=True)
        url_man.write_text(json.dumps(final, indent=1), encoding="utf-8")
        write_url_review(final, catalog, Path("data/real/robot_images_review.html"))
        print(f"{sum(m['status'] == 'ok' for m in final)}/{len(final)} usable links. Open data/real/robot_images_review.html and check each picture.")
        return 0
    old = {m["sku"]: m for m in json.loads(man_path.read_text(encoding="utf-8"))} if man_path.exists() else {}
    skus = [a.only] if a.only else list(catalog)
    results = []
    if a.scan:
        results = scan_folder(skus, out_dir)
        skus = []
    for sku in skus:
        pages = [overrides[sku]] if sku in overrides else PAGES.get(sku, [])
        if not pages:
            m = {"sku": sku, "status": "no product page configured", "file": "", "page_url": "", "image_url": "", "bytes": 0}
        else:
            m = fetch_one(sku, pages, out_dir, get=_get_curl if a.curl else _get, max_width=a.max_width)
            time.sleep(1.0)
        results.append(m)
        print(("OK   " if m["status"] == "ok" else "MISS ") + sku + ("" if m["status"] == "ok" else f" - {m['status']}"))
    merged = {**old, **{m["sku"]: m for m in results}}
    final = [merged[s] for s in catalog if s in merged]
    dups = mark_duplicates(final, out_dir)
    if dups:
        print(f"WARNING: {dups} robots share identical image files and are marked as not approved (generic images).")
    man_path.parent.mkdir(parents=True, exist_ok=True)
    man_path.write_text(json.dumps(final, indent=1), encoding="utf-8")
    write_review(final, catalog, Path(a.review), "../../" + out_dir.as_posix())
    print(f"{sum(m['status']=='ok' for m in final)}/{len(final)} images downloaded. Open {a.review} and check each picture.")
    return 0


def selftest() -> int:
    import tempfile, threading, http.server, socketserver, functools
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 6000
    assert sniff_ext(png) == "png" and sniff_ext(b"\xff\xd8\xff" + b"0" * 10) == "jpg" and sniff_ext(b"<html>") is None
    assert sniff_ext(b"RIFF\x00\x00\x00\x00WEBPxxxx") == "webp"
    h = '<head><meta property="og:image" content="/img/a&amp;b.png"><meta name="twitter:image" content="x.jpg"></head>'
    assert find_image_url(h, "https://e.com/p/q") == "https://e.com/img/a&b.png"
    assert find_image_url("<head></head>", "https://e.com/") is None
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "site").mkdir()
        (d / "site" / "good.html").write_text('<meta property="og:image" content="/robot.png">')
        (d / "site" / "robot.png").write_bytes(png)
        (d / "site" / "noimg.html").write_text("<html></html>")
        (d / "site" / "fake.html").write_text('<meta property="og:image" content="/notimage.html">')
        (d / "site" / "notimage.html").write_text("<html>" + "x" * 6000)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(d / "site"))
        handler.log_message = lambda *a, **k: None
        with socketserver.TCPServer(("127.0.0.1", 0), handler) as srv:
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{port}"
            out = d / "out"
            assert fetch_one("T-1", [base + "/missing.html", base + "/good.html"], out)["status"] == "ok"   # falls through to the 2nd page
            assert (out / "t-1.png").exists()
            assert fetch_one("T-2", [base + "/noimg.html"], out)["status"] == "page has no og:image"
            assert fetch_one("T-3", [base + "/fake.html"], out)["status"] == "not a jpg/png/webp image"
            assert fetch_one("T-4", [base + "/robot.png"], out)["status"] == "ok"                              # direct image override
            srv.shutdown()
        # apply + review
        cat = d / "c.csv"
        cat.write_text("sku_code,name,manufacturer,category,image_url,dimensions,weight_kg\nT-1,Robot One,Acme,AMR,,1 x 2 x 3 mm,5\nT-2,Robot Two,Acme,AMR,,,\n")
        man = [{"sku": "T-1", "status": "ok", "file": "t-1.png", "page_url": "p", "image_url": "i", "bytes": 1},
               {"sku": "T-2", "status": "page has no og:image", "file": "", "page_url": "p", "image_url": "", "bytes": 0}]
        assert apply_images(cat, man, {"T-1", "T-2"}) == 1                    # T-2 has no image so it is never written
        got = {r["sku_code"]: r["image_url"] for r in read_catalog(cat)[0]}
        assert got == {"T-1": "/robots/t-1.png", "T-2": ""}, got
        write_review(man, {r["sku_code"]: r for r in read_catalog(cat)[0]}, d / "r.html", "../x")
        assert "NO IMAGE" in (d / "r.html").read_text() and "t-1.png" in (d / "r.html").read_text()
    # duplicates, folder scan, image listing
    with tempfile.TemporaryDirectory() as d3:
        d3 = Path(d3)
        (d3 / "a.png").write_bytes(png); (d3 / "b.png").write_bytes(png); (d3 / "c.png").write_bytes(png + b"1")
        rows = [{"sku": k, "status": "ok", "file": f, "page_url": "p", "image_url": "", "bytes": 1} for k, f in (("A", "a.png"), ("B", "b.png"), ("C", "c.png"))]
        assert mark_duplicates(rows, d3) == 2
        assert [r["status"] == "ok" for r in rows] == [False, False, True]
        xcsv = d3 / "x.csv"
        xcsv.write_text("sku_code,image_url\nA,\nC,\n")
        assert apply_images(xcsv, rows, {"A", "C"}) == 1                      # A is a duplicate so only C is written
        (d3 / "robo-1.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * 6000); (d3 / "robo-2.png").write_bytes(b"<html>" * 2000)
        sc = {r["sku"]: r["status"] for r in scan_folder(["ROBO-1", "ROBO-2", "ROBO-3"], d3)}
        assert sc == {"ROBO-1": "ok", "ROBO-2": "file is not a usable jpg/png/webp image", "ROBO-3": "no file found"}, sc
    page = '<img src="/media/mt1-hero.jpg"><img data-src="https://cdn.x.com/logo.png"><script>{"u":"https:\\/\\/cdn.x.com\\/a\\/mt1-side.webp?w=800"}</script>'
    urls = list_page_images(page, "https://e.com/products/mt1", "PUDU-MT1")
    assert urls[0].startswith("https://e.com/media/mt1-hero.jpg") and "https://cdn.x.com/a/mt1-side.webp?w=800" in urls[:2] and urls[-1] == "https://cdn.x.com/logo.png", urls
    # link mode
    with tempfile.TemporaryDirectory() as d4:
        d4 = Path(d4); (d4 / "site").mkdir()
        (d4 / "site" / "robot.png").write_bytes(png)
        h4 = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(d4 / "site")); h4.log_message = lambda *a, **k: None
        with socketserver.TCPServer(("127.0.0.1", 0), h4) as srv4:
            threading.Thread(target=srv4.serve_forever, daemon=True).start()
            base4 = f"http://127.0.0.1:{srv4.server_address[1]}"
            assert probe_url(base4 + "/robot.png")["ok"] and not probe_url(base4 + "/nope.png")["ok"]
            srv4.shutdown()
    assert resolve_url("X", ["http://e.com/a.png"], get=lambda u: png)["status"] == "image link is not https"
    good = resolve_url("X", ["https://e.com/a.png"], get=lambda u: png)
    assert good["status"] == "ok" and good["image_url"] == "https://e.com/a.png"
    rows4 = [dict(good, sku="A"), dict(good, sku="B"), {"sku": "C", "status": "ok", "page_url": "p", "image_url": "https://e.com/c.png", "bytes": 1}]
    assert mark_duplicate_urls(rows4) == 2 and [r["status"] == "ok" for r in rows4] == [False, False, True]
    with tempfile.TemporaryDirectory() as d5:
        c5 = Path(d5) / "c.csv"; c5.write_text("sku_code,image_url\nA,\nC,\nD,https://e.com/old.png\n")
        assert apply_urls(c5, rows4, {"A", "C"}) == 1
        got5 = {r["sku_code"]: r["image_url"] for r in read_catalog(c5)[0]}
        assert got5 == {"A": "", "C": "https://e.com/c.png", "D": "https://e.com/old.png"}, got5
        assert check_links(read_catalog(c5)[0], get=lambda u: png if "c.png" in u else b"<html>") == ["D"]
    # picker + next/image decoding
    assert decode_next_image("https://a.com/_next/image?url=https%3A%2F%2Fcdn.x.com%2Fm%2Fs1.webp&w=640&q=75") == "https://cdn.x.com/m/s1.webp"
    assert decode_next_image("https://a.com/x.png") == "https://a.com/x.png"
    pg = '<img src="https://a.com/_next/image?url=https%3A%2F%2Fcdn.x.com%2Fmt1%2FS1-3.webp&w=640"><img src="https://cdn.x.com/logo-up.png">'
    got6 = list_page_images(pg, "https://a.com/p", "PUDU-MT1")
    assert got6[0] == "https://cdn.x.com/mt1/S1-3.webp", got6
    with tempfile.TemporaryDirectory() as d6:
        out6 = Path(d6) / "pick.html"
        write_picker({"X-1": ["https://cdn.x.com/a.webp"], "X-2": []}, {"X-1": {"name": "Robot", "dimensions": "1 mm"}}, out6)
        t6 = out6.read_text()
        assert 'data-cmd="--override X-1=https://cdn.x.com/a.webp"' in t6 and "No candidate pictures" in t6 and 'referrerpolicy="no-referrer"' in t6
    # curl path and resize (skipped when curl or Pillow are not installed)
    import shutil
    if shutil.which("curl"):
        with tempfile.TemporaryDirectory() as d2:
            d2 = Path(d2); (d2 / "site").mkdir(); (d2 / "site" / "robot.png").write_bytes(png)
            h2 = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(d2 / "site")); h2.log_message = lambda *a, **k: None
            with socketserver.TCPServer(("127.0.0.1", 0), h2) as srv2:
                threading.Thread(target=srv2.serve_forever, daemon=True).start()
                r = fetch_one("T-5", [f"http://127.0.0.1:{srv2.server_address[1]}/robot.png"], d2 / "o", get=_get_curl)
                assert r["status"] == "ok", r
                srv2.shutdown()
    try:
        import io
        from PIL import Image
        buf = io.BytesIO(); Image.new("RGB", (2000, 1000), (200, 50, 50)).save(buf, "JPEG"); big = buf.getvalue()
        small = shrink(big, "jpg", 900)
        assert Image.open(io.BytesIO(small)).size == (900, 450) and len(small) < len(big)
        assert shrink(big, "jpg", 0) == big
    except ImportError:
        pass
    # Keenon: menu images are on both pages; each model's own picture is also in the menu.
    menu = ["https://storage.keenon.cn/uploads/menu/%02d.png" % i for i in range(1, 25)]
    w3_page = menu + ["https://storage.keenon.cn/uploads/w3.png",
                      "https://storage.keenon.cn/uploads/c40.png",
                      "https://storage.keenon.cn/uploads/w3-front-view.webp",
                      "https://storage.keenon.cn/uploads/keenon-logo.png",
                      "https://storage.keenon.cn/uploads/promo.svg",
                      "http://storage.keenon.cn/uploads/w3-insecure.png"]
    c40_page = menu + ["https://storage.keenon.cn/uploads/c40-hero.jpg",
                       "https://storage.keenon.cn/uploads/w3.png"]
    r = rank_candidates({"KEENON-W3": w3_page, "KEENON-C40": c40_page})
    w3 = [u for u, _, _ in r["KEENON-W3"]["shown"]]
    c40 = [u for u, _, _ in r["KEENON-C40"]["shown"]]
    assert w3[0].endswith("w3.png") or w3[0].endswith("w3-front-view.webp"), w3[:2]
    assert not any("c40" in u for u in w3), "another model's picture leaked into W3"
    assert not any("menu" in u for u in w3 + c40), "site-wide menu images were not hidden"
    assert any(u.endswith("c40.png") for u in c40), "menu thumbnail was not routed to C40"
    assert not any(u.endswith("w3.png") for u in c40)
    hid = " ".join(why for _, why in r["KEENON-W3"]["hidden"])
    assert "logo" in hid and "not a picture" in hid and "not https" in hid

    # Pudu: CC1 and CC1 Pro must not receive each other's pictures; variants may share.
    pudu = {
        "PUDU-CC1": ["https://cdn.pudutech.com/official-website/cc1/hero.png"],
        "PUDU-CC1-PRO": ["https://cdn.pudutech.com/official-website/cc1-pro/hero.png",
                         "https://cdn.pudutech.com/official-website/shared/banner.jpg"],
        "PUDU-MT1": ["https://cdn.pudutech.com/official-website/mt1/S1-3.webp",
                     "https://cdn.pudutech.com/official-website/shared/banner.jpg"],
    }
    r = rank_candidates(pudu)
    assert [u.split("/")[-2] for u, _, _ in r["PUDU-CC1"]["shown"]] == ["cc1"]
    assert [u.split("/")[-2] for u, _, _ in r["PUDU-CC1-PRO"]["shown"]] == ["cc1-pro"]
    assert any("banner" in u for u, _ in r["PUDU-MT1"]["hidden"])
    assert "_next" not in " ".join(u for v in r.values() for u, _, _ in v["shown"])
    assert unwrap_next_image("https://x.pudurobotics.com/_next/image?url=%2Fa%2Fb.png&w=640&q=75") \
        == "https://x.pudurobotics.com/a/b.png"

    # Copy-button text and override validation.
    ok = "https://cdn.pudutech.com/official-website/mt1/S1-3.webp"
    assert safe_override_arg("PUDU-MT1", ok) == '--override "PUDU-MT1=%s"' % ok
    for bad in ('https://cdn.pudutech.com/a"; calc ; ".png', "https://cdn.pudutech.com/a$b.png",
                "https://cdn.pudutech.com/a`b.png", "https://evil.example.com/a.png",
                "https://127.0.0.1/a.png", "http://cdn.pudutech.com/a.png",
                "https://cdn.pudutech.com/a b.png"):
        assert safe_override_arg("PUDU-MT1", bad) is None, bad
    assert parse_override("pudu-mt1=" + ok, set(HINTS)) == ("PUDU-MT1", ok)
    for bad in ("PUDU-MT1", "NOPE=" + ok, "PUDU-MT1=http://cdn.pudutech.com/a.png",
                "PUDU-MT1=https://localhost/a.png", "PUDU-MT1=https://x.evil.com/a.png"):
        try:
            parse_override(bad, set(HINTS))
        except ValueError:
            continue
        raise AssertionError("accepted: " + bad)
    print("selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
