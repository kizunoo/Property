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
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

UA = "Mozilla/5.0 (compatible; internal-catalog-build)"
MIN_BYTES, MAX_BYTES = 5_000, 5_000_000

# ADAPT-ME: candidate OFFICIAL product pages per SKU (first one that gives an image wins).
# Pages shared by a variant family (T600 / T600 Underride, CC1 / CC1 Pro, MT1 / MT1 Vac) may show a sibling:
# the review sheet is there to catch that. Put the right URL in --override when it does.
PAGES: dict[str, list[str]] = {
    "PUDU-T300": ["https://www.pudurobotics.com/products/pudut300", "https://www.pudurobotics.com/products/t300"],
    "PUDU-T600": ["https://www.pudurobotics.com/products/pudut600"],
    "PUDU-T600-UR": ["https://www.pudurobotics.com/products/pudut600"],
    "PUDU-FLASHBOT-MAX": ["https://www.pudurobotics.com/products/flashbotmax", "https://www.pudurobotics.com/products/flashbot-max"],
    "PUDU-CC1": ["https://www.pudurobotics.com/products/cc1"],
    "PUDU-CC1-PRO": ["https://www.pudurobotics.com/products/cc1pro", "https://www.pudurobotics.com/products/cc1-pro"],
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
    "MIR-250": ["https://mobile-industrial-robots.com/solutions/robots/mir250/"],
    "MIR-600": ["https://mobile-industrial-robots.com/solutions/robots/mir600/"],
    "MIR-1350": ["https://mobile-industrial-robots.com/solutions/robots/mir1350/"],
    "MIR-1200-PJ": ["https://mobile-industrial-robots.com/solutions/robots/mir1200-pallet-jack/"],
}


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
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()

    cat_path, out_dir, man_path = Path(a.catalog), Path(a.out), Path(a.manifest)
    rows, _ = read_catalog(cat_path)
    catalog = {r["sku_code"]: r for r in rows}

    if a.apply:
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
        n = apply_images(cat_path, manifest, {s.strip() for s in a.apply.split(",") if s.strip()})
        print(f"image_url written for {n} robots. Re-run the importer to load them.")
        return 0

    overrides = dict(o.split("=", 1) for o in a.override if "=" in o)
    old = {m["sku"]: m for m in json.loads(man_path.read_text(encoding="utf-8"))} if man_path.exists() else {}
    skus = [a.only] if a.only else list(catalog)
    results = []
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
    print("selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
