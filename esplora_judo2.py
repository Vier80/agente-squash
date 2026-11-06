"""Esplorazione IJF, fase 2: formato esatto dei dati (incontri, nomi, nazioni, calendario).

Non scrive nulla da nessuna parte.
"""
import json
import re
import traceback

import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json"})
API = "https://data.ijf.org/api/get_json"
COMP = 3151


def api(**p):
    params = {f"params[{k}]": v for k, v in p.items()}
    r = S.get(API, params=params, timeout=60)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:500]


def riduci(v, liv=0, n=3):
    if liv > 5:
        return "..."
    if isinstance(v, dict):
        return {k: riduci(x, liv + 1, n) for k, x in list(v.items())[:80]}
    if isinstance(v, list):
        out = [riduci(x, liv + 1, n) for x in v[:n]]
        if len(v) > n:
            out.append(f"... (totale {len(v)})")
        return out
    if isinstance(v, str):
        return v if len(v) <= 80 else v[:80] + "..."
    return v


def stampa(titolo, dato, n=2, limite=3500):
    t = json.dumps(riduci(dato, 0, n), ensure_ascii=False)
    print(f"\n=== {titolo}\n{t[:limite]}{' ...[tagliato]' if len(t) > limite else ''}")


def main():
    # 1. incontri: tutte le chiavi di un incontro completo
    st, d = api(action="contest.find", id_competition=COMP, id_weight=1, limit=200)
    print("contest.find stato", st)
    if isinstance(d, dict):
        c = d.get("contests", [])
        print("numero incontri -60 kg:", len(c), "| chiavi dell'oggetto:", list(d.keys()))
        if c:
            print("CHIAVI incontro:", list(c[0].keys()))
            stampa("Primo incontro completo (ordine API)", c[0], n=3, limite=5000)
            fin = [x for x in c if "Final" in str(x.get("round_name")) and "Semi" not in str(x.get("round_name"))
                   and "Quarter" not in str(x.get("round_name"))]
            if fin:
                stampa("Un incontro di finale/bronzo", fin[0], n=3, limite=5000)
            print("\nround_name presenti:", sorted({str(x.get("round_name")) for x in c}))
            print("round_code presenti:", sorted({str(x.get("round_code")) for x in c})[:25])
            print("valori 'type':", sorted({str(x.get("type")) for x in c}), "| 'bye':", sorted({str(x.get('bye')) for x in c}))
    # 2. stesso incontro via www.ijf.org/internal_api
    try:
        r = S.get(f"https://www.ijf.org/internal_api/contests?id_competition={COMP}&id_weight=1", timeout=60)
        j = r.json()
        print("\ninternal_api/contests stato", r.status_code, type(j).__name__)
        if isinstance(j, dict):
            print("chiavi:", list(j.keys())[:10])
            for k, v in j.items():
                if isinstance(v, list) and v:
                    print("elenco", k, "n =", len(v), "chiavi primo:", list(v[0].keys()) if isinstance(v[0], dict) else v[0])
                    stampa("primo elemento", v[0], n=3, limite=4500)
                    break
        elif isinstance(j, list) and j:
            print("n =", len(j), "chiavi primo:", list(j[0].keys()))
            stampa("primo elemento", j[0], n=3, limite=4500)
    except Exception:
        traceback.print_exc(limit=2)
    # 3. categorie di peso: id_weight 1..16
    print("\n=== Categorie di peso (id_weight -> nome, genere, numero incontri)")
    for w in range(1, 17):
        st, d = api(action="contest.find", id_competition=COMP, id_weight=w, limit=1)
        c = d.get("contests", []) if isinstance(d, dict) else []
        if c:
            x = c[0]
            print(w, {k: x.get(k) for k in x if "weight" in k or "gender" in k or "sex" in k or k in ("contest_code_long",)})
        else:
            print(w, "nessun incontro", st)
    # 4. competition.info completo
    st, d = api(action="competition.info", id_competition=COMP)
    stampa("competition.info completo", d, n=3, limite=4500)
    # 5. elenco competizioni: prove di azioni
    for act in ("competition.find", "competition.get_list", "competition.list", "competitions.find"):
        st, d = api(action=act, year=2026, limit=3)
        print(f"\n--- {act} -> {st}:", json.dumps(riduci(d, 0, 2), ensure_ascii=False)[:700])
    # 6. calendario: la variabile 'events' dentro la pagina
    for url in ("https://www.ijf.org/calendar?age=sen&year=2026", "https://www.ijf.org/calendar?age=sen&year=2027"):
        h = requests.get(url, headers={"User-Agent": UA}, timeout=60).text
        print(f"\n=== {url}: {len(h)} caratteri")
        for m in list(re.finditer(r"(?:let|var|const)\s+events\s*=", h))[:2]:
            print("   ...", h[m.start():m.start() + 1500].replace("\n", " "))
        ids = sorted(set(re.findall(r"/competition/(\d+)", h)))
        print("   id competizioni citati:", ids[:80])
        print("   link competizione con nome:",
              re.findall(r'href="/competition/(\d+)[^"]*"[^>]*>\s*([^<]{5,90})<', h)[:40])
    # 7. un campione dei dati atleta (se presenti nell'incontro) - cerca nomi
    st, d = api(action="contest.find", id_competition=COMP, id_weight=1, limit=2,
                part="info,score_list,media,sound,full_info")
    stampa("contest.find con part=...", d, n=2, limite=3500)
    print("\nFine esplorazione.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
