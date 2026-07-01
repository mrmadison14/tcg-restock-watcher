import sys, json, urllib.request, urllib.error

FEEDS = [
    "https://collectorsrow.cards",
    "https://thepokehive.com",
    "https://hobbiesville.com",
    "https://deckoutgaming.ca",
    "https://allpoketcg.com",
    "https://skyboxct.com",
    "https://matrixtcg.com",
    "https://store.401games.ca",
]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def probe(base):
    url = f"{base}/products.json?limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            n = len(json.loads(body).get("products", []))
            return (base, r.getcode(), f"ok products_parsed={n}")
    except urllib.error.HTTPError as e:
        return (base, e.code, f"HTTPError {e.reason}")
    except Exception as e:
        return (base, "ERR", f"{type(e).__name__}: {e}")


def main():
    rows = [probe(b) for b in FEEDS]
    blocked = []
    for base, code, note in rows:
        ok = code == 200 and note.startswith("ok")
        print(f"{'PASS' if ok else 'FAIL'}  {code!s:>5}  {base:30}  {note}")
        if not ok:
            blocked.append(base)
    if blocked:
        print(f"\nBLOCKED/UNREADABLE: {len(blocked)} -> {blocked}")
        sys.exit(1)
    print("\nAll feeds readable from this runner.")


if __name__ == "__main__":
    main()
