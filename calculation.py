import pandas as pd
import numpy as np


def get_nutzungsgrad(row, nutzungsgrade):
    """Get Jahresnutzungsgrad based on technology."""
    tech = str(row.get("Technologie", "")).strip()
    for key, value in nutzungsgrade.items():
        if key.lower() in tech.lower():
            return value
    # Default: BMVBS Pauschalwert
    return 0.849


def calculate_preisbereinigung_gp(grundpreis_basis, fix_gp, preisindizes_gp):
    """Calculate price-adjusted Grundpreis using index formula.
    GP = GPB * (FixGP + G1*GP1/GP1B + G2*GP2/GP2B + ...)
    """
    if not preisindizes_gp:
        return grundpreis_basis

    summe = fix_gp
    for idx in preisindizes_gp:
        if idx["basis"] != 0:
            summe += idx["anteil"] * (idx["aktuell"] / idx["basis"])

    if summe == 0:
        return grundpreis_basis
    return grundpreis_basis * summe


def calculate_preisbereinigung_ap(arbeitspreis_basis, fix_ap, preisindizes_ap):
    """Calculate price-adjusted Arbeitspreis using index formula.
    AP = APB * (FixAP + A1*AP1/AP1B + A2*AP2/AP2B + ...)
    """
    if not preisindizes_ap:
        return arbeitspreis_basis

    summe = fix_ap
    for idx in preisindizes_ap:
        if idx["basis"] != 0:
            summe += idx["anteil"] * (idx["aktuell"] / idx["basis"])

    if summe == 0:
        return arbeitspreis_basis
    return arbeitspreis_basis * summe


def calculate_warmwasser_anteil(waermemenge, warmwasser_aktiv, heizflaeche, ww_kwh_pro_m2=20.0):
    """Berechne Warmwasseranteil gemäß WärmeLV.
    
    Bei zentraler Warmwasseraufbereitung wird ein pauschaler Anteil 
    für Warmwasser hinzugerechnet (ca. 20 kWh/m²/a als Richtwert).
    
    Args:
        waermemenge: Wärmemenge Heizung in kWh/a
        warmwasser_aktiv: ob zentrale WW-Aufbereitung vorhanden
        heizflaeche: beheizte Fläche in m²
        ww_kwh_pro_m2: Warmwasser-Pauschale kWh pro m² und Jahr
    
    Returns:
        Gesamtwärmemenge inkl. Warmwasser in kWh/a
    """
    if warmwasser_aktiv and heizflaeche > 0:
        ww_anteil = heizflaeche * ww_kwh_pro_m2
        return waermemenge + ww_anteil
    return waermemenge


