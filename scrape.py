"""Agente Squash (risultati PSA) · versione 2.0 del 20/11/2026 (scheda 45)

COSA FA
  1. Trova i tornei PSA da leggere:
     - in automatico: Mondiali, Tour Finals, Diamond, Platinum e Gold dal 1/1/2026 (DATA_INIZIO);
     - in più: gli indirizzi scritti a mano in tornei.txt (come nella versione 1).
  2. Per ogni torneo legge dal sito PSA il TABELLONE UFFICIALE completo (servizio dati del sito
     psasquashtour.com, lo stesso che disegna la scheda «Draw»): ordine delle caselle, teste di serie,
     wild card, bye, qualificazioni, risultati game per game, incontri in programma.
  3. Scrive in Notion («🟠 Agente Squash») gli incontri finiti del tabellone principale, senza doppioni.
     Le colonne e l'«ID Univoco» sono IDENTICI alla versione 1: le righe già presenti non si ripetono.
  4. Prepara squash-risultati.json per la pagina squash-risultati.html e, nel lancio vero, lo pubblica
     nel repository map-q-la28 (serve il secret MAPPA_TOKEN) e fa ripartire «Aggiorna mappa LA28».

DIFFERENZE RISPETTO ALLA VERSIONE 1 (che leggeva la pagina HTML dei risultati)
  - fonte: servizio dati del sito invece del testo della pagina (più preciso e più veloce: il NOC arriva
    insieme all'incontro, non serve più aprire la scheda di ogni giocatore);
  - entrano anche gli incontri al meglio dei 3 game (primi turni di alcuni tornei Gold) e i ritiri:
    la versione 1 li scartava perché cercava sempre 3 game vinti;
  - i ritiri hanno «ritiro» in fondo al punteggio, i walkover il punteggio «walkover»;
  - le qualificazioni vanno solo nella pagina web, NON in Notion (come prima).

VARIABILI (secrets e scelte del workflow)
  NOTION_TOKEN        token della connessione Notion «Agente Squash»
  NOTION_DATABASE_ID  link o codice del database «🟠 Agente Squash»
  MAPPA_TOKEN         token GitHub che può scrivere su map-q-la28 (Contents e Actions in scrittura);
                      senza, Notion si aggiorna lo stesso ma la pagina web no
  DRY_RUN=true        solo prova: legge sito e Notion, non scrive nulla
  DATA_INIZIO         primo giorno dei tornei automatici (predefinito 2026-01-01)
  PSA_LOCALE          SOLO PER I COLLAUDI: cartella con file già scaricati al posto del sito
"""
import base64
import html
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta

import requests

VERSIONE = "2.0"

# ------------------------------------------------------------------ impostazioni
SITO = "https://www.psasquashtour.com"
API = SITO + "/wp-json/wp/v2"          # servizio dati del sito (WordPress), pubblico, senza login
CAMPI = "id,slug,link,title,tournament-level,meta"   # solo i campi che servono (la risposta è più leggera)

# Livello del torneo sul sito PSA (numero della categoria «tournament-level») -> nome nella pagina.
# Verificati dal browser il 20/11/2026.
LIVELLI = {1714: "Mondiali", 1715: "Tour Finals", 1716: "Diamond", 1717: "Platinum", 1718: "Gold",
           1719: "Silver", 1720: "Bronze", 1721: "Copper", 1723: "Challenger"}
LIVELLI_AUTOMATICI = [1714, 1715, 1716, 1717, 1718]   # tornei letti senza scriverli in tornei.txt
GIORNI_ANTICIPO = 21          # un torneo futuro entra nella pagina 3 settimane prima dell'inizio
PAUSA_SITO = 1.5              # secondi di pausa tra una richiesta e l'altra al sito PSA
PAUSA_NOTION = 0.4            # secondi di pausa tra una scrittura e l'altra su Notion

WEB_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Referer": SITO + "/",
}

# Variabili d'ambiente
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()
_grezzo = os.getenv("NOTION_DATABASE_ID", "").strip().replace("-", "")
_trovato = re.search(r"[0-9a-fA-F]{32}", _grezzo)
DATABASE_ID = _trovato.group(0) if _trovato else _grezzo
DRY_RUN = os.getenv("DRY_RUN", "").strip().lower() == "true"
DATA_INIZIO = (os.getenv("DATA_INIZIO", "") or "2026-01-01").strip()
MAPPA_TOKEN = os.getenv("MAPPA_TOKEN", "").strip()
PSA_LOCALE = os.getenv("PSA_LOCALE", "").strip()

