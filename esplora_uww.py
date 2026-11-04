"""Esplorazione UWW - versione 2.

Apre la pagina come un browser e stampa nel log i dettagli che servono per
costruire il lettore: com'e' fatto un incontro (HTML), i controlli per scegliere
stile e categoria di peso, le bandiere (NOC), il programma per date.
Non scrive nulla da nessuna parte. Ogni passaggio e' protetto.
"""
import os
import re
import sys
import traceback
import urllib.request

from playwright.sync_api import sync_playwright

URL = os.getenv("PAGE_URL", "").strip()
if not URL:
    sys.exit("Manca l'indirizzo della pagina (PAGE_URL).")


def passo(titolo, funzione):
    try:
        funzione()
    except Exception:
        print(f"\n--- Problema nel passaggio: {titolo} ---")
        traceback.print_exc(limit=2, file=sys.stdout)


def html_grezzo():
    print("\n=== 1. LA PAGINA 'GREZZA' (senza browser) CONTIENE I RISULTATI? ===")
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (compatible; AgenteWrestling/1.0)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="replace")
    print(f"Lunghezza pagina grezza: {len(html)} caratteri")
    for chiave in ["DINGASHVILI", "Dingashvili", "VPO1", "VSU1"]:
        print(f"  contiene '{chiave}': {chiave in html}")
    m = re.search(r".{200}VPO1.{200}", html, re.S)
    if m:
        print("  Esempio di contesto:", m.group(0).replace("\n", " "))


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 2000})

    def apri():
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)
        print("Pagina aperta.")

    def struttura_incontro():
        print("\n=== 2. STRUTTURA HTML DI UN INCONTRO ===")
        js = """
        () => {
          const re = /\\d+\\s*-\\s*\\d+[\\s\\S]*by\\s+V[A-Z0-9]+/;
          const all = Array.from(document.querySelectorAll('div, li, a, tr, section'));
          const hits = all.filter(el => re.test(el.innerText || ''));
          const leaf = hits.filter(el => !Array.from(el.children).some(c => re.test(c.innerText || '')));
          if (!leaf.length) return ['nessun incontro trovato'];
          let el = leaf[0];
          const out = [];
          for (let i = 0; i < 4 && el; i++) {
            out.push('LIVELLO ' + i + ' <' + el.tagName + '> ' + el.outerHTML.slice(0, 2500));
            el = el.parentElement;
          }
          return out;
        }
        """
        for riga in page.evaluate(js):
            print(riga)
            print("-----")

    def bandiere():
        print("\n=== 3. BANDIERE / NOC ===")
        js = """
        () => Array.from(document.querySelectorAll('img'))
          .filter(i => (i.src || '').includes('flag'))
          .slice(0, 12)
          .map(i => i.src + ' | alt=' + i.alt + ' | accanto: ' + (i.parentElement ? i.parentElement.innerText.slice(0, 60).replace(/\\n/g, ' / ') : ''))
        """
        for riga in page.evaluate(js):
            print(riga)

    def controlli():
        print("\n=== 4. CONTROLLI PER STILE E CATEGORIA DI PESO ===")
        js = """
        () => {
          const out = [];
          const re = /^(\\d+ kg|Freestyle|Greco[- ]Roman|Women.*)$/i;
          for (const el of document.querySelectorAll('a, button, li, span, div')) {
            if (el.children.length === 0 && re.test((el.innerText || '').trim())) {
              out.push(el.tagName + ' | testo=' + el.innerText.trim() + ' | href=' + (el.getAttribute('href') || (el.closest('a') ? el.closest('a').getAttribute('href') : '')) + ' | ' + el.outerHTML.slice(0, 220));
            }
          }
          return out.slice(0, 16);
        }
        """
        for riga in page.evaluate(js):
            print(riga)

    def programma():
        print("\n=== 5. SCHEDA 'Schedule' (programma per date) ===")
        page.get_by_text("Schedule", exact=True).first.click(timeout=10000)
        page.wait_for_timeout(8000)
        testo = page.inner_text("body", timeout=15000)
        inizio = testo.find("Schedule")
        print(testo[inizio:inizio + 3500])

    passo("pagina grezza", html_grezzo)
    passo("apertura", apri)
    passo("struttura incontro", struttura_incontro)
    passo("bandiere", bandiere)
    passo("controlli stile/peso", controlli)
    passo("programma", programma)
    browser.close()
