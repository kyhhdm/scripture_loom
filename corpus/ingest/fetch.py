"""Download one source file into corpus/sources/<name>/ and record provenance."""
import hashlib, json, sys
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen


def fetch(url, dest_dir, license_note):
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    name = url.rsplit("/", 1)[-1]
    req = Request(url, headers={"User-Agent": "scripture-loom-corpus/0.1"})
    data = urlopen(req).read()
    (dest / name).write_bytes(data)
    meta = {"url": url, "fetched": date.today().isoformat(),
            "license": license_note, "file": name,
            "sha256": hashlib.sha256(data).hexdigest()}
    (dest / "meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n")
    print(f"{name}: {len(data)} bytes sha256={meta['sha256'][:12]}…")
    return meta


if __name__ == "__main__":
    fetch(sys.argv[1], sys.argv[2], sys.argv[3])