MAPPA_REPO = "vier80/map-q-la28"      # repository della mappa (pagine web)
MAPPA_WORKFLOW = "aggiorna.yml"       # workflow «Aggiorna mappa LA28», che ripubblica il sito
FILE_WEB = "squash-risultati.json"

NOTION_HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": "2022-06-28",
                  "Content-Type": "application/json"}

# Colonne del database (come nella versione 1; maiuscole/minuscole non contano).
# La colonna titolo («Incontro») viene riconosciuta da sola.
COLONNE = {
    "p1": ["Player 1"], "noc1": ["NOC 1"], "p2": ["Player 2"], "noc2": ["NOC 2"],
    "gender": ["Gender"], "score": ["Score"], "round": ["Turno"], "tournament": ["Torneo"],
    "date": ["Data"], "source": ["Fonte", "Fonte (link)", "Link"], "id": ["ID Univoco", "ID"],
}

# Formato di una casella del tabellone in squash-risultati.json (identico a tennistavolo.json):
#   [colonna, posizione, giocatore_a, testa_a, giocatore_b, testa_b, vincitore, stato, esito, game, data]
#   - colonna: 0 = primo turno; posizione: 0 = in alto (ordine ufficiale del sito);
#   - giocatore_a / _b: numero nell'elenco «squadre» del torneo, -1 = vuoto (bye o da definire);
#   - testa: testa di serie («1»), «WC» wild card, «LL» lucky loser, «Q» dalle qualificazioni, «»;
#   - vincitore: 1 = giocatore_a, 2 = giocatore_b, 0 = da giocare; stato: «F» finito, «N» da giocare;
#   - esito: «» normale, «walkover», «ritiro»;
#   - game: i game dal punto di vista di giocatore_a, es. «11-7 9-11 11-5»; data: AAAA-MM-GG o «».
CAMPI_CASELLA = ["colonna", "posizione", "squadra_a", "testa_a", "squadra_b", "testa_b",
                 "vincitore", "stato", "esito", "set", "data"]

INIZIO = time.time()
AVVISI = []


def avviso(testo):
    print("  Avviso: " + testo)
    AVVISI.append(testo)


def muori(testo):
    print("ERRORE: " + testo)
    sys.exit(1)


# ------------------------------------------------------------------ sito PSA
class SitoRifiuta(Exception):
    """Il sito PSA ha risposto, ma non con i dati (403, 5xx, pagina non JSON, rete)."""


def chiedi(percorso, nome_locale):
    """Una richiesta al servizio dati del sito PSA (3 tentativi). Restituisce i dati JSON.
    Con PSA_LOCALE (collaudi) legge invece il file nome_locale da quella cartella."""
    if PSA_LOCALE:
        f = os.path.join(PSA_LOCALE, nome_locale)
        if not os.path.exists(f):
            raise SitoRifiuta(f"file di collaudo {nome_locale} mancante")
        with open(f, encoding="utf-8") as x:
            return json.load(x)
    ultimo = ""
    for tentativo in range(3):
        try:
            r = requests.get(API + percorso, headers=WEB_HEADERS, timeout=60)
            time.sleep(PAUSA_SITO)
            if r.status_code == 200:
                return r.json()
            ultimo = f"risposta {r.status_code} «{r.text[:80]}»"
            if r.status_code < 500 and r.status_code != 429:
                break                            # 403, 404...: inutile riprovare
        except (requests.RequestException, ValueError) as e:
            ultimo = f"{type(e).__name__}: {e}"
        time.sleep(5 * (tentativo + 1))
    raise SitoRifiuta(ultimo)


def slug_da_url(url):
    """«https://www.psasquashtour.com/tournament/u-s-open-2026/» -> «u-s-open-2026»."""
    m = re.search(r"/tournament/([^/?#]+)", url or "")
    return m.group(1).strip() if m else ""


def leggi_tornei_txt():
    """Indirizzi scritti a mano in tornei.txt (una riga per torneo, # = commento)."""
    if not os.path.exists("tornei.txt"):
        return []
    slugs = []
    with open("tornei.txt", encoding="utf-8") as f:
        for riga in f:
            riga = riga.strip()
            if not riga or riga.startswith("#"):
                continue
            s = slug_da_url(riga)
            if s:
                slugs.append(s)
            else:
                avviso(f"tornei.txt: riga non riconosciuta «{riga}» (serve l'indirizzo .../tournament/nome/)")
    return slugs


