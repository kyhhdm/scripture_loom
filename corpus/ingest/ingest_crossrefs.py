"""Normalize the OpenBible.info cross-reference TSV into canon refs."""
import io, json, sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import osis, refs as reflib

CORPUS = Path(__file__).resolve().parents[1]

# OpenBible uses OSIS book abbreviations; map to our USFM codes (shared: lib/osis).


def _conv(osis_ref):
    """'Gen.1.1' -> 'GEN.1.1'; 'Prov.8.22-Prov.8.30' -> 'PRO.8.22-30' or full form."""
    def one(r):
        book, ch, v = r.split(".")
        return f"{osis.OSIS_TO_USFM[book]}.{ch}.{v}"
    if "-" in osis_ref:
        a, b = osis_ref.split("-", 1)
        ra, rb = one(a), one(b)
        (b1, c1, _), (b2, c2, v2) = reflib.parse(ra), reflib.parse(rb)
        if b1 == b2 and c1 == c2:
            return f"{ra}-{v2}"
        return f"{ra}-{rb}"
    return one(osis_ref)


def main():
    src = CORPUS / "sources" / "openbible-crossrefs"
    meta = json.loads((src / "meta.json").read_text())
    blob = (src / meta["file"]).read_bytes()
    if meta["file"].endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            name = next(n for n in z.namelist() if n.endswith(".txt"))
            text = z.read(name).decode("utf-8")
    else:
        text = blob.decode("utf-8")

    out, skipped = [], 0
    unmatched = {}
    for line in text.splitlines():
        if not line or line.startswith("From Verse"):
            continue
        frm, to, votes = line.split("\t")[:3]
        try:
            f = _conv(frm)
            t = _conv(to)
            reflib.parse(f), reflib.parse_range(t)
        except (KeyError, ValueError) as e:
            # KeyError: OSIS book token not in OSIS_TO_USFM (unmapped/deuterocanon).
            # ValueError: refs.parse/parse_range rejected the ref outright — in
            # practice this is entirely cross-book ranges (e.g. 2Chr.36.22-Ezra.1.3),
            # which the Task 2 `refs.parse_range` schema categorically cannot
            # represent (it requires start/end in the same book). These are real,
            # canonically significant cross-references dropped by schema limitation,
            # not junk data.
            skipped += 1
            if isinstance(e, KeyError):
                tok = e.args[0]
                unmatched[tok] = unmatched.get(tok, 0) + 1
            continue
        out.append({"from": f, "to": t, "weight": int(votes),
                    "sources": ["openbible"]})

    dest = CORPUS / "canon" / "structure" / "crossrefs.json"
    dest.write_text(json.dumps(
        {"license": "CC-BY",
         "license_note": "openbible.info — attribute in any shipped product",
         "license_url": "https://www.openbible.info/labs/cross-references/",
         "role": "displayable", "refs": out},
        indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(out)} refs written, {skipped} skipped -> {dest}")
    if unmatched:
        print("Unmatched book tokens:", sorted(unmatched.items(), key=lambda kv: -kv[1])[:30])


if __name__ == "__main__":
    main()
