# DaytradingBot — Nasdaq 100 Intraday

Ein Daytrading-Bot für Indizes (Fokus: Nasdaq 100) ist machbar. Dieses Repo enthält den
Strategie-Trichter dafür: Ideen-Screening → Triage-Backtest → volle Validierung → erst danach Bot-Code.

## Warum diese Reihenfolge

Der Bot selbst (Datenfeed, Order-Ausführung, Risiko-Layer) ist gelöste Ingenieursarbeit.
Was fast alle Daytrading-Bots scheitern lässt, ist die Strategie: die meisten Intraday-Ideen
sterben an den Handelskosten oder waren nie mehr als Rauschen. Deshalb wird hier zuerst die
Strategie belastbar gemacht, bevor eine Zeile Ausführungscode entsteht.

## Instrumentenwahl (privater Trader, Europa)

| Instrument | Zugang | Round-Trip-Kosten (grob) | Anmerkung |
|---|---|---|---|
| MNQ (Micro E-mini Nasdaq Future) | IBKR, Tradovate u. a. | ~1–3 bps | bester Kompromiss aus Größe (~2 $/Punkt) und Kosten |
| NQ (E-mini Future) | IBKR u. a. | ~0,5–1,5 bps | günstigst, aber ~20 $/Punkt — Kontogröße nötig |
| Nasdaq-100-CFD | Dukascopy, IG u. a. | ~2–5 bps | kleinste Größen, API-Zugang einfach, Kosten höher |
| QQQ (ETF) | IBKR u. a. | ~1–3 bps | UCITS-Problematik in der EU; PDT-Regel nur bei US-Konten |

## Pipeline

1. **`/screen`** — Ideen-Screening: Kandidaten aus dokumentierten Anomalien und Marktstruktur,
   Mechanismus-Gate („Wer zahlt?"), Kosten-Arithmetik-Gate, dann ein Triage-Backtest für alle
   Überlebenden in einem Lauf. Ergebnis: höchstens 1–2 Kandidaten. → `docs/screening-nasdaq-intraday.md`
2. **Triage-Backtest** — `backtests/triage_nasdaq_intraday.py`, ein Colab-Skript, einmal einfügen,
   einmal laufen lassen. Fester Parametersatz pro Idee, volle Kosten, nur Trainingsfenster,
   Holdout quarantäniert.
3. **`/colab`** — volle statistische Validierung (Permutationstest, Block-Bootstrap, OOS auf dem
   Holdout) für den einen Kandidaten, der die Triage-Schwelle reißt.
4. **Bot-Bau** — erst danach: Signal-Engine aus der validierten Regel, Paper-Trading gegen
   Live-Daten (mind. 1–3 Monate), dann kleines Echtgeld (1 MNQ / kleinste CFD-Größe).

## Bot-Architektur (Zielbild)

```
Datenfeed (Broker-API/Websocket, 1-Min-Bars)
        │
Signal-Engine (die validierte Regel, zustandslos pro Session)
        │
Risk-Layer (Positionsgröße, Tages-Stopp, Kill-Switch, Zeitfenster-Sperren)
        │
Order-Management (Broker-API, Idempotenz, Reconnect, Fehlerpfade)
        │
Journal (jeder Trade + Slippage vs. Backtest-Annahme)
```

Der Risk-Layer ist nicht optional: ein Bot ohne Tagesverlust-Stopp und Kill-Switch ist ein
Totalverlust mit Zeitverzögerung.