def tornei_automatici(oggi):
    """Tornei dei livelli principali dal DATA_INIZIO fino a 3 settimane da oggi: elenco di slug."""
    livelli = ",".join(str(x) for x in LIVELLI_AUTOMATICI)
    inizio = DATA_INIZIO.replace("-", "")
    limite = (oggi + timedelta(days=GIORNI_ANTICIPO)).strftime("%Y%m%d")
    trovati = []
    for pagina in range(1, 6):      # 100 tornei per pagina, dal più recente: 5 pagine bastano e avanzano
        dati = chiedi(f"/tournament?tournament-level={livelli}&per_page=100&page={pagina}&orderby=date"
                      f"&order=desc&_fields=slug,meta.start_date", f"elenco_{pagina}.json")
        for t in dati or []:
            sd = str((t.get("meta") or {}).get("start_date") or "")
            if inizio <= sd <= limite:
                trovati.append((sd, t["slug"]))
        if not dati or len(dati) < 100:
            break
    return [s for _, s in sorted(trovati)]


def data_iso(testo):
    """«20261101» -> «2026-11-01» (le date del torneo); lascia com'è «2026-11-01»."""
    testo = str(testo or "")
    if re.match(r"^\d{8}$", testo):
        return f"{testo[:4]}-{testo[4:6]}-{testo[6:]}"
    return testo[:10]


def nome_breve(titolo):
    """«US Open Squash Championships 2026 powered by Comcast Business» -> «US Open Squash Championships 2026»."""
    nome = re.split(r"\s+(?:presented|powered|sponsored)\s+by\s+", titolo, flags=re.I)[0]
    return re.sub(r"\s+", " ", nome.replace(",", " ")).strip()


def codice_noc(bandiera):
    """Il NOC sta nel nome del file della bandiera: «…/flags/80x40/EGY.png» -> «EGY» (codici PSA: ENG resta ENG)."""
    m = re.search(r"/([A-Z]{3})\.(?:png|svg|jpg)", bandiera or "")
    return m.group(1) if m else ""


# ------------------------------------------------------------------ lettura di un incontro
def game_validi(m, ids):
    """Game di un incontro dal punto di vista di ids[0], tolti i game non iniziati (0-0)."""
    lista = []
    for g in m.get("games") or []:
        punti = {p.get("player_id"): p.get("score") for p in g.get("players") or []}
        a, b = punti.get(ids[0]), punti.get(ids[1]) if len(ids) > 1 else None
        if isinstance(a, int) and isinstance(b, int) and (a, b) != (0, 0):
            lista.append((a, b))
    return lista


def esito_incontro(m, giochi, lato_vincitore):
    """«» = normale, «walkover» = non giocato, «ritiro» = finito prima del tempo.

    - walkover: nessun game, oppure solo game 11-0 per il vincitore (il sito li usa come riempitivo:
      Tour Finals 2026, Asal–Elias in semifinale = 0-11 0-11 0-11);
    - ritiro: il vincitore ha finito meno game di quelli che servono (3 su 5, o 2 su 3).
      Un game è finito quando qualcuno arriva a 11 (con il vantaggio di 2, oppure 11-10 nelle Tour Finals).
    """
    if not giochi:
        return "walkover"
    v = 0 if lato_vincitore == 1 else 1
    if all(g[v] == 11 and g[1 - v] == 0 for g in giochi) and len(giochi) >= 2:
        return "walkover"
    servono = int(m.get("best") or 5) // 2 + 1
    vinti = sum(1 for g in giochi if max(g) >= 11 and g[v] > g[1 - v])
    return "ritiro" if vinti < servono else ""


class Squadre:
    """Elenco dei giocatori del torneo (ognuno una volta): [nome, NOC, codice PSA].
    Nelle caselle del tabellone si scrive solo il numero del giocatore in questo elenco."""

    def __init__(self):
        self.lista, self.indice = [], {}

    def aggiungi(self, nome, noc, codice):
        chiave = str(codice or nome)
        if not nome and not codice:
            return -1
        if chiave not in self.indice:
            self.indice[chiave] = len(self.lista)
            self.lista.append([nome or "?", noc or "", str(codice or "")])
        return self.indice[chiave]


