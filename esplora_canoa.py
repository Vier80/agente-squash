"""Esplorazione del sito ICF Rankings (rankings.canoeicf.com) per l'agente canoa LA28.

Non scrive nulla da nessuna parte: scarica alcune pagine, guarda i dati che il sito
nasconde dentro la pagina (Next.js), prova le interfacce dati (/api/...) e stampa
un riassunto da incollare in chat.
"""
import json
import re
import traceback

import requests

BASE = "https://rankings.canoeicf.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
PAGES = ["/sprint/mk1", "/sprint/wk4", "/slalom", "/slalom/mk1", "/slalom/wc1", "/athletes",
         "/noc/por", "/road-to-la28"]
API_TRY = ["/api", "/api/athletes?limit=2", "/api/results?limit=2", "/api/rankings?limit=2",
           "/api/nocs?limit=2", "/api/events?limit=2", "/api/competitions?limit=2",
           "/api/quotas?limit=2", "/api/ranking-entries?limit=2", "/api/entries?limit=2",
           "/api/disciplines?limit=2", "/api/countries?limit=2"]
NAMES = ["Gennaro", "Trav", "Clarke", "Fox", "Pankova", "Funk", "Szeged", "Brandenburg", "World Cup"]

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "en"})


def get(path, **kw):
    url = path if path.startswith("http") else BASE + path
    return S.get(url, timeout=40, **kw)


def riduci(v, livello=0):
    if livello > 5:
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
        return v if len(v) <= 70 else v[:70] + "..."
    return v


def payload_rsc(html):
    """Ricompone i dati che Next.js incorpora nella pagina (self.__next_f.push([1,"..."]))."""
    pezzi = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html):
        try:
            pezzi.append(json.loads('"' + m.group(1) + '"'))
        except Exception:
            pass
    return "".join(pezzi)


def oggetti_json(testo):
    """Prova a leggere come JSON ogni riga del tipo 'id:[...]' o 'id:{...}' del payload."""
    out = []
    for riga in testo.split("\n"):
        m = re.match(r"^[0-9a-f]+:([\[{].*)$", riga)
        if not m:
            continue
        try:
            out.append(json.loads(m.group(1)))
        except Exception:
            continue
    return out


def cammina(v, visita):
    if isinstance(v, dict):
        visita(v)
        for x in v.values():
            cammina(x, visita)
    elif isinstance(v, list):
        for x in v:
            cammina(x, visita)


def firme_con_chiavi(oggetti, parole):
    """Raggruppa i dizionari che hanno chiavi contenenti una delle parole: firma -> (conteggio, esempio)."""
    firme = {}

    def visita(d):
        ks = list(d.keys())
        if any(any(p in k.lower() for p in parole) for k in ks):
            firma = tuple(sorted(ks))
            n, es = firme.get(firma, (0, None))
            firme[firma] = (n + 1, es or d)

    for o in oggetti:
        cammina(o, visita)
    return firme


def contesti(testo, parola, quanti=2, raggio=350):
    out = []
    for m in re.finditer(re.escape(parola), testo):
        a, b = max(0, m.start() - raggio), min(len(testo), m.end() + raggio)
        out.append(testo[a:b].replace("\n", " "))
        if len(out) >= quanti:
            break
    return out


def esamina_pagina(path):
    print(f"\n=================== {path} ===================")
    r = get(path)
    html = r.text
    print(f"stato {r.status_code}, {len(html)} caratteri, tipo {r.headers.get('content-type')}")
    for frase in ("No ranking data available", "0 athletes"):
        if frase in html:
            print(f"   la pagina contiene: '{frase}'")
    testo = payload_rsc(html)
    print(f"payload Next.js incorporato: {len(testo)} caratteri")
    if not testo:
        return html, ""
    oggetti = oggetti_json(testo)
    print(f"righe di dati leggibili come JSON: {len(oggetti)}")
    firme = firme_con_chiavi(oggetti, ["point", "athlete", "rank", "quota", "result"])
    print(f"tipi di oggetto con chiavi rilevanti: {len(firme)}")
    for firma, (n, es) in sorted(firme.items(), key=lambda x: -x[1][0])[:8]:
        print(f"  - {n} oggetti con chiavi {list(firma)[:30]}")
        print("      esempio:", json.dumps(riduci(es), ensure_ascii=False)[:900])
    for p in NAMES:
        if p in testo:
            print(f"  parola '{p}' presente nel payload, contesto:")
            for c in contesti(testo, p, 1):
                print("     ...", c[:700])
    return html, testo


def cerca_api_nel_codice(html):
    """Scarica i file JavaScript della pagina e cerca le chiamate a /api/..."""
    print("\n=================== Interfacce /api citate nel codice ===================")
    script = sorted(set(re.findall(r'/_next/static/chunks/[^"\'\s>]+\.js', html)))
    print(f"file JavaScript trovati: {len(script)}")
    trovate = {}
    for s in script[:60]:
        try:
            js = get(s).text
        except Exception:
            continue
        for m in re.finditer(r'["\'`](/api/[A-Za-z0-9_\-/\.\?=&${}]*)', js):
            trovate.setdefault(m.group(1), s)
        for m in re.finditer(r'fetch\(([^)]{0,160})\)', js):
            if "api" in m.group(1):
                trovate.setdefault("fetch(" + m.group(1)[:120] + ")", s)
    for k, v in sorted(trovate.items())[:60]:
        print("  ", k, " <-", v[-24:])
    html_api = sorted(set(re.findall(r'["\'](/api/[A-Za-z0-9_\-/\.\?=&]*)', html)))
    print("citate nell'HTML:", html_api[:30])


def prova_api():
    print("\n=================== Prove di interfacce /api ===================")
    for p in API_TRY:
        try:
            r = get(p, headers={"Accept": "application/json"})
            corpo = r.text[:500].replace("\n", " ")
            print(f"GET {p} -> {r.status_code} {r.headers.get('content-type', '')} | {corpo}")
        except Exception as e:
            print(f"GET {p} -> errore {e}")


def main():
    htmls = {}
    for p in PAGES:
        try:
            htmls[p] = esamina_pagina(p)
        except Exception:
            print(f"\n(errore su {p})")
            traceback.print_exc(limit=2)
    base_html = (htmls.get("/sprint/mk1") or (None, ""))[0] or (htmls.get("/slalom") or (None, ""))[0]
    if base_html:
        try:
            cerca_api_nel_codice(base_html)
        except Exception:
            traceback.print_exc(limit=2)
    prova_api()
    print("\nFine esplorazione.")


if __name__ == "__main__":
    main()
