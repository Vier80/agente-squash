"""Esplorazione di una pagina UWW.

Apre la pagina come farebbe un browser vero, prova a cliccare la scheda
"Results" e stampa nel log: il testo visibile, gli eventuali link a PDF e le
richieste di dati (JSON/API) fatte dalla pagina. Non scrive nulla da nessuna parte.
"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = os.getenv("PAGE_URL", "").strip()
if not URL:
    sys.exit("Manca l'indirizzo della pagina (PAGE_URL).")

richieste = []


def on_response(resp):
    try:
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype or "/api/" in resp.url or "graphql" in resp.url:
            try:
                body = resp.text()
            except Exception:
                body = ""
            richieste.append((resp.status, resp.request.method, resp.url, len(body),
                              body[:300].replace("\n", " ")))
    except Exception:
        pass


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 2000})
    page.on("response", on_response)
    page.goto(URL, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(5000)

    print("=== TESTO VISIBILE PRIMA DEL CLIC (primi 2500 caratteri) ===")
    print(page.inner_text("body")[:2500])

    try:
        page.get_by_text("Results", exact=True).first.click(timeout=8000)
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(5000)
        print("\n=== TESTO VISIBILE DOPO IL CLIC SU 'Results' (primi 4000 caratteri) ===")
        print(page.inner_text("body")[:4000])
    except Exception as e:
        print(f"\nNon sono riuscito a cliccare 'Results': {e}")

    print("\n=== LINK A PDF ===")
    for a in page.query_selector_all("a[href*='.pdf']"):
        print(a.get_attribute("href"))

    print("\n=== RICHIESTE DI DATI (JSON/API) ===")
    for stato, metodo, url, size, anteprima in richieste[:40]:
        print(f"{stato} {metodo} {url} ({size} caratteri)\n    {anteprima}")

    browser.close()