def nome_turno(i, n_turni, n_incontri):
    """Nome del turno come sul sito PSA (e come nella colonna «Turno» di Notion).
    i = 0 per il primo turno; gli ultimi tre sono Quarter Final, Semi Final, Final."""
    if n_incontri == 1 and i == n_turni - 1:
        return "Final"
    if n_incontri == 2 and i == n_turni - 2:
        return "Semi Final"
    if n_incontri == 4 and i == n_turni - 3:
        return "Quarter Final"
    return f"Round {i + 1}"


def sigla_turno(n_incontri):
    """Sigla della colonna nella pagina: 1 incontro = Final, 2 = SF, 4 = QF, 8 = R16, 16 = R32..."""
    return {1: "Final", 2: "SF", 4: "QF"}.get(n_incontri, f"R{2 * n_incontri}")


def leggi_torneo(slug, oggi):
    """Legge un torneo dal sito PSA. Restituisce un dizionario con:
    info (per la pagina), righe (per Notion), incontri (per l'elenco della pagina), tab (tabellone)."""
    dati = chiedi(f"/tournament?slug={slug}&_fields={CAMPI}", f"{slug}.json")
    if not dati:
        raise ValueError("torneo non trovato sul sito PSA (controlla l'indirizzo)")
    t = dati[0]
    meta = t.get("meta") or {}
    titolo = html.unescape((t.get("title") or {}).get("rendered") or slug).strip()
    livelli = t.get("tournament-level") or []
    categoria = next((LIVELLI[x] for x in livelli if x in LIVELLI), "Altro")
    try:
        competizioni = json.loads(meta.get("competitions") or "[]")
        iscritti = json.loads(meta.get("players") or "[]")
    except ValueError:
        raise ValueError("dati del torneo in un formato inatteso")
    # nomi e NOC dall'elenco degli iscritti: servono quando l'incontro non li riporta (Tour Finals 2026)
    anagrafe = {}
    for p in iscritti:
        anagrafe[p.get("player_id")] = (p.get("name") or "", p.get("country_iso3") or "")

    inizio, fine = data_iso(meta.get("start_date")), data_iso(meta.get("end_date"))
    nome = nome_breve(titolo)
    url = t.get("link") or f"{SITO}/tournament/{slug}/"
    squadre = Squadre()
    righe, incontri, spec, attesi, finiti = [], [], {}, 0, 0

    for comp in competizioni:
        genere = "Women" if str(comp.get("name") or "").lower().startswith("w") else "Men"
        disc = "WS" if genere == "Women" else "MS"
        tabelloni = [d for d in comp.get("draws") or [] if d.get("rounds")]
        principale = next((d for d in tabelloni if d.get("draw_type_id") == 1), None)
        qualif = next((d for d in tabelloni if d is not principale and d.get("draw_type_id") != 1), None)
        if not principale:
            continue
        # teste di serie, wild card e lucky loser del tabellone principale
        segni = {}
        for p in principale.get("players") or []:
            if p.get("seeding"):
                segni[p.get("player_id")] = str(p["seeding"])
            elif p.get("wildcard"):
                segni[p.get("player_id")] = "WC"
            elif p.get("luckyloser"):
                segni[p.get("player_id")] = "LL"
        qualificati = set()        # vincitori dell'ultimo turno delle qualificazioni = «Q» nel principale

        def giocatore(p):
            pid = p.get("player_id")
            nome_g, noc_g = anagrafe.get(pid, ("", ""))
            nome_g = (p.get("name") or "").strip() or nome_g
            noc_g = codice_noc(p.get("flag")) or noc_g
            return pid, nome_g, noc_g

        def tabellone(draw, e_principale):
            """Caselle di un tabellone (principale o qualificazioni) + righe per Notion e per l'elenco."""
            nonlocal attesi, finiti
            turni = sorted(draw.get("rounds") or [], key=lambda r: r.get("num") or 0)
            caselle, sigle = [], []
            for i, turno in enumerate(turni):
                partite = turno.get("matches") or []
                n = len(partite)
                if e_principale:
                    sigle.append(sigla_turno(n))
                    nome_t = nome_turno(i, len(turni), n)
                else:
                    sigle.append(f"Q{i + 1}")
                    nome_t = f"Qualifying Round {i + 1}"
                for m in partite:
                    lati = {p.get("num"): p for p in m.get("players") or []}
                    info = [giocatore(lati[k]) if k in lati else (None, "", "") for k in (1, 2)]
                    idx = [squadre.aggiungi(x[1], x[2], x[0]) if x[0] else -1 for x in info]
                    vincitore = m.get("winner") or 0
                    if m.get("bye"):
                        # passaggio diretto: passa il giocatore presente (a volte il sito non lo segna)
                        vincitore = 1 if idx[0] >= 0 else 2 if idx[1] >= 0 else 0
                        giochi, esito = [], ""
                    else:
                        attesi += 1
                        ids = [info[0][0], info[1][0]]
                        giochi = game_validi(m, ids) if vincitore else []
                        esito = esito_incontro(m, giochi, vincitore) if vincitore else ""
                        if esito == "walkover":
                            giochi = []
                    teste = []
                    for k in (0, 1):
                        pid = info[k][0]
                        teste.append("" if not pid else segni.get(pid, "") if e_principale else "")
                        if e_principale and pid and not teste[k] and (pid in qualificati or lati.get(k + 1, {}).get("qualifier")):
                            teste[k] = "Q"
                    pos = max(0, int(m.get("num") or 1) - 1)
                    caselle.append([i, pos, idx[0], teste[0], idx[1], teste[1], vincitore,
                                    "F" if vincitore else "N", esito,
                                    " ".join(f"{a}-{b}" for a, b in giochi), m.get("date") or ""])
                    if m.get("bye") or not vincitore or idx[0] < 0 or idx[1] < 0:
                        continue
                    finiti += 1
                    if not e_principale and i == len(turni) - 1:
                        qualificati.add(info[vincitore - 1][0])
                    # --- riga dell'elenco della pagina: vincitore per primo, punteggio dal suo punto di vista
                    v, s = (0, 1) if vincitore == 1 else (1, 0)
                    g_v = [(g[v], g[s]) for g in giochi]
                    dett = ", ".join(f"{a}-{b}" for a, b in g_v)
                    vinti_v = int((lati[v + 1].get("games")) or 0)
                    vinti_s = int((lati[s + 1].get("games")) or 0)
                    if esito == "walkover":
                        testo_web = "walkover"
                    elif esito == "ritiro":
                        testo_web = f"ritiro ({dett})" if dett else "ritiro"
                    else:
                        testo_web = f"{vinti_v}-{vinti_s} ({dett})"
                    incontri.append([nome, disc, nome_t, info[v][1], info[v][2], info[s][1], info[s][2],
                                     testo_web, m.get("date") or ""])
                    if not e_principale:
                        continue                  # le qualificazioni non vanno in Notion
                    # --- riga per Notion: come nella versione 1 (Player 1 = primo giocatore della casella,
                    #     punteggio dal SUO punto di vista: Player 1 non è sempre il vincitore)
                    g1, g2 = int(lati[1].get("games") or 0), int(lati[2].get("games") or 0)
                    if esito == "walkover":
                        score = "walkover"
                    else:
                        score = f"{g1}-{g2} (" + ", ".join(f"{a}-{b}" for a, b in giochi) + ")"
                        if esito == "ritiro":
                            score += " ritiro"
                    p1, p2 = info[0][1], info[1][1]
                    righe.append({
                        "id": f"{slug}|{genere}|{nome_t}|{p1}|{p2}",
                        "p1": p1, "noc1": info[0][2], "p2": p2, "noc2": info[1][2],
                        "gender": genere, "score": score, "round": nome_t, "tournament": titolo,
                        "date": m.get("date") or "", "source": url,
                        "_ordine": (m.get("date") or "9", i, pos),
                    })
            caselle.sort(key=lambda c: (c[0], c[1]))
            return {"misura": int(draw.get("size") or 2 * len(turni[0].get("matches") or []) if turni else 0),
                    "turni": sigle, "c": caselle}

        voce_q = tabellone(qualif, False) if qualif else None   # prima le qualificazioni (servono le «Q»)
        voce = {"tipo": "E", **tabellone(principale, True)}
        if voce_q and voce_q["c"]:
            voce["q"] = voce_q
        spec[disc] = voce

    # stato del torneo
    if inizio and inizio > oggi.isoformat():
        stato = "da giocare"
    elif fine and fine >= oggi.isoformat():
        stato = "in corso"
    elif spec and any(c[7] != "F" for v in spec.values() for c in v["c"]) \
            and fine >= (oggi - timedelta(days=3)).isoformat():
        stato = "in corso"           # finito da poco sul calendario, ma qualche risultato non è ancora arrivato
    else:
        stato = "concluso"
    info = {"nome": nome, "id": t.get("id"), "slug": slug, "categoria": categoria, "inizio": inizio,
            "fine": fine, "luogo": meta.get("location") or "", "url": url, "stato": stato,
            "incontri": finiti, "attesi": attesi}
    tab = {"id": t.get("id"), "squadre": squadre.lista, "spec": {d: spec[d] for d in ("MS", "WS") if d in spec}}
    return {"info": info, "righe": righe, "incontri": incontri, "tab": tab if spec else None, "titolo": titolo}


