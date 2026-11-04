"""Diagnosi UWW - versione 3.

Obiettivo: capire perche' alcune categorie di peso risultano vuote. Apre la pagina,
poi clicca alcune categorie e, per ciascuna, stampa: quante partite e quanti atleti
vede, l'inizio del testo mostrato, e le richieste di rete fatte dalla pagina
(escluse pubblicita' e statistiche). Non scrive nulla da nessuna parte.
"""
import os
import re
import sys
import traceback

from playwright.sync_api import sync_playwright

URL = os.getenv("PAGE_URL", "").strip()
if not URL:
    sys.exit("Manca l'indirizzo della pagina (PAGE_URL).")

IGNORA = ("doubleclick", "google", "tiktok", "wonderpush", "sentry", "facebook",
          "adtraffic", "monitoring", "gstatic", "clarity", "hotjar")
WEIGHT_RE = re.compile(r"^\s*\d+\s*kg\s*$", re.I)
richieste = []


def on_response(resp):
    try:
        url = resp.url
        if any(x in url for x in IGNORA):
            return
        req = resp.request
        tipo = req.resource_type
        if tipo in ("image", "font", "stylesheet", "media", "script"):
            return
        ctype = resp.headers.get("content-type", "")
        body = ""
        try:
            body = resp.text()
        except Exception:
            pass
        richieste.append(
            f"{resp.status} {req.method} [{tipo}] {url[:160]}\n"
            f"      content-type={ctype} | dimensione={len(body)} | next-action={'si' if req.headers.get('next-action') else 'no'}\n"
            f"      invio: {(req.post_data or '')[:150]!r}\n"
            f"      risposta: {body[:200].replace(chr(10), ' ')!r}"
        )
    except Exception:
        pass


def stato(page, etichetta):
    print(f"\n########## {etichetta} ##########")
    try:
        attivo = page.locator("button[data-slot='button'][data-variant='default']").filter(has_text=WEIGHT_RE)
        print("Categoria evidenziata nei pulsanti:", [attivo.nth(i).inner_text().strip() for i in range(attivo.count())])
    except Exception as e:
        print("Pulsanti non leggibili:", e)
    try:
        print("Spans 'by ...' (incontri conclusi visibili):",
              page.locator("span", has_text=re.compile(r"^by\s+\S+$")).count())
        print("Link ad atleti:", page.locator("a[href^='/athletes/']").count())
        testo = page.inner_text("body", timeout=15000)
        i = testo.find("125 kg")
        if i < 0:
            i = testo.find("kg")
        print("Testo mostrato dopo i pulsanti dei pesi:")
        print(testo[i:i + 700] if i >= 0 else testo[:700])
    except Exception as e:
        print("Lettura pagina non riuscita:", e)
    print(f"--- Richieste di rete in questo passaggio: {len(richieste)} ---")
    for r in richieste[:12]:
        print(r)
    richieste.clear()


def clic_peso(page, kg):
    btn = page.locator("button[data-slot='button']").filter(has_text=WEIGHT_RE).filter(has_text=re.compile(rf"^\s*{kg}\s*kg\s*$"))
    btn.first.click(timeout=10000)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 2000})
    page.on("response", on_response)
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)
        stato(page, "A. Pagina appena aperta (57 kg)")
        for kg in (61, 65, 57, 74):
            try:
                clic_peso(page, kg)
                page.wait_for_timeout(12000)
                stato(page, f"B. Dopo il clic su {kg} kg (attesa 12 secondi)")
            except Exception:
                print(f"\n--- Problema con il clic su {kg} kg ---")
                traceback.print_exc(limit=2, file=sys.stdout)
        page.wait_for_timeout(10000)
        stato(page, "C. Altri 10 secondi dopo l'ultimo clic (arriva qualcosa in ritardo?)")
    except Exception:
        traceback.print_exc(limit=3, file=sys.stdout)
    browser.close()