def calculate_kostenvergleich(df, params):
    """Calculate Kostenvergleich gemäß §8 WärmeLV für alle Standorte.

    Vergleich nach §8 WärmeLV:
    1. Betriebskosten der bisherigen Versorgung (§9 WärmeLV)
    2. Kosten der Wärmelieferung (§10 WärmeLV)
    
    Die Kosten der Wärmelieferung dürfen die bisherigen Betriebskosten
    nicht übersteigen.

    Args:
        df: DataFrame with site data (multiple rows per site for different periods)
        params: Dictionary with calculation parameters

    Returns:
        DataFrame with results per site
    """
    ust_satz = params["ust_satz"]
    nutzungsgrade = params["nutzungsgrade"]
    default_grundpreis = params["grundpreis_netto"]
    default_arbeitspreis = params["arbeitspreis_netto"]  # ct/kWh
    fix_gp = params["fix_gp"]
    fix_ap = params["fix_ap"]
    preisindizes_gp = params["preisindizes_gp"]
    preisindizes_ap = params["preisindizes_ap"]
    ww_kwh_pro_m2 = params.get("ww_kwh_pro_m2", 20.0)

    # Group by Heizzentrale
    if "Heizzentrale" not in df.columns:
        return pd.DataFrame()

    results = []

    for site, group in df.groupby("Heizzentrale", sort=False):
        row_first = group.iloc[0]

        # --- 1. Betriebskosten der bisherigen Versorgung (§9 WärmeLV) ---
        # §9 (1): Durchschnitt des Energieverbrauchs der letzten 3 Abrechnungszeiträume
        #          multipliziert mit dem Durchschnittspreis des letzten Abrechnungszeitraums
        brennstoff_kwh_col = "Brennstoff_kWh" if "Brennstoff_kWh" in group.columns else None
        if brennstoff_kwh_col:
            verbrauch_values = group[brennstoff_kwh_col].dropna()
            verbrauch_values = verbrauch_values[verbrauch_values > 0]
            durchschnitt_verbrauch = verbrauch_values.mean() if len(verbrauch_values) > 0 else 0
            anzahl_zeitraeume = len(verbrauch_values)
        else:
            durchschnitt_verbrauch = 0
            anzahl_zeitraeume = 0

        # Kosten des letzten Abrechnungszeitraums (Zeile mit Kostendaten)
        last_row = group.iloc[0]
        for _, r in group.iterrows():
            if r.get("Brennstoffkosten", 0) and r["Brennstoffkosten"] > 0:
                last_row = r

        brennstoffkosten = last_row.get("Brennstoffkosten", 0) or 0
        wartung = last_row.get("Wartung", 0) or 0
        schornsteinfeger = last_row.get("Schornsteinfeger", 0) or 0
        betriebsstrom = last_row.get("Betriebsstrom", 0) or 0

        # Durchschnittspreis des letzten Abrechnungszeitraums (ct/kWh)
        last_verbrauch = last_row.get("Brennstoff_kWh", 0) or 0
        if last_verbrauch > 0:
            preis_ct_kwh = (brennstoffkosten / last_verbrauch) * 100
        else:
            preis_ct_kwh = 0

        # §9 (1): Verbrauchskosten = Ø Verbrauch × Durchschnittspreis letzter Zeitraum
        verbrauchskosten = durchschnitt_verbrauch * preis_ct_kwh / 100

        # §9 (1): Sonstige Betriebskosten des letzten Abrechnungszeitraums
        sonstige_betriebskosten = wartung + schornsteinfeger + betriebsstrom

        # Betriebskosten der bisherigen Versorgung §8 Nr. 1 (brutto)
        betriebskosten_bisherig = verbrauchskosten + sonstige_betriebskosten

        # --- 2. Kosten der Wärmelieferung (§10 WärmeLV) ---
        # Jahresnutzungsgrad der Altanlage (Pauschalwert BMVBS oder individuell)
        nutzungsgrad = get_nutzungsgrad(row_first, nutzungsgrade)

        # Wärmemenge = Energieverbrauch (Durchschnitt) × Jahresnutzungsgrad Altanlage
        waermemenge = durchschnitt_verbrauch * nutzungsgrad

        # Warmwasser-Anteil berücksichtigen
        warmwasser_aktiv = str(row_first.get("Warmwasser", "nein")).strip().lower() == "ja"
        heizflaeche = row_first.get("Heizflaeche_m2", 0) or 0
        waermemenge_gesamt = calculate_warmwasser_anteil(
            waermemenge, warmwasser_aktiv, heizflaeche, ww_kwh_pro_m2
        )

        # Wärmelieferpreise - standortspezifisch oder Default
        grundpreis_netto = row_first.get("Grundpreis_netto", default_grundpreis) or default_grundpreis
        arbeitspreis_netto = row_first.get("Arbeitspreis_netto", default_arbeitspreis) or default_arbeitspreis

        # Grundkosten (preisbereinigt) §10
        gp_bereinigt = calculate_preisbereinigung_gp(grundpreis_netto, fix_gp, preisindizes_gp)
        grundkosten_netto_jahr = gp_bereinigt * 12  # Monatlich -> jährlich
        grundkosten_brutto = grundkosten_netto_jahr * (1 + ust_satz)

        # Arbeitskosten (preisbereinigt) §10
        ap_bereinigt = calculate_preisbereinigung_ap(arbeitspreis_netto, fix_ap, preisindizes_ap)
        arbeitskosten_netto = waermemenge_gesamt * ap_bereinigt / 100  # ct/kWh -> €
        arbeitskosten_brutto = arbeitskosten_netto * (1 + ust_satz)

        # Gesamtkosten Wärmelieferung §8 Nr. 2
        kosten_waermelieferung_netto = grundkosten_netto_jahr + arbeitskosten_netto
        kosten_waermelieferung_brutto = grundkosten_brutto + arbeitskosten_brutto

        # --- Ergebnis §8: Kosten WL dürfen Betriebskosten nicht übersteigen ---
        bestanden = kosten_waermelieferung_brutto <= betriebskosten_bisherig
        differenz = betriebskosten_bisherig - kosten_waermelieferung_brutto

        results.append({
            "Heizzentrale": site,
            "Brennstoffart": row_first.get("Brennstoffart", ""),
            "Technologie": row_first.get("Technologie", ""),
            "Leistung_kW": row_first.get("Leistung_kW", 0),
            "Heizflaeche_m2": heizflaeche,
            "Warmwasser": "ja" if warmwasser_aktiv else "nein",
            "Anzahl_Zeitraeume": anzahl_zeitraeume,
            "Durchschnitt_Verbrauch_kWh": round(durchschnitt_verbrauch, 0),
            "Nutzungsgrad": nutzungsgrad,
            "Waermemenge_Heizung_kWh": round(waermemenge, 0),
            "Waermemenge_gesamt_kWh": round(waermemenge_gesamt, 0),
            "Preis_ct_kWh_Brennstoff": round(preis_ct_kwh, 3),
            "Verbrauchskosten_S9": round(verbrauchskosten, 2),
            "Sonstige_Betriebskosten_S9": round(sonstige_betriebskosten, 2),
            "Betriebskosten_bisherig_brutto": round(betriebskosten_bisherig, 2),
            "Grundpreis_Angebot_netto": round(grundpreis_netto, 2),
            "Arbeitspreis_Angebot_netto_ct": round(arbeitspreis_netto, 3),
            "Grundkosten_brutto": round(grundkosten_brutto, 2),
            "Arbeitskosten_brutto": round(arbeitskosten_brutto, 2),
            "Kosten_Waermelieferung_brutto": round(kosten_waermelieferung_brutto, 2),
            "Differenz_Euro": round(differenz, 2),
            "Ergebnis": "✅ §8 erfüllt" if bestanden else "❌ §8 nicht erfüllt",
        })

    return pd.DataFrame(results)