# ------------------------------------------------------------------ Notion (come nella versione 1)
def notion(metodo, percorso, **kwargs):
    r = None
    for tentativo in range(5):
        r = requests.request(metodo, "https://api.notion.com/v1" + percorso,
                             headers=NOTION_HEADERS, timeout=60, **kwargs)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(float(r.headers.get("Retry-After", 2)) + tentativo * 2)
            continue
        break
    if r.status_code == 404:
        muori("Notion non trova il database «🟠 Agente Squash»: aprilo, ••• > Connessioni, aggiungi la "
              "connessione «Agente Squash» e controlla NOTION_DATABASE_ID.")
    if not r.ok:
        raise RuntimeError(f"Notion ha risposto {r.status_code}: {r.text[:400]}")
    return r.json()


def leggi_schema():
    props = notion("GET", f"/databases/{DATABASE_ID}")["properties"]
    per_nome = {n.strip().lower(): (n, p["type"]) for n, p in props.items()}
    mappa, mancanti = {}, []
    for chiave, nomi in COLONNE.items():
        trovata = next((per_nome[x.lower()] for x in nomi if x.lower() in per_nome), None)
        if trovata:
            mappa[chiave] = trovata
        else:
            mancanti.append(nomi[0])
    if mancanti:
        muori("nel database mancano queste colonne: " + ", ".join(mancanti)
              + ". Colonne presenti: " + ", ".join(props.keys()))
    mappa["title"] = next((n, p["type"]) for n, p in props.items() if p["type"] == "title")
    return mappa


