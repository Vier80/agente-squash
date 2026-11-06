"""Esplorazione del sito ranking di World Taekwondo (worldtkd.simplycompete.com).

Non scrive nulla da nessuna parte: apre la pagina del ranking in un browser, osserva da dove
arrivano i dati (le chiamate di rete), elenca i menu a tendina (tipo di ranking, categorie di peso)
e stampa un riassunto da incollare in chat.
"""
import json
import re
import sys
import traceback
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

BASE = "https://worldtkd.simplycompete.com"
URL = (BASE + "/playerRankingV2?limit=25&pageNo=1&month=10&year=2026"
       "&rankingCategoryId=11ef3918-68c6-28dd-8999-023374a4dcc1"
       "&subCategory1=11ef3918-30a6-2db9-8999-023374a4dcc1"
       "&rankingTypeId=11ef3916-58d3-484e-8999-023374a4dcc1")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def cut(s, n=1500):
    s = re.sub(r"\s+", " ", str(s))
    return s if len(s) <= n else s[:n] + " ...[taglio]"


def parte1_requests():
    print("=================== PARTE 1: pagina letta con requests ===================")
    try:
        r = requests.get(URL, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=45)
    except Exception as e:
        print("errore:", e)
        return
    html = r.text
    print(f"GET -> {r.status_code}, {len(html)} caratteri, {r.headers.get('content-type')}")
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
    print("script:", scripts[:15])
    print("testo grezzo (primi 600):", cut(re.sub(r"<[^>]+>", " ", html), 600))
    found = set()
    for src in scripts[:8]:
        u = src if src.startswith("http") else BASE + src
        try:
            js = requests.get(u, headers={"User-Agent": UA}, timeout=45).text
        except Exception as e:
            print("  script non letto:", u, e)
            continue
        for m in re.findall(r'["\'`](/?(?:api|rest|ranking|player)[A-Za-z0-9_/\-\.]*)["\'`?]', js):
            if len(m) > 4:
                found.add(m)
        for m in re.findall(r'["\'`]([A-Za-z0-9_/\-\.]*[Rr]anking[A-Za-z0-9_/\-\.]*)["\'`]', js):
            found.add(m)
    print("percorsi che sembrano API nei file JS (primi 60):", sorted(found)[:60])


