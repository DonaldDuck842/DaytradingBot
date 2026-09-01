# Ideen-Screening II: andere Märkte (2026-09-01)

Runde 2 nach der leeren Nasdaq-Runde. Quellen: gezielte Online-Recherche nach
Daytrading-Strategien für Bots (Papers, Quantpedia, CFTC/ECB-Studien) plus
Strukturanalyse. Gesperrt aus Runde 1: alle 11 Nasdaq-Intraday-Ideen außer S3 (OPEX, geparkt).

**Trichter:** 14 Rohideen → 10 nach Mechanismus-Gate → 8 nach Kosten-Gate →
**4 getestet + 1 Kontrolle**, 4 geparkt (Daten).
Kumuliert über beide Runden: 12 getestete Ideen → PROMOTE-Schwelle **Sharpe ≥ 1,2**.

## Die entscheidende Kostenzahl dieser Runde

Krypto-Perp-Taker-Gebühren liegen bei **4,5–5,5 bps pro Seite** (Binance 0,045 % mit
BNB-Rabatt, Bybit 0,055 %) → ~10 bps Round-Trip. Das ist der **25-fache** Kostenblock
gegenüber dem MNQ-Future (0,4 bps). Konsequenz: In Krypto überlebt keine Strategie mit
kleinem Edge pro Trade — nur Ereignisse mit großer Bewegung (Liquidationskaskaden) oder
Carry. Genau daran sterben die im Netz beworbenen Krypto-Intraday-Bots.

## Getestet (`backtests/triage_multimarkt.py`)

| # | Idee | Markt | Mechanismus — wer zahlt? | Edge/Kosten |
|---|---|---|---|---|
| K1 | EIA-Announcement: short 09:00→11:00 NY am Meldedonnerstag | Erdgas | Risikoprämie: Hedger wollen über den Termin nicht ungesichert sein. >50 % der Jahresrendite fällt auf Meldetage (Reading-Paper) | ~40 bps / 6 bps ≈ 7 |
| K2 | Monatsende: Richtung aus Aktien-MTD, 15:00→16:00 London-Fix | EUR/USD | Zwang: mandatierte Hedge-Quoten globaler Aktienmanager (Melvin/Prins 2015: 10 % Aktienplus → 14 bps Währungsabwertung) | ~5 bps / 1 bps ≈ 5 |
| K3 | Gegenprobe: Position nach dem Fix drehen, Exit Folgetag 10:00 | EUR/USD | Derselbe Zwang: temporärer Preisdruck muss zurückdrehen | ~5 bps / 1 bps ≈ 5 |
| K4 | Liquidationskaskade (60-Min-Move ≥ 4,5 %) faden, 4 h halten, 3 % Stop | BTC | Zwang: Perp-Börsen liquidieren per Market-Order ohne Nachschussfrist, ~60x Hebel; wer aufnimmt, wird für Inventarrisiko bezahlt | >100 bps / 10 bps ≈ 10 |
| K4b | **Kontrolle**, kein Kandidat: dieselbe Kaskade als Momentum | BTC | — | — |

K4b ist kein Vorschlag, sondern der Falsifikationstest zu K4: Ist K4b ähnlich gut, misst K4
nur Volatilität statt Reversion.

## Kills am Mechanismus-Gate

- **CME-Gap / Krypto-Wochenendeffekt** — Mechanismus seit **29.05.2026** strukturell
  beseitigt: die CME handelt Krypto-Futures durchgehend, es entstehen keine Wochenendlücken mehr.