def id_presenti(colonna_id):
    """Tutti gli «ID Univoco» già in Notion (100 righe alla volta)."""
    ids, cursore = set(), None
    while True:
        corpo = {"page_size": 100}
        if cursore:
            corpo["start_cursor"] = cursore
        dati = notion("POST", f"/databases/{DATABASE_ID}/query", json=corpo)
        for pagina in dati["results"]:
            prop = pagina["properties"].get(colonna_id, {})
            testo = "".join(x.get("plain_text", "") for x in (prop.get("rich_text") or prop.get("title") or []))
            if testo:
                ids.add(testo)
        if not dati.get("has_more"):
            return ids
        cursore = dati["next_cursor"]


def valore_notion(tipo, valore):
    valore = "" if valore is None else str(valore)
    if tipo == "title":
        return {"title": [{"text": {"content": valore[:2000]}}]}
    if tipo == "rich_text":
        return {"rich_text": [{"text": {"content": valore[:2000]}}] if valore else []}
    if tipo == "select":
        return {"select": {"name": valore.replace(",", " ")[:100]} if valore else None}
    if tipo == "date":
        return {"date": {"start": valore} if valore else None}
    if tipo == "url":
        return {"url": valore or None}
    raise RuntimeError(f"Tipo di colonna non gestito: {tipo}. Usa testo, selezione, data o URL.")


def scrivi_riga(mappa, riga):
    valori = dict(riga)
    valori["title"] = f"{riga['p1']} vs {riga['p2']}"
    props = {nome: valore_notion(tipo, valori.get(chiave, "")) for chiave, (nome, tipo) in mappa.items()}
    notion("POST", "/pages", json={"parent": {"database_id": DATABASE_ID}, "properties": props})