def parte2_browser():
    print("\n=================== PARTE 2: browser (rete osservata) ===================")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("playwright non disponibile:", e)
        return None
    visti = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(user_agent=UA, locale="en-US", viewport={"width": 1500, "height": 1100})
        page = ctx.new_page()

        def on_resp(resp):
            try:
                req = resp.request
                if req.resource_type in ("xhr", "fetch"):
                    try:
                        body = resp.text()
                    except Exception:
                        body = ""
                    visti.append({"status": resp.status, "method": req.method, "url": resp.url,
                                  "post": req.post_data, "ct": resp.headers.get("content-type", ""),
                                  "body": body})
            except Exception:
                pass

        page.on("response", on_resp)
        try:
            page.goto(URL, wait_until="networkidle", timeout=90000)
        except Exception as e:
            print("goto:", e)
        page.wait_for_timeout(6000)
        print("titolo pagina:", page.title())
        print("indirizzo finale:", page.url)
        try:
            page.screenshot(path="tkd_ranking.png", full_page=True)
        except Exception as e:
            print("screenshot:", e)
        try:
            testo = page.inner_text("body")
        except Exception:
            testo = ""
        print("\n--- testo visibile (primi 2500 caratteri) ---")
        print(testo[:2500])

        print("\n--- chiamate di rete xhr/fetch ---")
        for v in visti:
            print(f"{v['status']} {v['method']} {v['url'][:260]}  [{v['ct'][:40]}, {len(v['body'])} car.]"
                  + (f" POST={cut(v['post'], 300)}" if v["post"] else ""))
        print("\n--- corpo delle risposte JSON più interessanti ---")
        n = 0
        for v in visti:
            if v["body"] and ("json" in v["ct"] or v["body"][:1] in ("[", "{")):
                if n >= 8:
                    break
                n += 1
                print(f"\n>>> {v['method']} {v['url'][:300]}")
                print(cut(v["body"], 1800))

        print("\n--- menu e filtri visibili ---")
        try:
            sel = page.evaluate("""() => [...document.querySelectorAll('select')].map(s => ({
                nome: s.name || s.id, opzioni: [...s.options].map(o => o.value + ' = ' + o.text).slice(0, 40)}))""")
            print("select:", json.dumps(sel, ensure_ascii=False)[:3000])
        except Exception as e:
            print("select:", e)
        try:
            cand = page.evaluate("""() => [...document.querySelectorAll(
                '[role=combobox],[aria-haspopup],mat-select,.MuiSelect-select,.ant-select,[class*=select i],[class*=dropdown i],[class*=filter i]')]
                .map(e => (e.className||'').toString().slice(0,60) + ' | ' + (e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,80)).slice(0,40)""")
            for c in cand:
                print("  filtro?:", c)
        except Exception as e:
            print("filtri:", e)
        try:
            links = page.evaluate("""() => [...document.querySelectorAll('a[href]')].map(a => a.href).filter(h => /ranking|player|athlete/i.test(h)).slice(0,25)""")
            print("link utili:", links)
        except Exception as e:
            print("link:", e)

        # apro i menu a tendina uno alla volta e leggo le voci
        print("\n--- voci dei menu (clic sui filtri) ---")
        try:
            handles = page.query_selector_all('[role=combobox],[aria-haspopup=listbox],mat-select,.MuiSelect-select,.ant-select-selector')
            print("filtri cliccabili trovati:", len(handles))
            for i, h in enumerate(handles[:8]):
                try:
                    etichetta = cut(h.inner_text(), 60)
                    h.click(timeout=4000)
                    page.wait_for_timeout(900)
                    voci = page.evaluate("""() => [...document.querySelectorAll('[role=option],mat-option,.MuiMenuItem-root,.ant-select-item-option,li[data-value]')]
                        .map(o => (o.getAttribute('data-value')||o.getAttribute('value')||'') + ' = ' + (o.innerText||'').trim().replace(/\\s+/g,' ')).slice(0,60)""")
                    print(f"[{i}] '{etichetta}' -> {voci}")
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(400)
                except Exception as e:
                    print(f"[{i}] errore: {cut(e, 150)}")
        except Exception as e:
            print("menu:", e)
        b.close()
    return visti


def parte3_prove_api(visti):
    print("\n=================== PARTE 3: prove sull'API trovata ===================")
    if not visti:
        print("niente da provare")
        return
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Referer": URL})
    prove = 0
    for v in visti:
        if v["method"] != "GET" or v["body"][:1] not in ("[", "{"):
            continue
        low = v["body"].lower()
        if "rank" not in low and "point" not in low:
            continue
        u = urlparse(v["url"])
        q = dict(parse_qsl(u.query))
        print(f"\nAPI candidata: {v['url'][:300]}")
        for var in ({}, {"limit": "500"}, {"limit": "100", "pageNo": "2"}, {"limit": "100", "page": "2"}):
            qq = dict(q)
            qq.update({k: val for k, val in var.items() if (k in q or k == "limit")})
            url = urlunparse(u._replace(query=urlencode(qq)))
            try:
                r = s.get(url, timeout=45)
                d = r.json()
                if isinstance(d, dict):
                    chiavi = {k: (len(val) if isinstance(val, list) else type(val).__name__) for k, val in d.items()}
                else:
                    chiavi = f"lista di {len(d)}"
                print(f"  {var or 'originale'} -> {r.status_code}, struttura: {chiavi}")
            except Exception as e:
                print(f"  {var or 'originale'} -> errore {cut(e, 150)}")
        prove += 1
        if prove >= 3:
            break


if __name__ == "__main__":
    for f in (parte1_requests,):
        try:
            f()
        except Exception:
            traceback.print_exc()
    visti = None
    try:
        visti = parte2_browser()
    except Exception:
        traceback.print_exc()
    try:
        parte3_prove_api(visti)
    except Exception:
        traceback.print_exc()
    print("\nEsplorazione terminata.")
    sys.stdout.flush()
