# =========================================================================
# TRIAGE-BACKTEST II: 5 Kandidaten + 1 Kontrolle in anderen Maerkten
# (aus /screen vom 2026-09-01, Runde 2 nach der leeren Nasdaq-Runde)
#
# Maerkte:  Erdgas (GAS.CMD/USD), EUR/USD, Bitcoin (BTC/USD)
# Daten:    Dukascopy 1-Minuten-BID-Kerzen — NUR an den Tagen, die die
#           jeweilige Regel ueberhaupt braucht (Event-selektiver Download,
#           deshalb ~3.000 statt ~15.000 Dateien)
# Kosten:   pro Instrument realistisch am handelbaren Venue angesetzt
#           (Futures/Perp, nicht am CFD-Spread der Datenquelle)
# Holdout:  fest gepinnt ab QUARANTAENE_AB — wird hier NIE angefasst
# Regeln:   EIN fester Parametersatz pro Idee, kein Sweep, keine Optimierung
# Laufzeit: erster Lauf ~15-25 Min (Download), danach <1 Min dank Cache.
#           Abgebrochener Lauf darf neu gestartet werden, Cache bleibt.
# =========================================================================

import warnings, os, lzma, time, math, sys, threading
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")
np.random.seed(42)

# ------------------------------------------------------------------
# 1) KONFIG
# ------------------------------------------------------------------
DATEN_ENDE     = dt.date(2026, 8, 28)            # FEST GEPINNT
QUARANTAENE_AB = pd.Timestamp("2023-06-01")      # FEST GEPINNT: Holdout fuer /colab
N_JOBS         = 6                               # Dukascopy drosselt ab ~10
CACHE_DIR      = "/content/dk_cache2"

# Startdaten je Instrument (Dukascopy-Historie: GAS ab 2012-09, BTC ab 2017-05)
START_GAS  = dt.date(2013, 1, 1)
START_EUR  = dt.date(2012, 1, 1)
START_BTC  = dt.date(2018, 1, 1)

# Realistische Round-Trip-Kosten am handelbaren Venue (bps des Notionals):
COST_BPS = {
    "GASCMDUSD": 6.0,   # NG-Future: Tick 0,001 = 10 USD auf ~30k Notional (3,3 bps)
                        #            + Slippage/Kommission -> konservativ 6
    "EURUSD":    1.0,   # EUR/USD Spot/Future: Spread ~0,2 Pips + Kommission
    "BTCUSD":   10.0,   # Perp-Taker Binance/Bybit ~4,5-5,5 bps PRO SEITE
}

# Feste Parameter (EIN Satz pro Idee, begruendet):
EIA_VOR_MIN    = 90      # K1: Short 90 Min vor der EIA-Meldung (Paper-Regel)
EIA_NACH_MIN   = 30      # K1: Exit 30 Min danach (Paper-Regel)
CASCADE_TRIG   = 0.045   # K4: 60-Min-Bewegung >= 4,5% = Liquidationskaskade
CASCADE_HOLD_H = 4       # K4: 4 Stunden halten
CASCADE_STOP   = 0.03    # K4: 3% Stop gegen die Position
TAGESRANGE_MIN = 0.040   # Vorfilter Downloadtage (STRIKT kleiner als CASCADE_TRIG
                         # -> jeder Trigger-Tag ist zwingend enthalten, kein Bias)

if not os.path.isdir("/content"):
    CACHE_DIR = "./dk_cache2"
os.makedirs(CACHE_DIR, exist_ok=True)

print("ANNAHMEN: Dukascopy 1-Min-BID-Kerzen als Preisquelle (CFD-Quotes ~ Referenz-")
print("markt); Ausfuehrung zu Bar-Preisen; Kosten je Instrument am realistischen")
print(f"Venue: {COST_BPS}; ein fester Parametersatz pro Idee, keine Optimierung;")
print(f"Datenende {DATEN_ENDE}; QUARANTAENE fuer /colab ab {QUARANTAENE_AB.date()}.\n")