# ------------------------------------------------------------------ pagina web
def file_web(tornei, oggi):
    """squash-risultati.json: stesso formato di tennistavolo.json (la pagina è una sua copia)."""
    elenco = sorted((x["info"] for x in tornei), key=lambda t: (t["inizio"], t["nome"]))
    incontri = [m for x in tornei for m in x["incontri"]]
    ordine = {"Final": 0, "Semi Final": 1, "Quarter Final": 2}
    incontri.sort(key=lambda m: (m[0], m[1], ordine.get(m[2], 9), m[2], m[8]))
    return {"aggiornato": oggi.isoformat(), "versione": VERSIONE,
            "stagioni": sorted({t["inizio"][:4] for t in elenco if t["inizio"]}),
            "campi": ["torneo", "disciplina", "turno", "vincitore", "noc_vincitore", "sconfitto",
                      "noc_sconfitto", "punteggio", "data"],
            "tornei": elenco, "incontri": incontri, "campi_casella": CAMPI_CASELLA,
            "tabelloni": {x["info"]["nome"]: x["tab"] for x in tornei if x["tab"]}}


def gh_headers(accept="application/vnd.github+json"):
    h = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if MAPPA_TOKEN:
        h["Authorization"] = f"Bearer {MAPPA_TOKEN}"
    return h


def pubblica(payload):
    """Scrive squash-risultati.json su map-q-la28 (solo se è cambiato qualcosa oltre la data)
    e fa ripartire «Aggiorna mappa LA28», che ripubblica il sito."""
    url = f"https://api.github.com/repos/{MAPPA_REPO}/contents/{FILE_WEB}"
    sha, vecchio = None, None
    r = requests.get(url, headers=gh_headers(), timeout=30)
    if r.status_code == 200:
        sha = r.json().get("sha")
        g = requests.get(url, headers=gh_headers("application/vnd.github.raw+json"), timeout=90)
        try:
            vecchio = json.loads(g.content.decode("utf-8")) if g.status_code == 200 else None
        except ValueError:
            vecchio = None
    elif r.status_code != 404:
        raise RuntimeError(f"GitHub ha risposto {r.status_code}: {r.text[:300]}")
    if vecchio and {**vecchio, "aggiornato": ""} == {**payload, "aggiornato": ""}:
        print("Pagina web: nessuna novità, non la ripubblico.")
        return
    testo = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    corpo = {"message": "Aggiorna i risultati dello squash",
             "content": base64.b64encode(testo.encode("utf-8")).decode("ascii")}
    if sha:
        corpo["sha"] = sha
    r = requests.put(url, headers=gh_headers(), json=corpo, timeout=120)
    if not r.ok:
        raise RuntimeError(f"GitHub non accetta {FILE_WEB}: {r.status_code} {r.text[:300]}")
    r = requests.post(f"https://api.github.com/repos/{MAPPA_REPO}/actions/workflows/{MAPPA_WORKFLOW}/dispatches",
                      headers=gh_headers(), json={"ref": "main"}, timeout=30)
    if r.status_code != 204:
        print(f"  Attenzione: {FILE_WEB} salvato, ma la ripubblicazione non è partita ({r.status_code}). "
              "Lancia a mano «Aggiorna mappa LA28» su map-q-la28.")
    else:
        print(f"Pagina web: {FILE_WEB} aggiornato ({len(testo) // 1024} KB), ripubblicazione avviata.")