- **London-Breakout (Forex-ORB)** — die meistbeworbene Bot-Strategie überhaupt; die Recherche
  fand ausschließlich Schulungs-/Marketingseiten (bis „20–30 % pro Monat"), keine
  peer-reviewte Evidenz und keinen benennbaren Zahler. Data Mining.
- **Funding-Extrem-Reversal** — „die Positionierung ist überhitzt" ist kein Zahler; mehrere
  Quellen sagen selbst, Funding-Raten prognostizieren keine Preisrichtung.
- **Monday-Asia-Open (Concretum)** — Erklärung bleibt „liquidity-driven", kein Zwang benannt.

## Kills am Kosten-Gate

- **Krypto-Intraday-Saisonalität (Stunde des Tages)** — dokumentierte Effekte liegen bei
  5–15 bps gegen 10 bps Round-Trip. Verhältnis < 3 bei hoher Frequenz.
- **Rohöl-Settlement-Fenster (14:00–14:30 NY)** — Edge grob 5–10 bps gegen ~4 bps bei
  ~250 Trades/Jahr. Verhältnis ~2.

## Geparkt (Mechanismus hält, Daten fehlen)

- **Funding-Rate-Carry, delta-neutral** — der am besten dokumentierte Krypto-Edge
  (Zahler: strukturelle Hebelnachfrage der Retail-Longs). Aber: kein Daytrading (Halten über
  Tage/Wochen), braucht Funding-Historie + Spot-Leg, und Binance ist aus DE/Colab teils
  geo-blockiert. Eigene Runde wert.
- **Goldman Roll** (Mou/CFTC: Sharpe bis 4,39 in-sample 2000–2010) — Zwang ist echt und
  öffentlich terminiert, aber die Idee ist ein Kalenderspread und braucht Einzelkontrakt-Preise,
  die unser CFD-Kanal nicht liefert. Zudem seit Publikation 2010 Roll-Termine diversifiziert
  → starker Zerfallsverdacht.
- **Treasury-Auktionszyklus** (Lou/Yan/Zhang 2013: Rendite +2,5 bp vor, −2,3 bp nach der
  Auktion; Primary Dealer *müssen* bieten und hedgen vorher) — stärkster Zwangs-Mechanismus
  der ganzen Recherche, aber keine freie Intraday-Historie für ZN über unseren Kanal, und
  mehrtägiger Halt statt Daytrading.
- **Krypto-ETF-Handelszeiten-Drift** — erst seit Januar 2024, ~2,5 Jahre → strukturell
  unterpowert.

## Daten & Quarantäne

Dukascopy 1-Minuten-Bars, **event-selektiv** geladen (nur Meldedonnerstage, Monatsenden bzw.
BTC-Tage mit Range ≥ 4 %) — ~3.000 statt ~15.000 Dateien. Der BTC-Vorfilter ist eine strikte
Obermenge der Trigger-Tage (Trigger 4,5 % > Filter 4,0 %), erzeugt also keinen Selektionsbias.
**Holdout fest gepinnt ab 2023-06-01**, in diesem Skript nie angefasst.

## Quellen

- Reading: [The natural gas announcement day puzzle](https://centaur.reading.ac.uk/90003/1/NG_paper_final_round.pdf)
- Melvin & Prins: [Equity hedging and exchange rates at the London 4 p.m. fix](https://www.sciencedirect.com/science/article/abs/pii/S1386418114000779) (ECB-Fassung: [PDF](https://www.ecb.europa.eu/events/pdf/conferences/131216/Third_FX_Workshop_MELVIN_PRINS_Equity%20hedging%20and%20exchange%20rates%20Nov%202013.pdf))
- Lou, Yan & Zhang: [Anticipated and Repeated Shocks in Liquid Markets](https://personal.lse.ac.uk/loud/Shocks.pdf)
- Mou (CFTC): [Limits to Arbitrage and Commodity Index Investment: Front-Running the Goldman Roll](https://www.cftc.gov/sites/default/files/idc/groups/public/@swaps/documents/file/plstudy_33_yu.pdf)
- Liquidationskaskaden: [Measuring the engine of a liquidation cascade](https://arxiv.org/abs/2608.03616)
- Krypto-Saisonalität: [Quantpedia — Overnight Seasonality in Bitcoin](https://quantpedia.com/strategies/intraday-seasonality-in-bitcoin), [Concretum](https://concretumgroup.com/seasonality-in-bitcoin-intraday-trend-trading/)
- CME 24/7 (Ende der Wochenendlücke): [CoinDesk](https://www.coindesk.com/markets/2026/05/28/bitcoin-s-famous-cme-gaps-are-about-to-disappear-though-three-remain-unresolved)
- Perp-Gebühren: [Bybit vs Binance Perpetual Futures Fees (2026)](https://www.coinperps.com/learn/bybit-vs-binance-perpetual-futures-fees)
