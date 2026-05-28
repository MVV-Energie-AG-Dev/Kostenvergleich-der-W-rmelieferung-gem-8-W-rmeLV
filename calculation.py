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


def calculate_kostenvergleich(df, params):
    """Calculate Kostenvergleich for all sites.

    Args:
        df: DataFrame with site data (multiple rows per site for different periods)
        params: Dictionary with calculation parameters

    Returns:
        DataFrame with results per site
    """
    ust_satz = params["ust_satz"]
    nutzungsgrade = params["nutzungsgrade"]
    grundpreis_netto = params["grundpreis_netto"]
    arbeitspreis_netto = params["arbeitspreis_netto"]  # ct/kWh
    fix_gp = params["fix_gp"]
    fix_ap = params["fix_ap"]
    preisindizes_gp = params["preisindizes_gp"]
    preisindizes_ap = params["preisindizes_ap"]

    # Group by Heizzentrale
    if "Heizzentrale" not in df.columns:
        return pd.DataFrame()

    results = []

    for site, group in df.groupby("Heizzentrale", sort=False):
        row_first = group.iloc[0]

        # --- 1. Betriebskosten der bisherigen Versorgung (§9 WärmeLV) ---
        brennstoff_kwh_col = "Brennstoff_kWh" if "Brennstoff_kWh" in group.columns else None
        if brennstoff_kwh_col:
            verbrauch_values = group[brennstoff_kwh_col].dropna()
            verbrauch_values = verbrauch_values[verbrauch_values > 0]
            durchschnitt_verbrauch = verbrauch_values.mean() if len(verbrauch_values) > 0 else 0
            anzahl_zeitraeume = len(verbrauch_values)
        else:
            durchschnitt_verbrauch = 0
            anzahl_zeitraeume = 0

        # Costs from last period with cost data
        last_row = group.iloc[0]
        for _, r in group.iterrows():
            if r.get("Brennstoffkosten", 0) and r["Brennstoffkosten"] > 0:
                last_row = r

        brennstoffkosten = last_row.get("Brennstoffkosten", 0) or 0
        wartung = last_row.get("Wartung", 0) or 0
        schornsteinfeger = last_row.get("Schornsteinfeger", 0) or 0
        betriebsstrom = last_row.get("Betriebsstrom", 0) or 0

        # Calculate price per kWh from last period
        last_verbrauch = last_row.get("Brennstoff_kWh", 0) or 0
        if last_verbrauch > 0:
            preis_ct_kwh = (brennstoffkosten / last_verbrauch) * 100
        else:
            preis_ct_kwh = 0

        # Verbrauchskosten nach §9(1)
        verbrauchskosten = durchschnitt_verbrauch * preis_ct_kwh / 100

        # Sonstige Betriebskosten
        sonstige_betriebskosten = wartung + schornsteinfeger + betriebsstrom

        # Betriebskosten der bisherigen Versorgung (brutto)
        betriebskosten_bisherig = verbrauchskosten + sonstige_betriebskosten

        # --- 2. Kosten der Wärmelieferung (§10 WärmeLV) ---
        nutzungsgrad = get_nutzungsgrad(row_first, nutzungsgrade)
        waermemenge = durchschnitt_verbrauch * nutzungsgrad

        # Grundkosten (preisbereinigt)
        gp_bereinigt = calculate_preisbereinigung_gp(grundpreis_netto, fix_gp, preisindizes_gp)
        grundkosten_netto = gp_bereinigt * 12
        grundkosten_brutto = grundkosten_netto * (1 + ust_satz)

        # Arbeitskosten (preisbereinigt)
        ap_bereinigt = calculate_preisbereinigung_ap(arbeitspreis_netto, fix_ap, preisindizes_ap)
        arbeitskosten_netto = waermemenge * ap_bereinigt / 100
        arbeitskosten_brutto = arbeitskosten_netto * (1 + ust_satz)

        # Gesamtkosten Wärmelieferung
        kosten_waermelieferung_brutto = grundkosten_brutto + arbeitskosten_brutto

        # --- Ergebnis ---
        bestanden = kosten_waermelieferung_brutto <= betriebskosten_bisherig

        heizflaeche = row_first.get("Heizflaeche_m2", 0) or 0

        results.append({
            "Heizzentrale": site,
            "Brennstoffart": row_first.get("Brennstoffart", ""),
            "Technologie": row_first.get("Technologie", ""),
            "Leistung_kW": row_first.get("Leistung_kW", 0),
            "Heizflaeche_m2": heizflaeche,
            "Anzahl_Zeitraeume": anzahl_zeitraeume,
            "Durchschnitt_Verbrauch_kWh": round(durchschnitt_verbrauch, 0),
            "Nutzungsgrad": nutzungsgrad,
            "Waermemenge_kWh": round(waermemenge, 0),
            "Preis_ct_kWh": round(preis_ct_kwh, 3),
            "Verbrauchskosten": round(verbrauchskosten, 2),
            "Sonstige_Betriebskosten": round(sonstige_betriebskosten, 2),
            "Betriebskosten_bisherig_brutto": round(betriebskosten_bisherig, 2),
            "Grundkosten_brutto": round(grundkosten_brutto, 2),
            "Arbeitskosten_brutto": round(arbeitskosten_brutto, 2),
            "Kosten_Waermelieferung_brutto": round(kosten_waermelieferung_brutto, 2),
            "Ergebnis": "\u2705 Bestanden" if bestanden else "\u274c Nicht bestanden",
        })

    return pd.DataFrame(results)
