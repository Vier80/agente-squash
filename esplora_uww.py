"""Esplorazione di una pagina UWW.

Apre la pagina come farebbe un browser vero, prova a cliccare la scheda
"Results" e stampa nel log: il testo visibile, gli eventuali link a PDF e le
richieste di dati (JSON/API) fatte dalla pagina. Non scrive nulla da nessuna parte.
Ogni passaggio e' protetto: anche se uno fallisce, il log mostra quello che e' stato trovato.
"""
import os
import sys
import traceback

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


def passo(titolo, funzione):
    try:
        funzione()
    except Exception:
        print(f"\n--- Problema nel passaggio: {titolo} ---")
        traceback.print_exc(limit=2, file=sys.stdout)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 2000})
    page.on("response", on_response)

    def apri():
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)
        print("Pagina aperta.")

    def testo_prima():
        print("\n=== TESTO VISIBILE PRIMA DEL CLIC (primi 2500 caratteri) ===")
        print(page.inner_text("body", timeout=15000)[:2500])

    def clic_results():
        page.get_by_text("Results", exact=True).first.click(timeout=10000)
        page.wait_for_timeout(10000)
        print("\n=== TESTO VISIBILE DOPO IL CLIC SU 'Results' (primi 4000 caratteri) ===")
        print(page.inner_text("body", timeout=15000)[:4000])

    def link_pdf():
        print("\n=== LINK A PDF ===")
        for a in page.query_selector_all("a[href*='.pdf']"):
            print(a.get_attribute("href"))

    passo("apertura della pagina", apri)
    passo("lettura del testo", testo_prima)
    passo("clic su Results", clic_results)
    passo("ricerca link PDF", link_pdf)

    print("\n=== RICHIESTE DI DATI (JSON/API) ===")
    for stato, metodo, url, size, anteprima in richieste[:40]:
        print(f"{stato} {metodo} {url} ({size} caratteri)\n    {anteprima}")
    print(f"\n(Totale richieste dati registrate: {len(richieste)})")

    browser.close()
