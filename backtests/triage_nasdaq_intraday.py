# =========================================================================
# TRIAGE-BACKTEST: 8 Nasdaq-100-Intraday-Kandidaten in einem Lauf
# (aus /screen vom 2026-09-01; volle Validierung spaeter via /colab)
#
# Daten:    Dukascopy USATECH.IDX/USD (Nasdaq-100-CFD), 1-Minuten-BID-Kerzen
#           ab 2012, frei und ohne Registrierung
# Kosten:   1,0 bps Round-Trip pro Trade (MNQ ~0,4 bps + Puffer),
#           Stop-Exits zusaetzlich 1,0 bps Slippage; Stops fuellen bei
#           Gaps zum Open der ausloesenden Bar (konservativ)
# Holdout:  Datenende ist FEST auf DATEN_ENDE gepinnt, damit die
#           Quarantaene-Grenze (juengste 30 % der Sessions) ueber
#           Wiederholungslaeufe stabil bleibt. Der Quarantaene-Zeitraum
#           wird hier NIE angefasst — er gehoert dem einen /colab-Test.
# Regeln:   EIN fester Parametersatz pro Idee, kein Sweep, keine Optimierung.
#           Signale nutzen ausschliesslich Information vor dem Einstieg.
# Laufzeit: erste Ausfuehrung ~5-10 Min (Download ~3.800 Tagesdateien),
#           danach <1 Min dank Cache in /content/dk_cache
# =========================================================================

import warnings, os, lzma, time, math, sys
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
START            = dt.date(2012, 1, 2)   # Dukascopy-m1-Historie beginnt 2011-09
DATEN_ENDE       = dt.date(2026, 8, 28)  # FEST GEPINNT: haelt die Holdout-Grenze
                                         # ueber alle Laeufe stabil. Nur bewusst
                                         # aendern — /colab nutzt dieselbe Grenze.
HOLDOUT_FRAC     = 0.30                  # juengste 30% der Sessions = Quarantaene
COST_RT_BPS      = 1.0                   # Round-Trip-Kosten pro Trade (MNQ + Puffer)
STOP_SLIP_BPS    = 1.0                   # Zusatz-Slippage, wenn ein Stop ausloest
SUBSAMPLE_START  = "2018-01-01"          # zweite Sharpe-Spalte (Regime-Check)
N_JOBS           = 48                    # parallele Downloads
CACHE_DIR        = "/content/dk_cache"   # Rohdaten-Cache (ausserhalb Colab: ./dk_cache)
INSTRUMENT       = "USATECHIDXUSD"       # Nasdaq-100-CFD im Dukascopy-Datafeed

# Feste Parameter der 8 Ideen (EIN Satz, begruendet, kein Sweep):
R1_THRESH    = 0.004    # S1: |Rendite 09:30-10:00| >= 0,4% ~ starke Eroeffnungshalbstunde
ORB_TP_R     = 10.0     # S2: Take-Profit bei 10R (Zarattini/Aziz 2023, Originalwert)
LETF_THRESH  = 0.010    # S6: |Tagesrendite bis 15:30| >= 1% loest LETF-Rebalancing aus
MARGIN_PREV  = -0.03    # S8: Vortag <= -3%
MARGIN_GAP   = -0.005   # S8: Open >= 0,5% unter Vortagesschluss
MARGIN_STOP  = -0.015   # S8: Stop-Loss -1,5% vom Einstieg
DIV_THRESH   = 3.0      # S7: |NDX-TLT-Monatsdivergenz| > 3 Prozentpunkte

if not os.path.isdir("/content"):
    CACHE_DIR = "./dk_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

print("ANNAHMEN: 1-Min-BID-Kerzen Dukascopy (CFD-Quotes ~ CME-Preis); Ausfuehrung zu")
print(f"Bar-Preisen; {COST_RT_BPS} bps Round-Trip + {STOP_SLIP_BPS} bps Stop-Slippage;")
print("Stops fuellen bei Gaps zum Open der ausloesenden Bar; keine Optimierung —")
print(f"ein fester Parametersatz pro Idee; Datenende gepinnt auf {DATEN_ENDE};")
print(f"juengste {int(HOLDOUT_FRAC*100)}% der Historie quarantaeniert fuer /colab.\n")

