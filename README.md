# Kostenvergleich der Wärmelieferung gemäß §8 WärmeLV – Bulk-Tool

Webbasiertes Tool für den Kostenvergleich der Wärmelieferung an **vielen Standorten gleichzeitig**.

## Features

- **Bulk-Berechnung**: Kostenvergleich für beliebig viele Standorte gleichzeitig
- **Datenimport**: CSV/Excel-Import mit automatischer Spaltenerkennung
- **Anpassbare Parameter**: Jahresnutzungsgrad, Heizwerte, USt-Satz, Preisindizes
- **Export**: Ergebnisse als CSV/Excel exportieren
- **Berechnung nach dena-Schema**: §8, §9, §10 WärmeLV

## Installation

```bash
pip install -r requirements.txt
```

## Starten

```bash
streamlit run app.py
```

## Datenimport-Format

CSV oder Excel mit folgenden Spalten (Reihenfolge flexibel, automatische Erkennung):

| Spalte | Beschreibung |
|--------|-------------|
| Heizzentrale | Name/Standort |
| Brennstoffart | z.B. Erdgas, Heizöl |
| Kessel | Kesselbezeichnung |
| Leistung | Nennleistung in kW |
| Technologie | z.B. Brennwert, Niedertemperatur |
| Baujahr | Baujahr der Anlage |
| Zentralisierte Warmwasseraufbereitung | ja/nein |
| Abrechnungsperiode | Zeitraum (z.B. 01.01.2024-31.12.2024) |
| Brennstoff kWh | Energieverbrauch in kWh |
| Brennstoffkosten | Kosten in € |
| Wartung | Wartungskosten in € |
| Schornsteinfeger | Kosten in € |
| Betriebsstrom | Kosten in € |
| Heizfläche m² | Beheizte Fläche |

Mehrere Abrechnungszeiträume pro Standort werden über mehrere Zeilen mit gleicher Heizzentrale abgebildet (siehe `example_data.csv`).

## Berechnung

1. **Betriebskosten bisherige Versorgung (§9 WärmeLV)**:
   - Durchschnittlicher Energieverbrauch über alle Abrechnungszeiträume
   - Kosten des letzten Abrechnungszeitraums

2. **Kosten der Wärmelieferung (§10 WärmeLV)**:
   - Wärmemenge = Energieverbrauch × Jahresnutzungsgrad
   - Grundkosten + Arbeitskosten (preisbereinigt über Indizes)
   - Preisbereinigung: `GP = GPB × (FixGP + G1×GP1/GP1B + ...)`

3. **Ergebnis**: Vergleich ob Wärmelieferung ≤ bisherige Betriebskosten
