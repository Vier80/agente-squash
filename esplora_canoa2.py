"""Esplorazione mirata dell'interfaccia dati di ICF Rankings (/api/...), fase 2.

Non scrive nulla da nessuna parte: legge poche righe di esempio e stampa la struttura.
"""
import json
import traceback

import requests

BASE = "https://rankings.canoeicf.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json"})


def get(path, params=None):
    r = S.get(BASE + path, params=params, timeout=60)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:400]


def riduci(v, livello=0, prof=6, n=3):
    if livello > prof:
        return "..."
    if isinstance(v, dict):
        voci = list(v.items())
        out = {k: riduci(x, livello + 1, prof, n) for k, x in voci[:40]}
        if len(voci) > 40:
            out["..."] = f"(+{len(voci) - 40} chiavi)"
        return out
    if isinstance(v, list):
        out = [riduci(x, livello + 1, prof, n) for x in v[:n]]
        if len(v) > n:
            out.append(f"... (totale {len(v)})")
        return out
    if isinstance(v, str):
        return v if len(v) <= 60 else v[:60] + "..."
    return v


def show(titolo, params_path, params=None, prof=6, n=3, limite=3500):
    print(f"\n=== {titolo}\n    GET {params_path} {params or ''}")
    try:
        st, data = get(params_path, params)
    except Exception as e:
        print("    errore:", e)
        return None
    print("    stato", st)
    if isinstance(data, dict) and "docs" in data:
        print("    totalDocs:", data.get("totalDocs"), "| totalPages:", data.get("totalPages"),
              "| limit:", data.get("limit"))
    txt = json.dumps(riduci(data, 0, prof, n), ensure_ascii=False)
    print("   ", txt[:limite] + (" ...[tagliato]" if len(txt) > limite else ""))
    return data


def main():
    # 1. elenco delle specialita' (events)
    st, ev = get("/api/events", {"limit": 100, "depth": 0})
    print("=== EVENTI (events), stato", st)
    if isinstance(ev, dict):
        print("totalDocs:", ev.get("totalDocs"))
        for d in ev.get("docs", []):
            print(f"  {d.get('code'):6} | {d.get('name'):22} | {d.get('gender'):7} | {d.get('boatType'):5} "
                  f"| disc={d.get('discipline')} | id={d.get('id')}")
    # 2. una riga di classifica, grezza
    show("Riga di classifica grezza (depth=0)", "/api/ranking-entries", {"limit": 1, "depth": 0}, prof=8, n=4)
    # 3. quale collezione contiene le liste (rankingList)?
    for slug in ("ranking-lists", "rankinglists", "ranking-list", "rankings", "ranking-lists-oqr"):
        try:
            st, data = get(f"/api/{slug}", {"limit": 2, "depth": 0})
            print(f"\n--- /api/{slug} -> {st}",
                  json.dumps(riduci(data, 0, 4, 2), ensure_ascii=False)[:900])
        except Exception as e:
            print(f"--- /api/{slug} errore {e}")
    # 4. classifica filtrata per lista: sprint K1 uomini
    show("Prime 3 righe 'CSP MK1 OQR' (depth=0)", "/api/ranking-entries",
         {"where[rankingList.title][equals]": "CSP MK1 OQR", "sort": "rank", "limit": 3, "depth": 0}, prof=8, n=3)
    show("Prime 2 righe 'CSP MK1 OQR' (depth=3: dovrebbe mostrare equipaggi/atleti)", "/api/ranking-entries",
         {"where[rankingList.title][equals]": "CSP MK1 OQR", "sort": "rank", "limit": 2, "depth": 3},
         prof=9, n=2, limite=6000)
    show("Prime 2 righe 'CSP MK4 OQR' (depth=3)", "/api/ranking-entries",
         {"where[rankingList.title][equals]": "CSP MK4 OQR", "sort": "rank", "limit": 2, "depth": 3},
         prof=9, n=2, limite=6000)
    show("Prime 2 righe 'CSL MK1 OQR' (depth=1)", "/api/ranking-entries",
         {"where[rankingList.title][equals]": "CSL MK1 OQR", "sort": "rank", "limit": 2, "depth": 1},
         prof=7, n=2, limite=4000)
    # 5. titoli delle liste esistenti (campionando le righe)
    st, d = get("/api/ranking-entries", {"limit": 500, "depth": 1, "sort": "-updatedAt"})
    if isinstance(d, dict):
        titoli = {}
        for x in d.get("docs", []):
            rl = x.get("rankingList") or {}
            t = rl.get("title") if isinstance(rl, dict) else str(rl)
            titoli[t] = titoli.get(t, 0) + 1
        print("\n=== Liste trovate nelle ultime 500 righe:", titoli)
    # 6. competizioni 2026-2027 (nome, tipo, stato, date)
    st, c = get("/api/competitions", {"limit": 200, "depth": 0, "sort": "startDate"})
    print("\n=== COMPETIZIONI, stato", st)
    if isinstance(c, dict):
        print("totalDocs:", c.get("totalDocs"))
        for d in c.get("docs", []):
            if d.get("competitionType") in ("national-championship",):
                continue
            print(f"  {str(d.get('startDate'))[:10]} | {str(d.get('competitionType')):22} | "
                  f"{str(d.get('status')):10} | x{d.get('multiplier')} | {d.get('name')}")
    # 7. un risultato grezzo (collezione dei risultati)
    for slug in ("race-results", "results", "competition-results", "athlete-results", "crew-members"):
        try:
            st, data = get(f"/api/{slug}", {"limit": 1, "depth": 0})
            print(f"\n--- /api/{slug} -> {st}",
                  json.dumps(riduci(data, 0, 4, 2), ensure_ascii=False)[:700])
        except Exception as e:
            print(f"--- /api/{slug} errore {e}")
    print("\nFine esplorazione.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