# ------------------------------------------------------------------
# 2) DATENBESCHAFFUNG — Dukascopy-Tagesdateien (Monat im Pfad 0-indexiert!)
# ------------------------------------------------------------------
def tage_liste():
    d, out = START, []
    while d <= DATEN_ENDE:
        if d.weekday() < 5:              # Sa/So haben keine US-Session
            out.append(d)
        d += dt.timedelta(days=1)
    return out

def lade_tag(d):
    """Laedt eine Tagesdatei (Cache zuerst). Rueckgabe: (datum, bytes|None)."""
    fn = os.path.join(CACHE_DIR, f"{d.isoformat()}.bi5")
    if os.path.exists(fn):
        with open(fn, "rb") as f:
            raw = f.read()
        return d, (raw if raw else None)  # 0-Byte-Datei = bekannter Feiertag
    url = (f"https://datafeed.dukascopy.com/datafeed/{INSTRUMENT}/"
           f"{d.year}/{d.month-1:02d}/{d.day:02d}/BID_candles_min_1.bi5")
    for versuch in range(3):
        try:
            r = requests.get(url, timeout=25)
            if r.status_code == 404 or (r.status_code == 200 and len(r.content) == 0):
                # Nur als Feiertag cachen, wenn der Tag sicher publiziert ist —
                # sonst wuerde ein noch fehlender junger Tag dauerhaft fehlen.
                if (dt.date.today() - d).days >= 4:
                    tmp = fn + ".tmp"
                    open(tmp, "wb").close()
                    os.replace(tmp, fn)
                return d, None
            if r.status_code == 200:
                tmp = fn + ".tmp"        # atomar schreiben: nie halbe Dateien cachen
                with open(tmp, "wb") as f:
                    f.write(r.content)
                os.replace(tmp, fn)
                return d, r.content
        except requests.RequestException:
            pass
        time.sleep(1 + versuch)
    return d, None                        # nach 3 Versuchen aufgeben (Luecke)