# ------------------------------------------------------------------
# 2) DUKASCOPY-LOADER (rate-limit-fest, event-selektiv)
# ------------------------------------------------------------------
HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
           "Accept": "*/*", "Referer": "https://freeserv.dukascopy.com/2.0/"}
_tls = threading.local()
def _session():
    if not hasattr(_tls, "s"):
        s = requests.Session(); s.headers.update(HEADERS); _tls.s = s
    return _tls.s

def lade_tag(inst, d, versuche=2):
    """Eine Tagesdatei. Rueckgabe (inst, datum, bytes|None, status)."""
    fn = os.path.join(CACHE_DIR, f"{inst}_{d.isoformat()}.bi5")
    if os.path.exists(fn):
        with open(fn, "rb") as f:
            raw = f.read()
        return inst, d, (raw if raw else None), ("ok" if raw else "leer")
    url = (f"https://datafeed.dukascopy.com/datafeed/{inst}/"
           f"{d.year}/{d.month-1:02d}/{d.day:02d}/BID_candles_min_1.bi5")
    grund = "unbekannt"
    for versuch in range(versuche):
        try:
            r = _session().get(url, timeout=30)
            if r.status_code == 404 or (r.status_code == 200 and len(r.content) == 0):
                if (dt.date.today() - d).days >= 4:      # nur sicher publizierte Tage
                    tmp = fn + ".tmp"; open(tmp, "wb").close(); os.replace(tmp, fn)
                return inst, d, None, "leer"
            if r.status_code == 200:
                tmp = fn + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(r.content)
                os.replace(tmp, fn)
                return inst, d, r.content, "ok"
            grund = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            grund = type(e).__name__
        time.sleep(min(2 ** versuch, 15))
    return inst, d, None, f"fehler:{grund}"

