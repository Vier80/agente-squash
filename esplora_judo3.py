"""Esplorazione IJF, fase 3: da dove la pagina del ranking olimpico prende i dati.

Non scrive nulla da nessuna parte.
"""
import json
import re
import sys
import traceback

import requests

BASE = "https://www.ijf.org"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
PAGES = ["/wrl_olympic?category=all_male", "/wrl_olympic?category=all_female"]
SKIP = ("cookiebot", "google", "analytics", "facebook", "doubleclick", "sponsors")


def riduci(v, liv=0, n=3):
    if liv > 6:
        return "..."
    if isinstance(v, dict):
        return {k: riduci(x, liv + 1, n) for k, x in list(v.items())[:60]}
    if isinstance(v, list):
        out = [riduci(x, liv + 1, n) for x in v[:n]]
        if len(v) > n:
            out.append(f"... (totale {len(v)})")
        return out
    if isinstance(v, str):
        return v if len(v) <= 80 else v[:80] + "..."
    return v


def parte1_html():
    print("=================== PARTE 1: codice della pagina (requests) ===================")
    for path in PAGES[:1]:
        h = requests.get(BASE + path, headers={"User-Agent": UA}, timeout=60).text
        print(f"{path}: {len(h)} caratteri")
        for m in list(re.finditer(r"IJF\.\w+\(|wrl|id_weight|category|ranking_type|id_ranking", h))[:25]:
            a, b = max(0, m.start() - 120), min(len(h), m.end() + 220)
            print("   ...", h[a:b].replace("\n", " "))
        blocchi = re.findall(r"<script(?![^>]*src)[^>]*>(.*?)</script>", h, flags=re.S)
        for i, bl in enumerate(blocchi):
            if "wrl" in bl.lower() or "ranking" in bl.lower():
                print(f"\n--- script inline n.{i} ({len(bl)} caratteri):\n{bl[:2500]}")


def parte2_browser():
    print("\n=================== PARTE 2: browser (rete osservata) ===================")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(user_agent=UA, locale="en-US", viewport={"width": 1400, "height": 2200})
        page = ctx.new_page()
        visti = []

        def on_resp(resp):
            try:
                u = resp.url
                if any(s in u for s in SKIP):
                    return
                ct = resp.headers.get("content-type", "")
                if resp.request.resource_type in ("xhr", "fetch") or "json" in ct:
                    visti.append((resp.status, ct, u, resp))
            except Exception:
                pass

        page.on("response", on_resp)
        for path in PAGES:
            visti.clear()
            print(f"\n--- apro {path}")
            try:
                page.goto(BASE + path, wait_until="networkidle", timeout=90000)
                page.wait_for_timeout(6000)
            except Exception as e:
                print("   errore apertura:", e)
            print("   richieste dati:", len(visti))
            for st, ct, u, resp in visti:
                print(f"   {st} {ct[:28]:28} {u[:230]}")
            for st, ct, u, resp in visti:
                try:
                    corpo = resp.text()
                except Exception:
                    continue
                print(f"\n   >>> corpo di {u[:160]} ({len(corpo)} caratteri)")
                try:
                    j = json.loads(corpo)
                    print("   ", json.dumps(riduci(j), ensure_ascii=False)[:2500])
                except Exception:
                    print("   ", corpo[:1200].replace("\n", " "))
            t = re.sub(r"\s+", " ", page.inner_text("body"))
            print("\n   testo visibile (primi 1800):", t[:1800])
            # filtri / menu a tendina / link che cambiano categoria
            try:
                sel = page.eval_on_selector_all(
                    "select", "els => els.map(e => ({id: e.id, name: e.name, opts: Array.from(e.options).map(o => o.value + '=' + o.text).slice(0, 40)}))")
                print("\n   menu a tendina:", json.dumps(sel, ensure_ascii=False)[:2500])
            except Exception as e:
                print("   (select non letti)", e)
            try:
                links = page.eval_on_selector_all(
                    "a[href*='wrl'], button", "els => els.map(e => (e.getAttribute('href')||'') + ' | ' + (e.innerText||'').trim().slice(0,40)).slice(0, 80)")
                print("   link/bottoni:", links)
            except Exception as e:
                print("   (link non letti)", e)
        # prova a cambiare categoria con un clic su '-60' e su un continente, se esistono
        page.goto(BASE + PAGES[0], wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(5000)
        for etichetta in ("-60", "-66", "Europe", "Africa", "Asia", "Oceania", "Panamerica"):
            try:
                loc = page.locator(f"text={etichetta}").first
                if loc.count():
                    visti.clear()
                    loc.click(timeout=5000)
                    page.wait_for_timeout(4000)
                    print(f"\n--- dopo clic su '{etichetta}': {len(visti)} richieste")
                    for st, ct, u, resp in visti:
                        print(f"   {st} {u[:260]}")
                        try:
                            corpo = resp.text()
                            print("      corpo:", corpo[:700].replace("\n", " "))
                        except Exception:
                            pass
                else:
                    print(f"\n--- '{etichetta}': elemento non trovato")
            except Exception as e:
                print(f"\n--- '{etichetta}': clic non riuscito ({str(e)[:100]})")
        b.close()


def parte3_api():
    print("\n=================== PARTE 3: prove su interfacce note ===================")
    API = "https://data.ijf.org/api/get_json"
    azioni = ["wrl.by_category", "wrl.get", "wrl.list", "wrl.ranking", "ranking.get", "ranking.list",
              "wrl.get_ranking", "wrl.find", "wrl.get_list", "wrl.olympic"]
    for a in azioni:
        try:
            r = requests.get(API, params={"params[action]": a, "params[id_weight]": 1}, timeout=40,
                             headers={"User-Agent": UA})
            print(f"{a:20} -> {r.status_code} {r.text[:260]!r}")
        except Exception as e:
            print(f"{a:20} -> errore {e}")


if __name__ == "__main__":
    for f in (parte1_html, parte2_browser, parte3_api):
        try:
            f()
        except Exception:
            traceback.print_exc()
        sys.stdout.flush()
    print("\nFine esplorazione.")
