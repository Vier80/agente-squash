"""Diagnosi UWW - versione 4.

Dal test precedente risulta che la pagina scarica i risultati di ogni categoria con
una richiesta dati (text/x-component). Questo programma intercetta quella risposta,
la legge come dati strutturati e stampa nel log: la struttura (ridotta), un esempio di
incontro, e dove compaiono eventuali date. Non scrive nulla da nessuna parte.
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

catture = []


def on_response(resp):
    try:
        req = resp.request
        if req.method != "POST" or not req.headers.get("next-action"):
            return
        catture.append({"url": resp.url, "invio": req.post_data or "", "corpo": resp.text()})
    except Exception:
        pass


def riduci(v, livello=0):
    """Versione compatta di una struttura: liste a 2 elementi, testi corti."""
    if livello > 7:
        return "..."
    if isinstance(v, dict):
        voci = list(v.items())
        out = {k: riduci(x, livello + 1) for k, x in voci[:25]}
        if len(voci) > 25:
            out["..."] = f"(+{len(voci) - 25} chiavi)"
        return out
    if isinstance(v, list):
        out = [riduci(x, livello + 1) for x in v[:2]]
        if len(v) > 2:
            out.append(f"... (totale {len(v)} elementi)")
        return out
    if isinstance(v, str):
        return v if len(v) <= 70 else v[:70] + "…"
    return v


def cammina(nodo, percorso, visita):
    visita(nodo, percorso)
    if isinstance(nodo, dict):
        for k, v in nodo.items():
            cammina(v, percorso + [str(k)], visita)
    elif isinstance(nodo, list):
        for i, v in enumerate(nodo):
            cammina(v, percorso + [str(i)], visita)


def analizza(c, needle):
    corpo = c["corpo"]
    print(f"Indirizzo: {c['url'][:150]}")
    print(f"Dati inviati: {c['invio'][:200]}")
    print(f"Dimensione risposta: {len(corpo)} caratteri")
    alberi = []
    for riga in corpo.split("\n"):
        m = re.match(r"^([0-9a-zA-Z]+):(.*)$", riga, re.S)
        if not m:
            continue
        idr, payload = m.groups()
        try:
            obj = json.loads(payload)
        except Exception:
            print(f"  riga {idr}: non JSON ({len(payload)} caratteri), inizio={payload[:80]!r}")
            continue
        alberi.append((idr, obj))
        print(f"  riga {idr}: JSON {type(obj).__name__}, {len(payload)} caratteri")

    print("\n--- Struttura ridotta (prime 3500 lettere per riga) ---")
    for idr, obj in alberi:
        print(f"[riga {idr}] " + json.dumps(riduci(obj), ensure_ascii=False)[:3500])

    candidati, date = [], []

    def visita(n, p):
        if isinstance(n, dict):
            s = json.dumps(n, ensure_ascii=False)
            if needle in s.upper() and len(s) <= 4000:
                candidati.append((len(s), p, n))
        elif isinstance(n, str) and re.search(r"\b20\d\d-\d\d-\d\d", n) and len(date) < 6:
            date.append(("/".join(p), n[:40]))

    for idr, obj in alberi:
        cammina(obj, [f"riga{idr}"], visita)

    print(f"\n--- Dove compare '{needle}' ---")
    if candidati:
        grande = max(candidati, key=lambda x: x[0])
        piccoli = [x for x in candidati if len(x[2]) >= 3]
        piccolo = min(piccoli, key=lambda x: x[0]) if piccoli else None
        print("Struttura piu' ampia (probabile incontro):", "/".join(grande[1]))
        print(json.dumps(riduci(grande[2]), ensure_ascii=False)[:2500])
        if piccolo and piccolo is not grande:
            print("\nStruttura piu' piccola (probabile atleta):", "/".join(piccolo[1]))
            print(json.dumps(riduci(piccolo[2]), ensure_ascii=False)[:1200])
    else:
        print("Non trovato nei dati strutturati.")

    print("\n--- Valori che sembrano date ---")
    if date:
        for percorso, valore in date:
            print(f"{percorso} = {valore}")
    else:
        print("Nessuna data trovata nei dati.")


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 2000})
    page.on("response", on_response)
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(12000)
        print(f"=== A. Dati ricevuti all'apertura della pagina (57 kg) === richieste registrate: {len(catture)}")
        if catture:
            analizza(catture[0], "DINGASHVILI")
        prima = len(catture)
        page.locator("button[data-slot='button']").filter(
            has_text=re.compile(r"^\s*61\s*kg\s*$")).first.click(timeout=10000)
        page.wait_for_timeout(10000)
        print(f"\n\n=== B. Dati ricevuti dopo il clic su 61 kg === nuove richieste: {len(catture) - prima}")
        if len(catture) > prima:
            analizza(catture[-1], "AITAKYN")
    except Exception:
        traceback.print_exc(limit=3, file=sys.stdout)
    browser.close()
