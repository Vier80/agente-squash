"""Diagnosi Fencing Time Live (stesso nome file del programma di esplorazione precedente).

Apre la pagina indicata, registra le richieste dati che fa il sito, stampa la struttura
della pagina (titoli, tabelle, link, esempi di righe) e prova a leggere la pagina anche
senza browser. Non scrive nulla da nessuna parte.
"""
import json
import os
import re
import sys
import traceback

from playwright.sync_api import sync_playwright

URL = os.getenv("PAGE_URL", "").strip()
if not URL:
    sys.exit("Manca l'indirizzo della pagina (PAGE_URL).")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
risposte = []


def riduci(v, livello=0):
    if livello > 6:
        return "..."
    if isinstance(v, dict):
        voci = list(v.items())
        out = {k: riduci(x, livello + 1) for k, x in voci[:30]}
        if len(voci) > 30:
            out["..."] = f"(+{len(voci) - 30} chiavi)"
        return out
    if isinstance(v, list):
        out = [riduci(x, livello + 1) for x in v[:2]]
        if len(v) > 2:
            out.append(f"... (totale {len(v)} elementi)")
        return out
    if isinstance(v, str):
        return v if len(v) <= 80 else v[:80] + "…"
    return v


def mostra_corpo(testo, ctype):
    testo = testo or ""
    s = testo.strip()
    if s[:1] in "{[":
        try:
            print("    JSON ridotto:", json.dumps(riduci(json.loads(s)), ensure_ascii=False)[:2500])
            return
        except Exception:
            pass
    print("    inizio:", re.sub(r"\s+", " ", s[:700]))


def on_response(resp):
    try:
        req = resp.request
        ct = resp.headers.get("content-type", "")
        if req.resource_type in ("image", "font", "stylesheet", "media"):
            return
        corpo = ""
        try:
            corpo = resp.text()
        except Exception:
            pass
        risposte.append((req.method, resp.status, req.resource_type, ct, resp.url, corpo, req.post_data or ""))
    except Exception:
        pass


def prova_senza_browser(ctx, url, etichetta):
    try:
        r = ctx.get(url, headers={"User-Agent": UA}, timeout=30000)
        corpo = r.text()
        if etichetta == "pagina":
            cerca_nel_codice(corpo)
        print(f"[{etichetta}] {url[:140]}")
        print(f"    stato {r.status}, tipo {r.headers.get('content-type', '?')}, {len(corpo)} caratteri, "
              f"<tr>: {corpo.count('<tr')}, <table>: {corpo.count('<table')}")
        mostra_corpo(corpo, r.headers.get("content-type", ""))
    except Exception as e:
        print(f"[{etichetta}] errore: {e}")


def cerca_nel_codice(html):
    print("\n--- Ricerca di parole chiave nel codice grezzo della pagina ---")
    print("dimensione:", len(html), "caratteri")
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        print("dati incorporati (__NUXT_DATA__):", len(m.group(1)), "caratteri; inizio:",
              re.sub(r"\s+", " ", m.group(1)[:600]))
    for parola in ("tableau", "bracket", "table of", "pool", "bout", "winner", "score", "api/competition", "api/"):
        pos = [x.start() for x in re.finditer(re.escape(parola), html, re.I)]
        print(f"'{parola}': {len(pos)} volte")
        for i in pos[:2]:
            print("    ...", re.sub(r"\s+", " ", html[max(0, i - 100): i + 160]))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1400, "height": 2000})
        print("=== A. Lettura semplice, senza browser ===")
        prova_senza_browser(ctx.request, URL, "pagina")
        prova_senza_browser(ctx.request, URL.rstrip("/") + "/data", "pagina + /data")

        print("\n=== B. Pagina aperta nel browser ===")
        page = ctx.new_page()
        page.on("response", on_response)
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(12000)
        print("Titolo:", page.title())
        for tag in ("h1", "h2", "h3"):
            testi = [t.strip() for t in page.locator(tag).all_inner_texts() if t.strip()]
            print(f"{tag}:", testi[:8])

        print("\n--- Testo visibile (primi 3000 caratteri) ---")
        print(re.sub(r"[ \t]+", " ", page.inner_text("body"))[:3000])

        print("\n--- Tabelle ---")
        n_tab = page.locator("table").count()
        print("tabelle:", n_tab, "| righe <tr>:", page.locator("tr").count())
        for i in range(min(n_tab, 3)):
            righe = page.locator("table").nth(i).locator("tr")
            print(f"tabella {i + 1}: {righe.count()} righe")
            for j in range(min(righe.count(), 4)):
                print("   ", re.sub(r"\s+", " ", righe.nth(j).inner_text())[:200])
        if page.locator("tr").count():
            print("\nHTML della 2a riga:")
            print(re.sub(r"\s+", " ", page.locator("tr").nth(1).evaluate("e => e.outerHTML"))[:1500])

        print("\n--- Link utili (eventi, gironi, tabelloni) ---")
        visti = set()
        for a in page.locator("a").all():
            try:
                href = a.get_attribute("href") or ""
                if re.search(r"tableau|pool|event|tournament|result", href, re.I) and href not in visti:
                    visti.add(href)
                    print("  ", href[:150], "|", re.sub(r"\s+", " ", a.inner_text())[:60])
                    if len(visti) >= 30:
                        break
            except Exception:
                pass


        print("\n--- Schede e pulsanti nella pagina ---")
        voci = []
        for sel in ("[role=tab]", "button", "a"):
            for el in page.locator(sel).all():
                try:
                    t = re.sub(r"\s+", " ", el.inner_text()).strip()
                    if t and len(t) < 40 and t not in voci:
                        voci.append(t)
                except Exception:
                    pass
        print(voci[:60])
        for nome in ("Table", "Tableau", "Elimination", "Bracket", "Pools", "Poules", "Bouts"):
            try:
                loc = page.get_by_text(re.compile(rf"^\s*{nome}", re.I)).first
                if loc.count() == 0:
                    continue
                prima = len(risposte)
                loc.click(timeout=5000)
                page.wait_for_timeout(6000)
                print(f"\n=== Dopo il clic su '{nome}' === indirizzo: {page.url}")
                print(re.sub(r"[ \t]+", " ", page.inner_text("body"))[:2500])
                for m, st, rt, ct, url, corpo, post in risposte[prima:]:
                    if rt in ("xhr", "fetch") or "json" in ct:
                        print(f"  richiesta dati: {m} {st} {url[:160]}")
                        mostra_corpo(corpo, ct)
                break
            except Exception as e:
                print(f"clic su {nome} non riuscito: {e}")

        print(f"\n--- Richieste fatte dalla pagina: {len(risposte)} ---")
        for m, st, rt, ct, url, corpo, post in risposte[:40]:
            print(f"{m} {st} {rt} {ct[:40]} {len(corpo)} car. {url[:140]}" + (f" | inviato: {post[:80]}" if post else ""))
        print("\n--- Contenuto delle richieste dati (json / xhr / fetch) ---")
        n = 0
        for m, st, rt, ct, url, corpo, post in risposte:
            if rt in ("xhr", "fetch") or "json" in ct:
                n += 1
                print(f"\n[{n}] {m} {url[:160]}")
                mostra_corpo(corpo, ct)
                if n >= 6:
                    break
        if n == 0:
            print("Nessuna richiesta dati: i risultati sono probabilmente scritti direttamente nella pagina.")
        browser.close()


try:
    main()
except Exception:
    traceback.print_exc(limit=4, file=sys.stdout)
sys.stdout.flush()
os._exit(0)
