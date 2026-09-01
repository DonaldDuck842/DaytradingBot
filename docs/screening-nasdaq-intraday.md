# Ideen-Screening: Nasdaq 100 Intraday (2026-09-01)

Sperrliste: `/areas/quant-trading.md` war in dieser Session nicht verfügbar — keine gesperrten
Ideen, keine früheren Screens dieses Markts angerechnet.

**Trichter:** 12 Rohideen → 11 nach Merge → 8 nach Mechanismus-Gate (3 Kills) → 8 nach
Kosten-Gate (0 Kills — Index-Futures sind zu billig, als dass das Kostengate hier tötet) →
**8 im Triage-Backtest**. PROMOTE-Schwelle bei 8 getesteten Ideen: **Sharpe ≥ 1,2**
(Multiplizitätskorrektur; ein knappes Reißen der Schwelle ist der Erwartungswert von Zufall).

## Getestete Kandidaten (Triage: `backtests/triage_nasdaq_intraday.py`)

| # | Idee | Mechanismus („Wer zahlt?") | Edge/Kosten | Trades/J. | Skeptiker |
|---|---|---|---|---|---|
| S1 | Intraday-Momentum: 09:30–10:00 ≥ ±0,4 % → Position 15:30–16:00 | Zwang: LETF-Rebalancing, Gamma-Hedging, VWAP-Restorders zum Schluss | 2,5 bps / 0,4 bps ≈ 6 | ~90 | wackelt (Gamma-Vorzeichen regimeabhängig, Post-Publikations-Zerfall) |
| S2 | ORB 5-Min (Zarattini/Aziz 2023): Richtung der ersten Kerze, Stop am Extrem, TP 10R | Verhaltensmuster: systematisches Faden newsgetriebener Eröffnungen | 3 bps / 0,55 bps ≈ 5,5 | ~230 | wackelt (Stop-Slippage-sensitiv, Sample 2020–22-lastig) |
| S3 | OPEX-Reversal: 3. Freitag Short 09:30→12:00 | Zwang: AM-Settlement/Charm-Flows verzerren den Verfalls-Open (Baltussen et al. 2023) | 8 bps / 0,4 bps ≈ 20 | 12 | wackelt (SPX→NDX-Extrapolation ungetestet) |
| S4 | Turn-of-Month: long letzter Handelstag → 3. Tag Folgemonat (Overlay, hält übernacht) | Gebündelte preisunempfindliche Zuflüsse (Gehalts-/Fondszyklus) | 25 bps / 0,4 bps ≈ 62 | 12 | wackelt (Zufluss-Kanal unbelegt, aber 35 J. OOS-Persistenz) |
| S5 | Overnight-Prämie: long 15:59 → 09:30, tagsüber flat | Risikoprämie für nicht hedgebares Gap-Risiko | 4 bps / 0,4 bps ≈ 10 | ~250 | wackelt (NY-Fed: seit 2021 nahe null → Subsample-Spalte entscheidet) |
| S6 | LETF-Schluss-Momentum: \|Rendite bis 15:30\| ≥ 1 % → letzte halbe Stunde in Trendrichtung | Zwang: Hebel-Reset der Leveraged ETFs (Cheng/Madhavan 2009) | 6 bps / 0,4 bps ≈ 15 | ~70 | wackelt (Anlegerflüsse kompensieren teils; redundant zu S1) |
| S7 | Monatsultimo: NDX/TLT-Divergenz > 3 pp → kontra 14:00–15:55 am Ultimo | Zwang: Quoten-Rebalancing von Misch-/Pensionsfonds (Etula et al. 2020) | 15 bps / 0,4 bps ≈ 37 | ~10 | wackelt (gecrowdet, Timing streut auf T-3…T+1) |
| S8 | Margin-Crash-Rebound: Vortag ≤ −3 % + schwaches Open → long 10:00, Stop −1,5 % | Zwang: Broker-diktierte Zwangsliquidationen in der ersten Stunde | 20 bps / 0,4 bps ≈ 50 | ~5 | wackelt (Timing-Konzentration unbelegt, Momentum spricht dagegen) |

## Kills am Mechanismus-Gate (vor jedem Backtest gestorben)