# ------------------------------------------------------------------ programma principale
def main():
    oggi = date.fromisoformat(os.getenv("OGGI")) if os.getenv("OGGI") else date.today()   # OGGI: solo collaudi
    print(f"Agente Squash {VERSIONE} · {datetime.now():%d/%m/%Y %H:%M} · "
          f"{'SOLO PROVA (non scrivo nulla)' if DRY_RUN else 'lancio vero'} · tornei automatici dal {DATA_INIZIO}")

    # 1. Notion: colonne e righe già presenti (anche in prova, se il token c'è)
    mappa, gia = None, set()
    if NOTION_TOKEN and DATABASE_ID:
        mappa = leggi_schema()
        gia = id_presenti(mappa["id"][0])
        print(f"Righe già presenti in Notion: {len(gia)}")
    elif not DRY_RUN:
        muori("mancano NOTION_TOKEN o NOTION_DATABASE_ID (controlla i Secrets su GitHub).")
    else:
        print("Notion non letto (manca il token): la prova conta tutto come nuovo.")

    # 2. Elenco dei tornei: automatici + tornei.txt (senza doppioni, nell'ordine)
    try:
        automatici = tornei_automatici(oggi)
    except SitoRifiuta as e:
        automatici = []
        avviso(f"elenco automatico dei tornei non letto, il sito PSA ha risposto: {e}")
    a_mano = leggi_tornei_txt()
    slugs = list(dict.fromkeys(automatici + a_mano))
    print(f"Tornei da leggere: {len(slugs)} ({len(automatici)} automatici, {len(a_mano)} da tornei.txt)")
    if not slugs:
        muori("nessun torneo da leggere: né l'elenco automatico né tornei.txt.")

    # 3. Lettura dei tornei
    letti, rifiuti = [], 0
    for slug in slugs:
        try:
            x = leggi_torneo(slug, oggi)
        except SitoRifiuta as e:
            rifiuti += 1
            avviso(f"{slug}: il sito PSA non dà i dati ({e})")
            continue
        except (ValueError, KeyError, TypeError) as e:
            avviso(f"{slug}: {e}")
            continue
        letti.append(x)
        i = x["info"]
        dett = ", ".join(f"{d} {v['misura']}" + (f" (qualif. {v['q']['misura']})" if v.get("q") else "")
                         for d, v in (x["tab"] or {"spec": {}})["spec"].items()) or "tabellone non ancora pubblicato"
        print(f"  {i['categoria']} · {i['nome']} ({i['inizio']} – {i['fine']}, {i['stato']}): {dett}; "
              f"incontri finiti {i['incontri']} su {i['attesi']}")
    if not letti:
        muori("nessun torneo letto: il sito PSA rifiuta i server di GitHub? Manda il rapporto a Claude.")

    # 4. Notion: righe nuove, in ordine di data
    tutte = sorted((r for x in letti for r in x["righe"]), key=lambda r: r["_ordine"])
    nuove = [r for r in tutte if r["id"] not in gia]
    gia_li = len(tutte) - len(nuove)
    print(f"\nIncontri del tabellone principale finiti: {len(tutte)} · già in Notion: {gia_li} · nuovi: {len(nuove)}")
    scritte = errori = 0
    if DRY_RUN:
        for r in nuove[:12]:
            print(f"  [{r['gender']}] {r['round']} | {r['p1']} ({r['noc1']}) vs {r['p2']} ({r['noc2']}) | "
                  f"{r['score']} | {r['date']} | {r['tournament']}")
        if len(nuove) > 12:
            print(f"  ... e altri {len(nuove) - 12}")
    else:
        for r in nuove:
            try:
                scrivi_riga(mappa, r)
                gia.add(r["id"])
                scritte += 1
                if scritte % 50 == 0:
                    print(f"  ... scritte {scritte} righe", flush=True)
                time.sleep(PAUSA_NOTION)
            except (RuntimeError, requests.RequestException) as e:
                errori += 1
                print(f"  Errore su {r['p1']} vs {r['p2']}: {e}")

    # 5. File per la pagina web: sempre negli Artifacts; nel lancio vero anche su map-q-la28
    payload = file_web(letti, oggi)
    with open(FILE_WEB, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    pubblicata = "no (prova)" if DRY_RUN else "no (manca MAPPA_TOKEN)"
    if not DRY_RUN and MAPPA_TOKEN:
        try:
            pubblica(payload)
            pubblicata = "sì"
        except (RuntimeError, requests.RequestException) as e:
            print(f"Pagina web non aggiornata: {e}")
            pubblicata = "NO, errore (vedi sopra)"
            errori += 1

    # 6. Riepilogo
    print("\n=================== RIEPILOGO ===================")
    print(f"Tornei letti: {len(letti)} su {len(slugs)}" + (f" · rifiutati dal sito: {rifiuti}" if rifiuti else ""))
    print(f"Notion: già presenti {gia_li}, nuovi {len(nuove)}" + ("" if DRY_RUN else f", scritti {scritte}, errori {errori}"))
    print(f"{FILE_WEB}: {len(payload['tornei'])} tornei, {len(payload['incontri'])} incontri, "
          f"{len(payload['tabelloni'])} tabelloni · pubblicato su map-q-la28: {pubblicata}")
    if AVVISI:
        print(f"\nAvvisi ({len(AVVISI)}):")
        for a in AVVISI:
            print("  - " + a)
    print(f"Durata: {(time.time() - INIZIO) / 60:.1f} minuti")
    if errori:
        sys.exit(1)


if __name__ == "__main__":
    main()
