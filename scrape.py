"""Agente Squash

Legge i risultati dei tornei PSA elencati in tornei.txt e li scrive in un
database Notion. Variabili necessarie: NOTION_TOKEN e NOTION_DATABASE_ID.
Se DRY_RUN=true fa solo una prova: stampa i dati trovati senza scrivere su Notion.
"""
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()
_raw_id = os.getenv("NOTION_DATABASE_ID", "").strip().replace("-", "")
_found = re.search(r"[0-9a-fA-F]{32}", _raw_id)
DATABASE_ID = _found.group(0) if _found else _raw_id
DRY_RUN = os.getenv("DRY_RUN", "").strip().lower() == "true"

GAMES_TO_WIN = 3       # partite al meglio dei 5 game
PAUSE_SECONDS = 1.5    # pausa tra una richiesta e l'altra ai siti
WEB_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AgenteSquash/1.0; uso personale)"}
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# Nomi delle colonne nel database (maiuscole/minuscole non contano).
# La colonna "titolo" viene riconosciuta da sola, qualunque nome abbia.
COLUMNS = {
    "p1": ["Player 1"],
    "noc1": ["NOC 1"],
    "p2": ["Player 2"],
    "noc2": ["NOC 2"],
    "gender": ["Gender"],
    "score": ["Score"],
    "round": ["Turno"],
    "tournament": ["Torneo"],
    "date": ["Data"],
    "source": ["Fonte", "Fonte (link)", "Link"],
    "id": ["ID univoco", "ID"],
}

ROUND_RE = re.compile(
    r"^(round \d+|round of \d+|quarter[- ]?finals?|semi[- ]?finals?|final)$", re.I
)
SCORE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<games>\d+|-)\s+(?P<pts>(?:\d+|-)(?:\s+(?:\d+|-)){4})$"
)
ENTRANT_RE = re.compile(r"^\d{1,3}\s+(?P<name>.+)$")
SEED_RE = re.compile(r"\s*\((?:\d+|WC|Q|LL)\)\s*$")
DATE_RE = re.compile(r"^\s*(\d{1,2} [A-Za-z]{3} \d{4})")
CODE_RE = re.compile(r"^\s*[A-Z]{3}\s*$")


def die(msg):
    print(f"ERRORE: {msg}")
    sys.exit(1)


def norm(name):
    return re.sub(r"\s+", " ", name).strip().casefold()


# ----------------------------------------------------------------- sito web
def fetch(url):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=WEB_HEADERS, timeout=30)
            r.raise_for_status()
            return r.text
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(3)