def lade_viele(jobs):
    """jobs: Liste (instrument, datum). Rueckgabe {(inst,datum): bytes}."""
    roh, fehl, gruende, fertig, streak, t0 = {}, set(), {}, 0, 0, time.time()
    abbruch = False
    with ThreadPoolExecutor(max_workers=N_JOBS) as ex:
        futs = {ex.submit(lade_tag, i, d): (i, d) for i, d in jobs}
        for fut in as_completed(futs):
            i, d, raw, status = fut.result()
            if raw:
                roh[(i, d)] = raw
            elif status.startswith("fehler"):
                fehl.add((i, d)); g = status.split(":", 1)[1]
                gruende[g] = gruende.get(g, 0) + 1
            streak = streak + 1 if status.startswith("fehler") else 0
            fertig += 1
            if fertig % max(1, len(jobs)//10) == 0:
                print(f"  {fertig}/{len(jobs)}, {len(roh)} mit Daten, {len(fehl)} Fehler "
                      f"({time.time()-t0:.0f}s)")
            if streak >= 150:
                print("  Massives Blocken — Parallel-Durchgang abgebrochen.")
                ex.shutdown(wait=False, cancel_futures=True); abbruch = True; break
        if abbruch:
            for fut, key in futs.items():
                if fut.cancelled() or not fut.done():
                    fehl.add(key)
                elif key not in roh and key not in fehl:
                    i, d, raw, status = fut.result()
                    if raw: roh[(i, d)] = raw
                    elif status.startswith("fehler"): fehl.add(key)
    if gruende:
        print(f"  Fehlergruende: {gruende}")
    if fehl:                                   # langsamer zweiter Durchgang
        rest = sorted(fehl, key=lambda k: (k[0], k[1]))
        print(f"  {len(rest)} Nachzuegler, zweiter langsamer Durchgang ...")
        serie = 0
        for n, (i, d) in enumerate(rest):
            _, _, raw, status = lade_tag(i, d, versuche=3)
            if raw: roh[(i, d)] = raw; serie = 0
            elif status.startswith("fehler"): serie += 1
            else: serie = 0
            if serie >= 30:
                print("  Server blockt weiterhin — Zelle spaeter erneut ausfuehren "
                      "(Cache bleibt erhalten).")
                break
            time.sleep(0.25)
    return roh

DT_OCLH = np.dtype([("t", ">u4"), ("o", ">u4"), ("c", ">u4"),
                    ("l", ">u4"), ("h", ">u4"), ("v", ">f4")])
DT_OHLC = np.dtype([("t", ">u4"), ("o", ">u4"), ("h", ">u4"),
                    ("l", ">u4"), ("c", ">u4"), ("v", ">f4")])

def entpacke(raw, dtype):
    dec = lzma.decompress(raw); n = len(dec) // 24
    return np.frombuffer(dec[:n*24], dtype=dtype)

def ohlc_ok(a):
    o, c, l, h = (a["o"].astype(float), a["c"].astype(float),
                  a["l"].astype(float), a["h"].astype(float))
    return np.mean((h >= np.maximum(o, c)) & (l <= np.minimum(o, c)))

def baue_frame(roh, inst):
    """Minutenframe (UTC) fuer ein Instrument, inkl. Format-/Skalen-Erkennung."""
    tage = sorted([d for (i, d) in roh if i == inst])
    if not tage:
        return None
    probe, FORMAT = None, None
    for d in tage[:5]:                          # deterministisch, aelteste Tage
        try:
            kand = entpacke(roh[(inst, d)], DT_OCLH)
        except lzma.LZMAError:
            continue
        if len(kand) < 60:
            continue
        FORMAT = DT_OCLH if ohlc_ok(kand) > 0.95 else DT_OHLC
        probe = entpacke(roh[(inst, d)], FORMAT); break
    if probe is None or ohlc_ok(probe) < 0.95:
        print(f"  WARNUNG {inst}: Kerzenformat nicht erkannt — uebersprungen.")
        return None
    med_roh = float(np.median(probe["c"]))
    SKALA = 1.0                                  # Skala aus plausiblem Preisniveau
    ZIEL = {"GASCMDUSD": (0.5, 30.0), "EURUSD": (0.5, 2.5), "BTCUSD": (1000., 500000.)}
    lo, hi = ZIEL[inst]
    for s in (1e5, 1e4, 1e3, 1e2, 10., 1.):
        if lo < med_roh / s < hi:
            SKALA = s; break
    frames, kaputt = [], 0
    for d in tage:
        try:
            a = entpacke(roh[(inst, d)], FORMAT)
        except lzma.LZMAError:
            fn = os.path.join(CACHE_DIR, f"{inst}_{d.isoformat()}.bi5")
            if os.path.exists(fn): os.remove(fn)
            kaputt += 1; continue
        if len(a) == 0:
            continue
        ts = pd.Timestamp(d, tz="UTC") + pd.to_timedelta(a["t"], unit="s")
        frames.append(pd.DataFrame({"open": a["o"]/SKALA, "high": a["h"]/SKALA,
                                    "low": a["l"]/SKALA, "close": a["c"]/SKALA}, index=ts))
    if kaputt:
        print(f"  WARNUNG {inst}: {kaputt} korrupte Cache-Dateien geloescht (Re-Download "
              "beim naechsten Lauf).")
    if not frames:
        return None
    m = pd.concat(frames).sort_index()
    m = m[~m.index.duplicated(keep="last")]
    print(f"  {inst}: {len(m):,} Minutenbars, Skala /{SKALA:.0f}, "
          f"{m.index[0].date()} .. {m.index[-1].date()}")
    return m

# ------------------------------------------------------------------
# 3) TAGESLISTEN — nur was die Regeln brauchen
# ------------------------------------------------------------------

def _naive(idx):
    """yfinance liefert je nach Version naive oder tz-aware Indizes."""
    idx = pd.to_datetime(idx)
    return idx.tz_convert(None) if getattr(idx, "tz", None) is not None else idx

def werktage(start, ende):
    d, out = start, []
    while d <= ende:
        if d.weekday() < 5: out.append(d)
        d += dt.timedelta(days=1)
    return out

# K1 Erdgas: Donnerstage (EIA 10:30 ET) + Freitage (Feiertagsverschiebung)
gas_tage = [d for d in werktage(START_GAS, DATEN_ENDE) if d.weekday() in (3, 4)]

# K2/K3 EUR/USD: letzte 3 Geschaeftstage des Monats + erster des Folgemonats
eur_alle = werktage(START_EUR, DATEN_ENDE)
eur_df = pd.DataFrame({"d": eur_alle})
eur_df["p"] = pd.to_datetime(eur_df["d"]).dt.to_period("M")
eur_tage = []
for p, g in eur_df.groupby("p"):
    eur_tage += list(g["d"].iloc[-3:])
    nxt = eur_df[eur_df["p"] == p + 1]
    if len(nxt): eur_tage.append(nxt["d"].iloc[0])
eur_tage = sorted(set(eur_tage))

# K4 Bitcoin: nur Tage mit Tagesrange >= TAGESRANGE_MIN (strikte Obermenge der
# Trigger-Tage, da ein 60-Min-Move von 4,5% zwingend >=4,5% Tagesrange erzeugt)
btc_tage, btc_daily = [], None
try:
    import yfinance as yf
    for versuch in range(3):
        bd = yf.download("BTC-USD", start=str(START_BTC), end=str(DATEN_ENDE),
                         auto_adjust=False, progress=False)
        if len(bd) > 500:
            if isinstance(bd.columns, pd.MultiIndex):
                bd.columns = bd.columns.get_level_values(0)
            bd.index = _naive(bd.index)
            btc_daily = bd; break
        time.sleep(3)
except Exception as e:
    print(f"WARNUNG: BTC-Tagesdaten (yfinance) fehlgeschlagen: {e}")
if btc_daily is not None:
    rng = (btc_daily["High"] - btc_daily["Low"]) / btc_daily["Low"]
    btc_tage = [d.date() for d in btc_daily.index[rng >= TAGESRANGE_MIN]]
    print(f"BTC-Vorfilter: {len(btc_tage)} von {len(btc_daily)} Tagen mit Range "
          f">= {TAGESRANGE_MIN:.1%} (Trigger liegt bei {CASCADE_TRIG:.1%} -> Obermenge)")
else:
    print("WARNUNG: ohne BTC-Tagesdaten kein Vorfilter — K4/K4b entfallen.")

jobs = ([("GASCMDUSD", d) for d in gas_tage]
        + [("EURUSD", d) for d in eur_tage]
        + [("BTCUSD", d) for d in btc_tage])
print(f"\nLade {len(jobs)} Tagesdateien (GAS {len(gas_tage)}, EURUSD {len(eur_tage)}, "
      f"BTC {len(btc_tage)}) von Dukascopy ...")
roh = lade_viele(jobs)
if len(roh) < 500:
    sys.exit(f"ABBRUCH: nur {len(roh)} Dateien geladen. Meist Dukascopy-Rate-Limit — "
             "Zelle in 10-15 Min ERNEUT ausfuehren (Cache behaelt alles Geladene), "
             "sonst N_JOBS auf 2 senken.")
print("\nBaue Minutenframes:")
M = {i: baue_frame(roh, i) for i in ("GASCMDUSD", "EURUSD", "BTCUSD")}

# ------------------------------------------------------------------
# 4) HILFSFUNKTIONEN
# ------------------------------------------------------------------
def preis_um(m, tag_lokal, uhrzeit_min, tz, feld="close", fenster=10):
    """Letzter Preis <= uhrzeit_min (lokale tz) am Tag tag_lokal, sonst NaN."""
    if m is None: return np.nan
    ziel = pd.Timestamp(tag_lokal, tz=tz) + pd.Timedelta(minutes=uhrzeit_min)
    ziel_utc = ziel.tz_convert("UTC")
    fenster_df = m.loc[(m.index <= ziel_utc) &
                       (m.index > ziel_utc - pd.Timedelta(minutes=fenster))]
    return float(fenster_df[feld].iloc[-1]) if len(fenster_df) else np.nan

TRADES = {}     # name -> Liste (datum, rendite_netto)
def buche(name, datum, brutto, kosten):
    TRADES.setdefault(name, []).append((pd.Timestamp(datum), brutto - kosten, brutto))

# ------------------------------------------------------------------
# 5) DIE KANDIDATEN
# ------------------------------------------------------------------
# --- K1: EIA-Erdgas-Announcement (Reading-Paper: short 90 Min vor bis 30 Min nach) ---
# Mechanismus: Risikopraemie fuer das Halten von Ankuendigungsrisiko; Produzenten-
# Hedger zahlen sie, weil sie ihre Absicherung nicht ueber den Termin hinweg offen
# lassen wollen. >50% der Jahresrendite von Erdgas faellt auf Meldetage.
def k1_eia():
    m = M.get("GASCMDUSD")
    if m is None: return
    kosten = COST_BPS["GASCMDUSD"] / 1e4
    tage = sorted({d.date() for d in m.tz_convert("America/New_York").index})
    nach_woche = {}
    for d in tage:                       # je Kalenderwoche: Do, sonst Fr (Feiertag)
        iso = dt.date(d.year, d.month, d.day).isocalendar()[:2]
        if iso not in nach_woche or d.weekday() == 3:
            if iso not in nach_woche or nach_woche[iso].weekday() != 3:
                nach_woche[iso] = d
    for d in sorted(nach_woche.values()):
        if pd.Timestamp(d) >= QUARANTAENE_AB: continue
        p_ein = preis_um(m, d, 10*60+30 - EIA_VOR_MIN, "America/New_York")
        p_aus = preis_um(m, d, 10*60+30 + EIA_NACH_MIN, "America/New_York")
        if not (np.isfinite(p_ein) and np.isfinite(p_aus)): continue
        buche("K1 Erdgas EIA-Announcement (short)", d, -(p_aus/p_ein - 1), kosten)

# --- K2/K3: Monatsende-Hedge-Rebalancing am 16:00-London-Fix -------------------
# Mechanismus: Globale Aktienmanager haben mandatierte Waehrungs-Hedge-Quoten.
# Steigt der US-Markt im Monat, ist der USD-Hedge zu klein und muss zum Fix
# aufgestockt werden -> USD-Verkauf -> EURUSD steigt in den Fix hinein
# (Melvin/Prins 2015: 10% Aktienplus -> ~14 bps Waehrungsabwertung).
# K3 testet die Gegenprobe: temporaerer Preisdruck sollte nach dem Fix zurueckdrehen.
def k2_k3_monatsende(spx):
    m = M.get("EURUSD")
    if m is None or spx is None: return
    kosten = COST_BPS["EURUSD"] / 1e4
    tage = sorted({d.date() for d in m.tz_convert("Europe/London").index})
    per = pd.Series([pd.Timestamp(d).to_period("M") for d in tage], index=tage)
    for p in sorted(set(per)):
        monatstage = [d for d in tage if per[d] == p]
        letzter = monatstage[-1]
        spaeter = [d for d in tage if d > letzter]
        if not spaeter: continue
        if pd.Timestamp(letzter) >= QUARANTAENE_AB: continue
        # Signal: Aktien-Monatsrendite bis zum VORTAG (ex ante bekannt)
        vor = spx[spx.index < pd.Timestamp(letzter)]
        basis = spx[spx.index < pd.Timestamp(p.start_time)]
        if len(vor) == 0 or len(basis) == 0: continue
        mtd = vor.iloc[-1] / basis.iloc[-1] - 1
        if not np.isfinite(mtd) or mtd == 0: continue
        richtung = 1 if mtd > 0 else -1          # Aktien hoch -> USD-Verkauf -> EURUSD long
        p15 = preis_um(m, letzter, 15*60, "Europe/London")
        p16 = preis_um(m, letzter, 16*60, "Europe/London")
        if np.isfinite(p15) and np.isfinite(p16):
            buche("K2 EURUSD Monatsende-Fix (in den Fix)", letzter,
                  richtung * (p16/p15 - 1), kosten)
        p_next = preis_um(m, spaeter[0], 10*60, "Europe/London")
        if np.isfinite(p16) and np.isfinite(p_next):
            buche("K3 EURUSD Fix-Reversal (nach dem Fix)", letzter,
                  -richtung * (p_next/p16 - 1), kosten)

# --- K4 (+ K4b Kontrolle): Liquidationskaskaden-Reversion in BTC --------------
# Mechanismus: Perp-Boersen liquidieren zwangsweise per Market-Order, ohne
# Nachschusspflicht-Frist und bei 60x Durchschnittshebel; wer die Ware aufnimmt,
# wird fuer Inventarrisiko bezahlt. Taeglich werden ~3,5% aller Long-Positionen
# zwangsliquidiert (dokumentiert), in Kaskaden ein Vielfaches davon.
def k4_kaskaden(richtung, name):
    m = M.get("BTCUSD")
    if m is None: return
    kosten = COST_BPS["BTCUSD"] / 1e4
    for tag, g in m.groupby(m.index.date):
        if pd.Timestamp(tag) >= QUARANTAENE_AB: continue
        if len(g) < 600: continue
        # auf ein luckenloses Minutenraster bringen: shift(60) ist sonst
        # 60 ZEILEN und nicht 60 MINUTEN, sobald Bars fehlen
        raster = pd.date_range(g.index[0].floor("min"), g.index[-1].ceil("min"),
                               freq="1min", tz="UTC")
        c = g["close"].reindex(raster).ffill()
        r60 = c / c.shift(60) - 1
        kand = r60[(r60.abs() >= CASCADE_TRIG) & (r60.index.hour >= 1)]
        kand = kand[kand.notna()]
        if len(kand) == 0: continue
        t0 = kand.index[0]                        # erster Trigger des Tages
        seite = -np.sign(kand.iloc[0]) * richtung # richtung=+1: fade, -1: Momentum
        entry = float(c.loc[t0])
        pfad = g.loc[(g.index > t0) & (g.index <= t0 + pd.Timedelta(hours=CASCADE_HOLD_H))]
        if len(pfad) < 30: continue
        stop = entry * (1 - CASCADE_STOP * seite)
        if seite > 0:
            hit = np.where(pfad["low"].values <= stop)[0]
        else:
            hit = np.where(pfad["high"].values >= stop)[0]
        if len(hit):
            fill = pfad["open"].values[hit[0]]
            fill = min(stop, fill) if seite > 0 else max(stop, fill)  # Gap-Fill
            brutto = seite * (fill/entry - 1); k = kosten * 2         # Stop-Slippage
        else:
            brutto = seite * (float(pfad["close"].iloc[-1])/entry - 1); k = kosten
        buche(name, t0.date(), brutto, k)

# --- Aktienindex-Tagesdaten fuer K2/K3 ---------------------------------------
spx = None
try:
    import yfinance as yf
    for versuch in range(3):
        sd = yf.download("^GSPC", start=str(START_EUR), end=str(DATEN_ENDE),
                         auto_adjust=True, progress=False)
        if len(sd) > 500:
            c = sd["Close"]
            if isinstance(c, pd.DataFrame): c = c.iloc[:, 0]
            c.index = _naive(c.index)
            spx = c; break
        time.sleep(3)
except Exception as e:
    print(f"WARNUNG: S&P-500-Daten fehlgeschlagen ({e}) — K2/K3 entfallen.")
if spx is None:
    print("WARNUNG: keine S&P-500-Daten — K2/K3 ohne Ergebnis.")

print("\nRechne Strategien ...")
k1_eia()
k2_k3_monatsende(spx)
k4_kaskaden(+1, "K4 BTC Liquidationskaskade (Reversion)")
k4_kaskaden(-1, "K4b KONTROLLE: dieselbe Kaskade als Momentum")

# ------------------------------------------------------------------
# 6) KENNZAHLEN
# ------------------------------------------------------------------
def kennzahlen(name, trades):
    if len(trades) < 5:
        return {"Idee": name, "Trades": len(trades), "Sharpe": np.nan, "t-Stat": np.nan,
                "Rendite %/J": np.nan, "MaxDD %": np.nan, "Hit %": np.nan,
                "Kosten/Brutto %": np.nan}
    df = pd.DataFrame(trades, columns=["datum", "netto", "brutto"]).sort_values("datum")
    r = df["netto"].values
    spanne = max((df["datum"].iloc[-1] - df["datum"].iloc[0]).days / 365.25, 0.5)
    pro_jahr = len(r) / spanne
    eq = np.cumprod(1 + r)
    sharpe = r.mean()/r.std()*math.sqrt(pro_jahr) if r.std() > 0 else np.nan
    tstat  = r.mean()/r.std()*math.sqrt(len(r))   if r.std() > 0 else np.nan
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    bs = df["brutto"].sum()
    kosten_anteil = (df["brutto"].sum() - df["netto"].sum()) / bs if bs > 0 else np.inf
    return {"Idee": name, "Trades": len(r), "Sharpe": sharpe, "t-Stat": tstat,
            "Rendite %/J": (eq[-1] ** (1/spanne) - 1) * 100, "MaxDD %": dd * 100,
            "Hit %": (r > 0).mean() * 100,
            "Kosten/Brutto %": min(kosten_anteil, 9.99) * 100}

reihenfolge = ["K1 Erdgas EIA-Announcement (short)",
               "K2 EURUSD Monatsende-Fix (in den Fix)",
               "K3 EURUSD Fix-Reversal (nach dem Fix)",
               "K4 BTC Liquidationskaskade (Reversion)",
               "K4b KONTROLLE: dieselbe Kaskade als Momentum"]
tab = pd.DataFrame([kennzahlen(n, TRADES.get(n, [])) for n in reihenfolge]).set_index("Idee")
tab = tab.sort_values("Sharpe", ascending=False)

SCHWELLE = 1.2      # 13 Ideen ueber beide Screening-Runden -> strengste Stufe
tab["Urteil"] = np.where(tab["Sharpe"] >= SCHWELLE, "PROMOTE-Kandidat", "-")
tab.loc[tab.index.str.startswith("K4b"), "Urteil"] = "(Kontrolle, nie PROMOTE)"

pd.set_option("display.width", 170)
print("\n" + "=" * 104)
print(f"TRIAGE II — Training bis {QUARANTAENE_AB.date()}, Kosten je Instrument "
      f"{COST_BPS}")
print(f"4 Ideen + 1 Kontrolle getestet (Runde 2; kumuliert 12 Ideen ueber beide "
      f"Runden) -> PROMOTE-Schwelle Sharpe >= {SCHWELLE}")
print("=" * 104)
print(tab.round(2).to_string())
print("-" * 104)
print(f"QUARANTAENE unangetastet ab {QUARANTAENE_AB.date()} — genau EINMAL in /colab "
      "verschiessen.")
print("Lesehilfe: K4 zaehlt nur, wenn K4b (dieselbe Kaskade in Gegenrichtung) klar")
print("schlechter ist — sonst misst K4 nur Volatilitaet, keine Reversion. t-Stat < 2")
print("heisst: zu wenige Events fuer eine Aussage, unabhaengig vom Sharpe.")