tage = tage_liste()
print(f"Lade {len(tage)} Handelstage {START} .. {DATEN_ENDE} von Dukascopy ...")
rohdaten, fertig, t0 = {}, 0, time.time()
with ThreadPoolExecutor(max_workers=N_JOBS) as ex:
    futs = {ex.submit(lade_tag, d): d for d in tage}
    for fut in as_completed(futs):
        d, raw = fut.result()
        if raw:
            rohdaten[d] = raw
        fertig += 1
        if fertig % max(1, len(tage)//10) == 0:
            print(f"  {fertig}/{len(tage)} Dateien, {len(rohdaten)} mit Daten "
                  f"({time.time()-t0:.0f}s)")

if len(rohdaten) < 1500:
    sys.exit(f"ABBRUCH: nur {len(rohdaten)} Tagesdateien mit Daten — Dukascopy nicht "
             "erreichbar oder Instrumentcode falsch. Bitte spaeter erneut versuchen.")

# --- Binaerformat: 24 Bytes/Record, Big-Endian.
#     Dokumentiert: [Sek-Offset ab 00:00 UTC, Open, Close, Low, High, Volumen].
#     Die OCLH-Reihenfolge wird gegen die OHLC-Alternative verifiziert.
DT_OCLH = np.dtype([("t", ">u4"), ("o", ">u4"), ("c", ">u4"),
                    ("l", ">u4"), ("h", ">u4"), ("v", ">f4")])
DT_OHLC = np.dtype([("t", ">u4"), ("o", ">u4"), ("h", ">u4"),
                    ("l", ">u4"), ("c", ">u4"), ("v", ">f4")])

def entpacke(raw, dtype):
    dec = lzma.decompress(raw)
    n = len(dec) // 24
    return np.frombuffer(dec[:n*24], dtype=dtype)

def ohlc_ok(a):
    o, c, l, h = (a["o"].astype(float), a["c"].astype(float),
                  a["l"].astype(float), a["h"].astype(float))
    return np.mean((h >= np.maximum(o, c)) & (l <= np.minimum(o, c)))

# Probe deterministisch aus den AELTESTEN Tagen (reproduzierbar, Training only)
probe, FORMAT = None, None
for d in sorted(rohdaten)[:5]:
    try:
        kand = entpacke(rohdaten[d], DT_OCLH)
    except lzma.LZMAError:
        continue
    if len(kand) < 100:
        continue
    FORMAT = DT_OCLH if ohlc_ok(kand) > 0.95 else DT_OHLC
    probe = entpacke(rohdaten[d], FORMAT)
    break
assert probe is not None and ohlc_ok(probe) > 0.95, \
    "ABBRUCH: Kerzenformat unbekannt — weder OCLH noch OHLC passt."

# Preisskalierung: dokumentiert /1000; zur Sicherheit verifizieren.
SKALA = 1000.0
med = np.median(probe["c"]) / SKALA
if not (1000 < med < 100000):
    for s in (1.0, 10.0, 100.0, 10000.0, 100000.0):
        if 1000 < np.median(probe["c"]) / s < 100000:
            SKALA = s; break
print(f"Kerzenformat: {'OCLH' if FORMAT is DT_OCLH else 'OHLC'}, "
      f"Preisskalierung: /{SKALA:.0f}")

frames, kaputt = [], []
for d, raw in sorted(rohdaten.items()):
    try:
        a = entpacke(raw, FORMAT)
    except lzma.LZMAError:                # korrupten Cache loeschen -> Re-Download
        fn = os.path.join(CACHE_DIR, f"{d.isoformat()}.bi5")
        if os.path.exists(fn):
            os.remove(fn)
        kaputt.append(d)
        continue
    if len(a) == 0:
        continue
    ts = (pd.Timestamp(d, tz="UTC") + pd.to_timedelta(a["t"], unit="s"))
    frames.append(pd.DataFrame({
        "open": a["o"]/SKALA, "high": a["h"]/SKALA,
        "low":  a["l"]/SKALA, "close": a["c"]/SKALA}, index=ts))
if kaputt:
    print(f"WARNUNG: {len(kaputt)} korrupte Cache-Dateien geloescht — naechster Lauf "
          f"laedt sie neu: {[str(x) for x in kaputt[:5]]} ...")
m1 = pd.concat(frames).sort_index()
m1 = m1[~m1.index.duplicated(keep="last")]
m1.index = m1.index.tz_convert("America/New_York")
print(f"{len(m1):,} Minutenbars, {m1.index[0]} .. {m1.index[-1]}")

# ------------------------------------------------------------------
# 3) SESSION-FRAMES — Ankerpreise je US-Handelstag (NY-Zeit)
# ------------------------------------------------------------------
tod = m1.index.hour * 60 + m1.index.minute          # Minuten seit Mitternacht NY
m1["ny_date"] = m1.index.date
rth = m1[(tod >= 9*60+30) & (tod < 16*60)].copy()
rth_tod = rth.index.hour * 60 + rth.index.minute

# --- Voll-Frame ALLER Tage mit RTH-Bars (inkl. Halbtage mit 13:00-Schluss).
#     Nur so referenziert prev_close den echten letzten Schlusskurs statt
#     ueber verworfene Tage hinweg Phantom-Mehrtagesrenditen zu erzeugen.
S_full = pd.DataFrame({
    "close_last": rth.groupby("ny_date")["close"].last(),
    "bars":       rth.groupby("ny_date")["close"].count(),
})
S_full.index = pd.to_datetime(S_full.index)
S_full = S_full.sort_index()
S_full["prev_close"]    = S_full["close_last"].shift(1)
S_full["prev_bars"]     = S_full["bars"].shift(1)
S_full["gap_tage"]      = S_full.index.to_series().diff().dt.days
S_full["ret_full"]      = S_full["close_last"].pct_change()
# Renditen ueber Datenluecken (>4 Kalendertage: mehr als Wochenende+Feiertag)
# sind keine Eintagesrenditen -> maskieren, damit kein Trigger darauf feuert.
S_full.loc[S_full["gap_tage"] > 4, ["ret_full", "prev_close"]] = np.nan
S_full["prev_ret"] = S_full["ret_full"].shift(1)     # Vortagesrendite, ex ante bekannt

def letzter_vor(minute, feld="close", fenster=15):
    """Letzter Preis mit Uhrzeit < `minute` (und >= minute-fenster), je Session."""
    sel = rth[(rth_tod < minute) & (rth_tod >= minute - fenster)]
    return sel.groupby("ny_date")[feld].last()

def erster_ab(minute, feld="open", fenster=5):
    sel = rth[(rth_tod >= minute) & (rth_tod < minute + fenster)]
    return sel.groupby("ny_date")[feld].first()

S = pd.DataFrame({
    "open0930":  erster_ab(9*60+30),
    "p1000":     letzter_vor(10*60),
    "p1200":     letzter_vor(12*60),
    "p1400":     letzter_vor(14*60),
    "p1530":     letzter_vor(15*60+30),
    "p1555":     letzter_vor(15*60+55),
    "p1558":     letzter_vor(15*60+58, fenster=5),
    "close1600": letzter_vor(16*60, fenster=10),
})
# ORB-Kerze 09:30-09:35
orb_sel = rth[(rth_tod >= 9*60+30) & (rth_tod < 9*60+35)]
S["orb_o"] = orb_sel.groupby("ny_date")["open"].first()
S["orb_h"] = orb_sel.groupby("ny_date")["high"].max()
S["orb_l"] = orb_sel.groupby("ny_date")["low"].min()
S["orb_c"] = orb_sel.groupby("ny_date")["close"].last()

S.index = pd.to_datetime(S.index)
S = S.sort_index()
S = S.join(S_full[["bars", "prev_close", "prev_bars", "gap_tage", "prev_ret"]])
# Volle Sessions: genug Bars + Eroeffnung + echter 16:00-Schluss (Halbtage raus)
S = S[(S["bars"] >= 250) & S["open0930"].notna() & S["close1600"].notna()]

# Pfad-Arrays je Session fuer die Stop-Simulationen (S2, S8)
pfad = {}
for d, g in rth.groupby("ny_date"):
    gt = g.index.hour*60 + g.index.minute
    pfad[pd.Timestamp(d)] = (gt.values, g["high"].values, g["low"].values,
                             g["close"].values, g["open"].values)

# --- HOLDOUT-QUARANTAENE: juengste 30% NIE anfassen -----------------
n_cut = int(len(S) * (1 - HOLDOUT_FRAC))
QUARANTAENE_AB = S.index[n_cut]
train = S.iloc[:n_cut].copy()
train_full = S_full[S_full.index < QUARANTAENE_AB]   # fuer S4 (inkl. Halbtage)
print(f"\n{len(S)} volle Sessions. TRAINING: {train.index[0].date()} .. "
      f"{train.index[-1].date()}  |  QUARANTAENE (nur fuer /colab): ab "
      f"{QUARANTAENE_AB.date()} ({len(S)-n_cut} Sessions)\n")

COST  = COST_RT_BPS / 1e4
SLIP  = STOP_SLIP_BPS / 1e4

# ------------------------------------------------------------------
# 4) DIE 8 KANDIDATEN — jede Funktion liefert (Tagesrenditen, Kosten, Bruttoserie)
# ------------------------------------------------------------------
def leer():
    z = pd.Series(0.0, index=train.index)
    return z.copy(), z.copy(), z.copy()

def stop_fill(stop, bar_open, dir_):
    """Konservativer Stop-Fill: gappt die ausloesende Bar durch den Stop,
    wird zum schlechteren Open gefuellt statt zum Stop-Preis."""
    return min(stop, bar_open) if dir_ > 0 else max(stop, bar_open)

# S1 — Market Intraday Momentum (Gao et al. 2018): 09:30-10:00 prognostiziert
#      Schlusshalbstunde. Schwelle 0,4% = grob halbe mittlere Eroeffnungsrange.
def s1_intraday_momentum():
    ret, cost, brutto = leer()
    r1 = train["p1000"] / train["prev_close"] - 1     # NaN bei Datenluecke -> kein Trade
    dir_ = np.where(r1 >= R1_THRESH, 1, np.where(r1 <= -R1_THRESH, -1, 0))
    g = dir_ * (train["close1600"] / train["p1530"] - 1)
    aktiv = (dir_ != 0) & g.notna()
    brutto[aktiv] = g[aktiv]
    cost[aktiv] = COST
    ret[aktiv] = g[aktiv] - COST
    return ret, cost, brutto

# S2 — Opening Range Breakout 5-Min (Zarattini/Aziz 2023): Richtung der ersten
#      5-Min-Kerze, Entry 09:35, Stop am Kerzenextrem, TP 10R, sonst Exit 16:00.
def s2_orb():
    ret, cost, brutto = leer()
    for d in train.index:
        row = train.loc[d]
        if not np.isfinite(row["orb_o"]) or not np.isfinite(row["orb_c"]):
            continue
        dir_ = np.sign(row["orb_c"] - row["orb_o"])
        if dir_ == 0:
            continue
        t, hi, lo, cl, op = pfad[d]
        nach = t >= 9*60+35
        if nach.sum() < 10:
            continue
        entry = op[nach][0]
        stop  = row["orb_l"] if dir_ > 0 else row["orb_h"]
        if dir_ * (entry - stop) <= 0:     # Entry gappt schon jenseits des Stops
            continue                       # -> Trade kommt real nie zustande
        R  = abs(entry - stop)
        tp = entry + dir_ * ORB_TP_R * R
        hi_n, lo_n, op_n = hi[nach], lo[nach], op[nach]
        stop_hit = np.where(lo_n <= stop)[0] if dir_ > 0 else np.where(hi_n >= stop)[0]
        tp_hit   = np.where(hi_n >= tp)[0]   if dir_ > 0 else np.where(lo_n <= tp)[0]
        i_stop = stop_hit[0] if len(stop_hit) else 10**9
        i_tp   = tp_hit[0]   if len(tp_hit)   else 10**9
        if i_stop <= i_tp and i_stop < 10**9:      # Stop zuerst (konservativ)
            fill = stop_fill(stop, op_n[i_stop], dir_)
            g = dir_ * (fill / entry - 1); extra = SLIP
        elif i_tp < 10**9:
            g = dir_ * (tp / entry - 1);   extra = 0.0
        else:
            g = dir_ * (row["close1600"] / entry - 1); extra = 0.0
        brutto[d] = g
        cost[d] = COST + extra
        ret[d] = g - COST - extra
    return ret, cost, brutto

# S3 — Third-Friday-OPEX-Reversal (Baltussen et al. 2023): verzerrter
#      3.-Freitag-Open revertiert bis Mittag -> Short 09:30-12:00.
def s3_opex():
    ret, cost, brutto = leer()
    idx = train.index
    for (y, m), _ in train.groupby([train.index.year, train.index.month]):
        erster = dt.date(y, m, 1)
        dritter_fr = pd.Timestamp(erster) + pd.Timedelta(days=(4 - erster.weekday()) % 7 + 14)
        if dritter_fr > idx[-1]:           # echter OPEX-Tag laege in der Quarantaene
            continue
        kand = idx[(idx <= dritter_fr) & (idx > dritter_fr - pd.Timedelta(days=5))]
        if len(kand) == 0:
            continue
        d = kand[-1]                       # Feiertagsverschiebung: letzter Handelstag davor
        row = train.loc[d]
        if np.isfinite(row["p1200"]) and np.isfinite(row["open0930"]):
            g = -(row["p1200"] / row["open0930"] - 1)
            brutto[d] = g; cost[d] = COST; ret[d] = g - COST
    return ret, cost, brutto

# S4 — Turn-of-Month (McConnell/Xu 2008): long letzter Handelstag ~15:55 bis
#      3. Handelstag des Folgemonats. ACHTUNG: haelt uebernacht (Overlay, kein
#      reines Daytrading). Rechnet auf dem Voll-Kalender inkl. Halbtagen;
#      Kosten einmal pro Fenster. Ergebnis wird auf das Trainingsraster gebucht.
def s4_tom():
    ret, cost, brutto = leer()
    monat = train_full.index.to_period("M")
    for p in monat.unique()[:-1]:          # letzter (evtl. angeschnittener) Monat faellt weg
        naechste = train_full.index[monat == p + 1]
        halte = naechste[:3]
        if len(halte) < 3:
            continue
        for i, d in enumerate(halte):
            g = train_full.loc[d, "ret_full"]
            if not np.isfinite(g):
                continue
            buchung = d if d in ret.index else None
            if buchung is None:            # Halbtag: auf naechster Trainingssession buchen
                nachher = ret.index[ret.index > d]
                if len(nachher) == 0:
                    continue
                buchung = nachher[0]
            brutto[buchung] += g
            c = COST if i == 0 else 0.0
            cost[buchung] += c
            ret[buchung] += g - c
    return ret, cost, brutto

# S5 — Overnight-Praemie (Cooper et al. 2008): taeglich long 15:59 -> 09:30
#      des Folgetags, tagsueber flat. Kostenintensivster Kandidat (250 RT/Jahr).
#      Nur nach VOLLEN Vortagen (an Halbtagen gibt es keinen 15:59-Einstieg).
def s5_overnight():
    ret, cost, brutto = leer()
    g = train["open0930"] / train["prev_close"] - 1
    ok = g.notna() & (train["prev_bars"] >= 250)
    brutto[ok] = g[ok]
    cost[ok] = COST
    ret[ok] = g[ok] - COST
    return ret, cost, brutto

# S6 — Leveraged-ETF-Rebalancing (Cheng/Madhavan 2009): |Tagesrendite bis
#      15:30| >= 1% -> letzte halbe Stunde in Trendrichtung, Exit 15:58.
def s6_letf():
    ret, cost, brutto = leer()
    r15 = train["p1530"] / train["prev_close"] - 1
    dir_ = np.where(r15 >= LETF_THRESH, 1, np.where(r15 <= -LETF_THRESH, -1, 0))
    g = dir_ * (train["p1558"] / train["p1530"] - 1)
    aktiv = (dir_ != 0) & g.notna()
    brutto[aktiv] = g[aktiv]
    cost[aktiv] = COST
    ret[aktiv] = g[aktiv] - COST
    return ret, cost, brutto

# S7 — Monatsultimo-Rebalancing (Etula et al. 2020): starke NDX/TLT-Monats-
#      divergenz -> kontra 14:00-15:55 am letzten Handelstag. Braucht TLT-Tagesdaten.
def s7_ultimo(tlt):
    ret, cost, brutto = leer()
    if tlt is None:
        return ret, cost, brutto
    tlt_c = tlt.reindex(train.index.normalize(), method="ffill")
    tlt_c.index = train.index
    monat = train.index.to_period("M")
    for p in monat.unique():
        if not (monat == p + 1).any():     # angeschnittener letzter Monat: kein echter Ultimo
            continue
        tage_m = train.index[monat == p]
        d = tage_m[-1]                     # letzter voller Handelstag des Monats
        vortage = train.index[train.index < d]
        vormonat = train.index[monat < p]
        if len(vortage) == 0 or len(vormonat) == 0:
            continue
        d_vor, d_base = vortage[-1], vormonat[-1]    # bis Vortagesschluss (ex ante)
        ndx_mtd = train.loc[d_vor, "close1600"] / train.loc[d_base, "close1600"] - 1
        tlt_mtd = tlt_c.loc[d_vor] / tlt_c.loc[d_base] - 1
        div = (ndx_mtd - tlt_mtd) * 100
        if not np.isfinite(div) or abs(div) <= DIV_THRESH:
            continue
        dir_ = -1 if div > 0 else 1
        row = train.loc[d]
        if np.isfinite(row["p1400"]) and np.isfinite(row["p1555"]):
            g = dir_ * (row["p1555"] / row["p1400"] - 1)
            brutto[d] = g; cost[d] = COST; ret[d] = g - COST
    return ret, cost, brutto

# S8 — Rebound nach Margin-Zwangsverkaeufen: Vortag <= -3% UND Open >= 0,5%
#      unter Vortagesschluss -> long 10:00, Stop -1,5%, Exit 15:55.
def s8_margin_rebound():
    ret, cost, brutto = leer()
    gap = train["open0930"] / train["prev_close"] - 1
    trigger = ((train["prev_ret"] <= MARGIN_PREV) & (gap <= MARGIN_GAP)
               & (train["prev_bars"] >= 250))
    for d in train.index[trigger.fillna(False)]:
        row = train.loc[d]
        entry = row["p1000"]
        if not np.isfinite(entry):
            continue
        t, hi, lo, cl, op = pfad[d]
        nach = (t >= 10*60) & (t < 15*60+55)     # Stop-Fenster endet am 15:55-Exit
        stop = entry * (1 + MARGIN_STOP)
        lo_n, op_n = lo[nach], op[nach]
        stop_hit = np.where(lo_n <= stop)[0]
        if len(stop_hit):
            fill = stop_fill(stop, op_n[stop_hit[0]], 1)
            g = fill / entry - 1; extra = SLIP
        else:
            g = row["p1555"] / entry - 1; extra = 0.0
        if not np.isfinite(g):
            continue
        brutto[d] = g; cost[d] = COST + extra; ret[d] = g - COST - extra
    return ret, cost, brutto

# --- TLT fuer S7 (yfinance, mit Retry; bei Fehlschlag wird S7 uebersprungen)
tlt = None
try:
    import yfinance as yf
    for versuch in range(3):
        df_tlt = yf.download("TLT", start=str(START), end=str(DATEN_ENDE),
                             auto_adjust=True, progress=False)
        if len(df_tlt) > 500:
            c = df_tlt["Close"]
            if isinstance(c, pd.DataFrame):
                c = c.iloc[:, 0]
            c.index = pd.to_datetime(c.index).tz_localize(None)
            tlt = c
            break
        time.sleep(3)
except Exception as e:
    print(f"WARNUNG: TLT-Download fehlgeschlagen ({e}) — S7 wird uebersprungen.")
if tlt is None:
    print("WARNUNG: keine TLT-Daten — S7 (Monatsultimo-Divergenz) ohne Ergebnis.")

# ------------------------------------------------------------------
# 5) KENNZAHLEN + TABELLE
# ------------------------------------------------------------------
def kennzahlen(name, ret, cost, brutto):
    ret, brutto = ret.fillna(0), brutto.fillna(0)
    cost = cost.where(brutto != 0, 0.0).fillna(0)    # keine Kosten ohne Trade
    n_jahre = len(ret) / 252
    aktiv = brutto != 0
    equity = (1 + ret).cumprod()
    cagr = equity.iloc[-1] ** (1 / n_jahre) - 1 if n_jahre > 0 else np.nan
    sharpe = ret.mean() / ret.std() * math.sqrt(252) if ret.std() > 0 else np.nan
    dd = (equity / equity.cummax() - 1).min()
    sub = ret[ret.index >= SUBSAMPLE_START]
    sharpe_sub = sub.mean() / sub.std() * math.sqrt(252) if sub.std() > 0 else np.nan
    brutto_sum = brutto.sum()
    kostenanteil = cost.sum() / brutto_sum if brutto_sum > 0 else np.inf
    trades = int(aktiv.sum())
    hit = (ret[aktiv] > 0).mean() if trades else np.nan
    return {"Idee": name, "Sharpe": sharpe, f"Sharpe ab {SUBSAMPLE_START[:4]}": sharpe_sub,
            "CAGR %": cagr * 100, "MaxDD %": dd * 100, "Trades": trades,
            "Hit %": hit * 100 if trades else np.nan,
            "Kosten/Brutto %": min(kostenanteil, 9.99) * 100}

laeufe = [
    ("S1 Intraday-Momentum 15:30",  s1_intraday_momentum()),
    ("S2 ORB 5-Min (Zarattini)",    s2_orb()),
    ("S3 OPEX 3.-Freitag-Reversal", s3_opex()),
    ("S4 Turn-of-Month (Overlay)",  s4_tom()),
    ("S5 Overnight-Praemie",        s5_overnight()),
    ("S6 LETF-Schluss-Momentum",    s6_letf()),
    ("S7 Ultimo NDX/TLT-Divergenz", s7_ultimo(tlt)),
    ("S8 Margin-Crash-Rebound",     s8_margin_rebound()),
]
tab = pd.DataFrame([kennzahlen(n, *r) for n, r in laeufe]).set_index("Idee")
tab = tab.sort_values("Sharpe", ascending=False)

# Multiplizitaet: 8 Ideen getestet -> PROMOTE erst ab Sharpe 1.2 (siehe /screen).
SCHWELLE = 1.2
tab["Urteil"] = np.where(tab["Sharpe"] >= SCHWELLE, "PROMOTE-Kandidat", "-")

pd.set_option("display.width", 160)
print("\n" + "=" * 100)
print(f"TRIAGE-ERGEBNIS — Training {train.index[0].date()} .. {train.index[-1].date()}, "
      f"Kosten {COST_RT_BPS} bps RT")
print(f"8 Ideen getestet (12 versucht, 3 starben am Mechanismus-Gate) "
      f"-> PROMOTE-Schwelle: Sharpe >= {SCHWELLE}")
print("=" * 100)
print(tab.round(2).to_string())
print("-" * 100)
print(f"QUARANTAENE unangetastet: ab {QUARANTAENE_AB.date()} — wird genau EINMAL in "
      "/colab verschossen.")
print("Interpretation: Ein PROMOTE-Kandidat zaehlt nur, wenn auch die Spalte 'Sharpe ab "
      f"{SUBSAMPLE_START[:4]}' nicht kollabiert (Regime-Zerfall). Knapp unter der Schwelle "
      "= Erwartungswert von Zufall bei 8 Versuchen, kein Ergebnis.")
