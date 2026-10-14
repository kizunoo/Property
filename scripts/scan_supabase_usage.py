"""
scripts/scan_supabase_usage.py
Scans app/api, lib, and components for direct Supabase client creation or public key usage.
"""

import glob
import os

PATTERNS = [
    "app/api/**/*.ts",
    "lib/**/*.ts",
    "lib/**/*.tsx",
    "components/**/*.ts",
    "components/**/*.tsx",
]

KEYWORDS = [
    "createClient",
    "NEXT_PUBLIC_SUPABASE",
    "@supabase/supabase-js",
    "@supabase/ssr",
]

def scan():
    total_files = 0
    matches = {}
    for pat in PATTERNS:
        for fpath in glob.glob(pat, recursive=True):
            norm = fpath.replace("\\", "/")
            total_files += 1
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            file_hits = []
            for i, line in enumerate(content.splitlines(), 1):
                if any(k in line for k in KEYWORDS):
                    file_hits.append((i, line.strip()))
            if file_hits:
                matches[norm] = file_hits

    print(f"Scanned {total_files} files.")
    print(f"Found {len(matches)} files referencing Supabase client or public keys:\n")
    for f, hits in sorted(matches.items()):
        print(f"File: {f}")
        for lno, text in hits:
            print(f"   L{lno}: {text}")
        print()

if __name__ == "__main__":
    scan()
