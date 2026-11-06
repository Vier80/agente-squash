"""Esplorazione del sito IJF (ijf.org) per l'agente judo.

Non scrive nulla da nessuna parte: legge alcune pagine, cerca da dove il sito prende
i dati degli incontri (contests) e stampa un riassunto da incollare in chat.
"""
import json
import re
import sys
import traceback

import requests

BASE = "https://www.ijf.org"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
COMP = 3151  # Mondiali Baku 2026

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "en"})


def get(url, **kw):
    return S.get(url if url.startswith("http") else BASE + url, timeout=45, **kw)


def parte1_requests():
    print("=================== PARTE 1: pagine lette con requests ===================")
    for path in (f"/competition/{COMP}/contests", f"/competition/{COMP}/draw",
                 f"/competition/{COMP}/results", "/calendar?age=sen&year=2027",
                 "/calendar?age=sen&year=2026"):
        try:
            r = get(path)
        except Exception as e:
            print(f"\nGET {path} -> errore {e}")
            continue
        html = r.text
        print(f"\nGET {path} -> {r.status_code}, {len(html)} caratteri, {r.headers.get('content-type')}")
        scripts = sorted(set(re.findall(r'<script[^>]+src="([^"]+)"', html)))
        print("  script:", scripts[:12])
        api = sorted(set(re.findall(r'["\'(](https?://[^"\'\s)]*(?:api|json|data\.ijf|judobase)[^"\'\s)]*)', html, re.I)))
        print("  url sospette (api/json/data):", api[:15])
        for parola in ("get_json", "contest.find", "id_competition", "window.__", "__NEXT_DATA__", "ajax"):
            for m in list(re.finditer(re.escape(parola), html))[:2]:
                a, b = max(0, m.start() - 150), min(len(html), m.end() + 250)
                print(f"  '{parola}' ->", html[a:b].replace("\n", " "))
        # righe con 'contest' o nomi di round
        for parola in ("Final", "Repechage", "Round of", "Ippon", "ippon", "waza"):
            n = html.count(parola)
            if n:
                print(f"  la parola '{parola}' compare {n} volte")
        if "contests" in path:
            testo = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
            testo = re.sub(r"<[^>]+>", " ", testo)
            testo = re.sub(r"\s+", " ", testo)
            print("  testo visibile (primi 1500):", testo[:1500])


def parte2_browser():
    print("\n=================== PARTE 2: browser (rete osservata) ===================")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("playwright non disponibile:", e)
        return
    visti = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(user_agent=UA, locale="en-US")
        page = ctx.new_page()

        def on_resp(resp):
            try:
                ct = resp.headers.get("content-type", "")
                u = resp.url
                if resp.request.resource_type in ("xhr", "fetch") or "json" in ct:
                    visti.append((resp.status, ct, u, resp))
            except Exception:
                pass

        page.on("response", on_resp)
        for path in (f"/competition/{COMP}/contests", f"/competition/{COMP}/draw"):
            visti.clear()
            print(f"\n--- apro {path}")
            try:
                page.goto(BASE + path, wait_until="networkidle", timeout=90000)
                page.wait_for_timeout(4000)
            except Exception as e:
                print("   errore apertura:", e)
            print("   titolo:", page.title())
            print(f"   richieste dati osservate: {len(visti)}")
            for st, ct, u, resp in visti[:25]:
                print(f"   {st} {ct[:30]:30} {u[:200]}")
            for st, ct, u, resp in visti:
                if "json" in ct and not any(x in u for x in ("google", "analytics", "facebook")):
                    try:
                        corpo = resp.text()
                    except Exception:
                        continue
                    print(f"\n   >>> JSON da {u[:200]} ({len(corpo)} caratteri)")
                    print("   ", corpo[:1800].replace("\n", " "))
                    break
            # testo visibile dopo il caricamento
            try:
                t = page.inner_text("body")
                t = re.sub(r"\s+", " ", t)
                print("   testo visibile (primi 1200):", t[:1200])
            except Exception as e:
                print("   testo non letto:", e)
        # prova a cliccare un filtro di peso (-60) se esiste
        try:
            page.goto(BASE + f"/competition/{COMP}/contests", wait_until="networkidle", timeout=90000)
            link = page.locator("text=-60").first
            if link.count():
                visti.clear()
                link.click()
                page.wait_for_timeout(5000)
                print("\n--- dopo il clic su '-60': richieste osservate", len(visti))
                for st, ct, u, resp in visti[:15]:
                    print(f"   {st} {ct[:30]:30} {u[:220]}")
                t = re.sub(r"\s+", " ", page.inner_text("body"))
                print("   testo visibile (primi 1800):", t[:1800])
        except Exception as e:
            print("   (clic non riuscito)", e)
        b.close()


def parte3_api_note():
    print("\n=================== PARTE 3: prove su interfacce dati note ===================")
    prove = [
        "https://data.ijf.org/api/get_json?params[action]=contest.find&params[id_competition]=%d&params[id_weight]=1&params[limit]=3" % COMP,
        "https://data.ijf.org/api/get_json?params[action]=competition.info&params[id_competition]=%d" % COMP,
        "https://judobase.ijf.org/api/get_json?params[action]=contest.find&params[id_competition]=%d&params[limit]=3" % COMP,
        BASE + "/api/competition/%d" % COMP,
    ]
    for u in prove:
        try:
            r = S.get(u, timeout=45, headers={"Accept": "application/json"})
            print(f"GET {u[:150]} -> {r.status_code} {r.headers.get('content-type', '')[:30]} | {r.text[:700]!r}")
        except Exception as e:
            print(f"GET {u[:150]} -> errore {e}")


if __name__ == "__main__":
    for f in (parte1_requests, parte2_browser, parte3_api_note):
        try:
            f()
        except Exception:
            traceback.print_exc()
        sys.stdout.flush()
    print("\nFine esplorazione.")
