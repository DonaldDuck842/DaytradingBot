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

## Nächster Schritt

1. `backtests/triage_nasdaq_intraday.py` in eine Colab-Zelle einfügen und laufen lassen
   (~5–10 Min beim ersten Lauf).
2. Ergebnis-Tabelle zurückmelden. Bei Sharpe ≥ 1,2 (und stabiler „ab 2018"-Spalte):
   `/colab <Kandidat>` für die volle Validierung inkl. Permutationstest, Block-Bootstrap
   und dem einmaligen Holdout-Test.
3. Reißt nichts die Schwelle: leere Runde akzeptieren, nächstes Screening auf anderem
   Markt/Mechanismus — nicht dieselben Ideen mit anderen Parametern wiederholen.