def parse_tournament(html, url):
    """Restituisce l'elenco degli incontri conclusi trovati nella pagina."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    tournament = h1.get_text(" ", strip=True) if h1 else url
    slug = urlparse(url).path.strip("/").split("/")[-1] or "torneo"

    gender_of = {}      # nome giocatore -> Men / Women (dall'elenco partecipanti)
    gender = None
    current_round = None
    found = []          # (turno, elemento, risultato della regex)

    for el in soup.find_all(True):
        if el.name in ("h2", "h3", "h4"):
            t = el.get_text(" ", strip=True)
            if t.upper() == "MEN":
                gender = "Men"
            elif t.upper() == "WOMEN":
                gender = "Women"
            else:
                gender = None
        if el.name in ("h1", "h2", "h3", "h4", "h5", "h6") or el.find(True) is None:
            t = el.get_text(" ", strip=True)
            if ROUND_RE.match(t):
                current_round = re.sub(r"\s+", " ", t).title()
        if el.name == "a":
            t = el.get_text(" ", strip=True)
            m = SCORE_RE.match(t)
            if m:
                found.append((current_round, el, m))
            elif gender:
                e = ENTRANT_RE.match(t)
                if e:
                    gender_of[norm(SEED_RE.sub("", e.group("name")))] = gender

    if len(found) % 2:
        print("  Attenzione: numero dispari di giocatori trovati, l'ultimo viene ignorato.")

    matches = {}
    for i in range(0, len(found) - 1, 2):
        rnd, a1, m1 = found[i]
        _, a2, m2 = found[i + 1]
        n1 = (a1.get("title") or SEED_RE.sub("", m1.group("name"))).strip()
        n2 = (a2.get("title") or SEED_RE.sub("", m2.group("name"))).strip()
        if "TBD" in (n1.upper(), n2.upper()) or not rnd:
            continue
        g1, g2 = m1.group("games"), m2.group("games")
        if not (g1.isdigit() and g2.isdigit()) or max(int(g1), int(g2)) < GAMES_TO_WIN:
            continue  # non ancora giocato o non concluso
        pts1, pts2 = m1.group("pts").split(), m2.group("pts").split()
        games = [f"{a}-{b}" for a, b in zip(pts1, pts2) if a != "-" and b != "-"]
        score = f"{g1}-{g2} ({', '.join(games)})"

        date_node = a2.find_next(string=DATE_RE)
        date_iso = ""
        if date_node:
            try:
                date_iso = datetime.strptime(DATE_RE.match(date_node).group(1), "%d %b %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass

        gen = gender_of.get(norm(n1)) or gender_of.get(norm(n2)) or ""
        href1, href2 = a1.get("href", ""), a2.get("href", "")
        match = {
            "id": f"{slug}|{gen}|{rnd}|{n1}|{n2}",
            "p1": n1, "p2": n2,
            "url1": href1 if "/player/" in href1 else "",
            "url2": href2 if "/player/" in href2 else "",
            "gender": gen, "score": score, "round": rnd,
            "tournament": tournament, "date": date_iso, "source": url,
        }
        matches[match["id"]] = match
    return list(matches.values())


_noc_cache = {}


def read_noc(html):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else ""
    for h3 in soup.find_all("h3"):
        if name and h3.get_text(strip=True) == name:
            node = h3.find_next(string=CODE_RE)
            if node:
                return node.strip()
    m = re.search(r"BIRTHPLACE\s+([A-Z]{3})", soup.get_text(" ", strip=True))
    return m.group(1) if m else ""


def get_noc(profile_url):
    if not profile_url:
        return ""
    if profile_url not in _noc_cache:
        time.sleep(PAUSE_SECONDS)
        try:
            _noc_cache[profile_url] = read_noc(fetch(profile_url))
        except requests.RequestException as e:
            print(f"  Non riesco a leggere {profile_url}: {e}")
            _noc_cache[profile_url] = ""
    return _noc_cache[profile_url]


# ------------------------------------------------------------------- Notion
def notion(method, path, **kwargs):
    r = None
    for attempt in range(4):
        r = requests.request(method, "https://api.notion.com/v1" + path,
                             headers=NOTION_HEADERS, timeout=30, **kwargs)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(float(r.headers.get("Retry-After", 2)) + attempt)
            continue
        break
    if not r.ok:
        raise RuntimeError(f"Notion ha risposto {r.status_code}: {r.text[:400]}")
    return r.json()


def read_schema():
    props = notion("GET", f"/databases/{DATABASE_ID}")["properties"]
    by_name = {n.strip().lower(): (n, p["type"]) for n, p in props.items()}
    mapping, missing = {}, []
    for key, options in COLUMNS.items():
        hit = next((by_name[o.lower()] for o in options if o.lower() in by_name), None)
        if hit:
            mapping[key] = hit
        else:
            missing.append(options[0])
    titles = [(n, p["type"]) for n, p in props.items() if p["type"] == "title"]
    mapping["title"] = titles[0]
    if missing:
        die("nel database non trovo queste colonne: " + ", ".join(missing)
            + ". Colonne presenti: " + ", ".join(props.keys()))
    return mapping


def existing_ids(id_column):
    ids, cursor = set(), None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = notion("POST", f"/databases/{DATABASE_ID}/query", json=body)
        for page in data["results"]:
            prop = page["properties"].get(id_column, {})
            parts = prop.get("rich_text") or prop.get("title") or []
            text = "".join(p.get("plain_text", "") for p in parts)
            if text:
                ids.add(text)
        if not data.get("has_more"):
            return ids
        cursor = data["next_cursor"]


def notion_value(ptype, value):
    value = "" if value is None else str(value)
    if ptype == "title":
        return {"title": [{"text": {"content": value[:2000]}}]}
    if ptype == "rich_text":
        return {"rich_text": [{"text": {"content": value[:2000]}}]}
    if ptype == "select":
        return {"select": {"name": value.replace(",", " ")[:100]} if value else None}
    if ptype == "date":
        return {"date": {"start": value} if value else None}
    if ptype == "url":
        return {"url": value or None}
    raise RuntimeError(f"Tipo di colonna non gestito: {ptype}. Usa testo, selezione, data o URL.")


def create_row(mapping, m):
    values = dict(m)
    values["title"] = f"{m['p1']} vs {m['p2']}"
    props = {}
    for key, (name, ptype) in mapping.items():
        props[name] = notion_value(ptype, values.get(key, ""))
    notion("POST", "/pages", json={"parent": {"database_id": DATABASE_ID}, "properties": props})


# --------------------------------------------------------------------- main
def read_urls():
    with open("tornei.txt", encoding="utf-8") as f:
        return [r.strip() for r in f if r.strip() and not r.strip().startswith("#")]


def main():
    if not DRY_RUN and (not NOTION_TOKEN or not DATABASE_ID):
        die("mancano NOTION_TOKEN o NOTION_DATABASE_ID (controlla i Secrets su GitHub).")
    mapping, done = None, set()
    if not DRY_RUN:
        mapping = read_schema()
        done = existing_ids(mapping["id"][0])
        print(f"Righe già presenti in Notion: {len(done)}")
    else:
        print("MODALITÀ PROVA: non scrivo nulla su Notion.")

    errors = added = 0
    for url in read_urls():
        print(f"\nLeggo {url}")
        try:
            matches = parse_tournament(fetch(url), url)
        except requests.RequestException as e:
            print(f"  Sito non raggiungibile: {e}")
            errors += 1
            continue
        new = [m for m in matches if m["id"] not in done]
        print(f"  Incontri conclusi: {len(matches)}, nuovi: {len(new)}")
        if DRY_RUN:
            new = new[:8]
        for m in new:
            m["noc1"], m["noc2"] = get_noc(m["url1"]), get_noc(m["url2"])
            if DRY_RUN:
                print(f"  [{m['gender']}] {m['round']} | {m['p1']} ({m['noc1']}) vs "
                      f"{m['p2']} ({m['noc2']}) | {m['score']} | {m['date']}")
                continue
            try:
                create_row(mapping, m)
                done.add(m["id"])
                added += 1
                time.sleep(0.4)
            except RuntimeError as e:
                print(f"  Errore su {m['p1']} vs {m['p2']}: {e}")
                errors += 1
    if DRY_RUN:
        print("\nProva terminata (mostrati solo i primi 8 incontri nuovi).")
    else:
        print(f"\nFatto. Righe aggiunte: {added}. Errori: {errors}.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