- **Pre-FOMC-Drift** (Lucca/Moench 2015) — Mechanismus als Risikoprämie schon in-sample
  widerlegt („Puzzle"), Zerfall auf ~null nach 2016 dokumentiert (Guo et al. 2021). Die freie
  1-Min-Historie (ab 2011) deckt fast nur die Zerfallsperiode ab.
- **0DTE-Gamma-Pinning am Max-OI-Strike** — behauptete Edge ist null-konsistent (Touch-
  Wahrscheinlichkeit einer Irrfahrt ≈ angesetzte „Reversionsquote", EV unter H0 = 0); OI-Daten
  veralten über Nacht und verfehlen Intraday-0DTE-Flow; historische Optionsketten nicht frei.
- **Europa-Close-Reversion 11:30 NY** — kein Abgabezwang im CME-Futures-Markt um 11:30;
  Signalfenster misst überwiegend US-Morgentrend, dessen Faden der Momentum-Evidenz widerspricht.

## Geparkt

- Keine reinen PARKs: der einzige Datenbedarfs-Fall (0DTE-Pinning) starb zusätzlich am
  Mechanismus. S7 trägt eine Auflage (Post-2020-Subsample prüfen), wurde aber getestet.

## Kostenbasis (Recherche, Stand 2026-09)

MNQ ≈ **0,40 bps** Round-Trip (Spread 1 Tick + ~0,5 Ticks Slippage + IBKR-Kommission),
NQ ≈ 0,21 bps, guter CFD ≈ 0,6–2 bps, QQQ für DE-Retail wegen PRIIPs faktisch gesperrt
(UCITS-Ersatz ~5–8 bps). **Empfehlung: MNQ.** Triage rechnet konservativ mit 1,0 bps
Round-Trip + 1,0 bps Stop-Slippage.

## Daten & Quarantäne

- Dukascopy `USATECHIDXUSD`, 1-Min-BID-Kerzen ab 2011-09 (frei, ohne Registrierung);
  Monat im URL-Pfad 0-indexiert; 24-Byte-Records `>u4×5 + f4`, Reihenfolge Open/Close/Low/High,
  Preis = int/1000; Zeitstempel UTC.
- **Holdout:** fest gepinnt auf **ab 2022-04-01** (~jüngste 30 % bei Datenende 2026-08-28,
  ebenfalls gepinnt) — dadurch ist die Grenze über Wiederholungsläufe stabil. Der Holdout
  wird genau einmal verschossen — in `/colab`, für den einen Kandidaten, der die
  Triage-Schwelle deutlich überschreitet. Danach ist er verbrannt.

## Triage-Ergebnis (Lauf 2026-09-01, Training 2012-01-02 – 2022-03-31)

**Leere Runde: 0 von 8 Ideen erreichte die PROMOTE-Schwelle (Sharpe ≥ 1,2).**

| Idee | Sharpe | ab 2018 | CAGR % | MaxDD % | Trades | Kosten/Brutto % | Verdikt |
|---|---|---|---|---|---|---|---|
| S5 Overnight-Prämie | 0,79 | 0,71 | 8,7 | −22,0 | 2666 | 21,9 | **KILL** — reines Beta: schlechter als Buy-and-Hold NDX (Sharpe ~1,0 im selben Fenster), Mechanismus lt. NY Fed seit 2021 zerfallen |
| S3 OPEX-Reversal | 0,68 | 1,10 | 1,4 | −2,7 | 123 | 7,8 | **PARK** — einziger Kandidat, der sich ab 2018 mechanismus­konform *verstärkt*; für Signifikanz fehlen Events (12/Jahr). Reaktivierbar mit längerer NQ-Historie (ab ~2005) oder nach ~2 Jahren Live-Beobachtung |
| S2 ORB 5-Min | 0,33 | 0,45 | 2,5 | −17,5 | 2570 | 60,5 | **KILL** — Kosten fressen 60 % des Bruttos; Paper-Ergebnis repliziert nicht mit ehrlicher Stop-Slippage |
| S6 LETF-Schluss-Momentum | 0,32 | 0,61 | 1,1 | −6,9 | 720 | 36,2 | **KILL** — zu schwach, redundant zu S1 |
| S4 Turn-of-Month | 0,28 | 0,27 | 1,8 | −11,8 | 122 | 5,3 | **KILL** — auf NDX-Intraday-Overlay kein verwertbarer Effekt |
| S1 Intraday-Momentum | −0,06 | −0,13 | −0,4 | −21,3 | 1214 | 132 | **KILL** — Post-Publikations-Zerfall bestätigt |
| S7 Ultimo NDX/TLT | −0,11 | −0,40 | −0,1 | −5,7 | 75 | >999 | **KILL** — Vorzeichen sogar falsch (Front-Running-These des Skeptikers bestätigt) |
| S8 Margin-Rebound | −0,15 | −0,34 | −0,2 | −4,6 | 13 | >999 | **KILL** — 13 Trades, negativ |

Der Holdout (ab 2022-04-01) wurde **nicht** angefasst und bleibt intakt.

**Sperrliste-Eintrag:** Alle 8 getesteten Ideen plus die 3 Mechanismus-Kills (Pre-FOMC,
0DTE-Pinning, Europa-Close) gelten für Nasdaq-100-Intraday als verworfen und werden nicht
mit anderen Parametern erneut vorgeschlagen. Ausnahme: S3 (OPEX) ist geparkt, nicht verworfen.

## Konsequenz

Auf frei verfügbaren Daten und zu ehrlichen Kosten gibt es unter den dokumentierten
Nasdaq-Intraday-Anomalien derzeit keinen belastbaren Bot-Kandidaten — das ist das erwartbare
Ergebnis für den liquidesten Aktienindex-Markt der Welt. Nicht die Parameter nachjustieren,
bis „etwas funktioniert": genau dafür existiert die Multiplizitätsschwelle. Sinnvolle nächste
Züge: anderen Markt/Mechanismus screenen oder auf Tages-Horizont wechseln (Trendfolge/
Vol-Targeting auf Futures), wo Kosten irrelevant sind und die Evidenzlage deutlich besser ist.
