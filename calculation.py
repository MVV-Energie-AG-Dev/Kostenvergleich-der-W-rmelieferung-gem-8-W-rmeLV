import pandas as pd
import numpy as np


def get_nutzungsgrad(row, nutzungsgrade, site_params=None):
    """Get Jahresnutzungsgrad based on technology or site-specific override."""
    if site_params and site_params.get("nutzungsgrad"):
        return site_params["nutzungsgrad"]
    tech = str(row.get("Technologie", "")).strip()
    for key, value in nutzungsgrade.items():
        if key.lower() in tech.lower():
            return value
    # Default: BMVBS Pauschalwert
    return 0.849


def calculate_preisbereinigung_gp(grundpreis_basis, fix_gp, preisindizes_gp):
    """Calculate price-adjusted Grundpreis using index formula.
    GP = GPB × (FixGP + G1×GP1/GP1B + G2×GP2/GP2B + …)
    
    Returns:
        tuple: (bereinigter Preis, Formel-String mit eingesetzten Werten)
    """
    if not preisindizes_gp:
        return grundpreis_basis, f"GP = {grundpreis_basis:.2f} € (keine Preisgleitklausel)"

    summe = fix_gp
    formel_teile = [f"{fix_gp:.4f}"]
    for i, idx in enumerate(preisindizes_gp):
        if idx["basis"] != 0 and idx["anteil"] != 0:
            teil = idx["anteil"] * (idx["aktuell"] / idx["basis"])
            summe += teil
            formel_teile.append(f"{idx['anteil']:.4f} × {idx['aktuell']:.1f}/{idx['basis']:.1f}")

    if summe == 0:
        return grundpreis_basis, f"GP = {grundpreis_basis:.2f} € (Summe=0, unbereinigt)"

    result = grundpreis_basis * summe
    formel = f"GP = {grundpreis_basis:.2f} × ({' + '.join(formel_teile)}) = {result:.2f} €/Monat"
    return result, formel


def calculate_preisbereinigung_ap(arbeitspreis_basis, fix_ap, preisindizes_ap):
    """Calculate price-adjusted Arbeitspreis using index formula.
    AP = APB × (FixAP + A1×AP1/AP1B + A2×AP2/AP2B + …)
    
    Returns:
        tuple: (bereinigter Preis, Formel-String mit eingesetzten Werten)
    """
    if not preisindizes_ap:
        return arbeitspreis_basis, f"AP = {arbeitspreis_basis:.3f} ct/kWh (keine Preisgleitklausel)"

    summe = fix_ap
    formel_teile = [f"{fix_ap:.4f}"]
    for i, idx in enumerate(preisindizes_ap):
        if idx["basis"] != 0 and idx["anteil"] != 0:
            teil = idx["anteil"] * (idx["aktuell"] / idx["basis"])
            summe += teil
            formel_teile.append(f"{idx['anteil']:.4f} × {idx['aktuell']:.1f}/{idx['basis']:.1f}")

    if summe == 0:
        return arbeitspreis_basis, f"AP = {arbeitspreis_basis:.3f} ct/kWh (Summe=0, unbereinigt)"

    result = arbeitspreis_basis * summe
    formel = f"AP = {arbeitspreis_basis:.3f} × ({' + '.join(formel_teile)}) = {result:.3f} ct/kWh"
    return result, formel


def calculate_warmwasser_anteil(waermemenge, warmwasser_aktiv, heizflaeche, ww_kwh_pro_m2=20.0):
    """Berechne Warmwasseranteil gemäß WärmeLV."""
    if warmwasser_aktiv and heizflaeche > 0:
        ww_anteil = heizflaeche * ww_kwh_pro_m2
        return waermemenge + ww_anteil
    return waermemenge


def calculate_kostenvergleich(df, params, site_params_dict=None):
    """Calculate Kostenvergleich gemäß §8 WärmeLV für alle Standorte.

    Args:
        df: DataFrame with site data (multiple rows per site for different periods)
        params: Dictionary with default calculation parameters
        site_params_dict: Optional dict {site_name: {param_overrides}} for per-site params

    Returns:
        DataFrame with results per site
    """
    if site_params_dict is None:
        site_params_dict = {}

    ust_satz = params["ust_satz"]
    nutzungsgrade = params["nutzungsgrade"]
    default_grundpreis = params["grundpreis_netto"]
    default_arbeitspreis = params["arbeitspreis_netto"]  # ct/kWh
    default_betriebsstunden = params.get("betriebsstunden", 0)
    fix_gp = params["fix_gp"]
    fix_ap = params["fix_ap"]
    preisindizes_gp = params["preisindizes_gp"]
    preisindizes_ap = params["preisindizes_ap"]
    ww_kwh_pro_m2 = params.get("ww_kwh_pro_m2", 20.0)

    if "Heizzentrale" not in df.columns:
        return pd.DataFrame()

    results = []

    for site, group in df.groupby("Heizzentrale", sort=False):
        row_first = group.iloc[0]
        sp = site_params_dict.get(site, {})

        # Site-specific overrides
        site_grundpreis = sp.get("grundpreis_netto", default_grundpreis) or default_grundpreis
        site_arbeitspreis = sp.get("arbeitspreis_netto", default_arbeitspreis) or default_arbeitspreis
        site_betriebsstunden = sp.get("betriebsstunden", default_betriebsstunden) or default_betriebsstunden
        site_fix_gp = sp.get("fix_gp", fix_gp)
        site_fix_ap = sp.get("fix_ap", fix_ap)
        site_preisindizes_gp = sp.get("preisindizes_gp", preisindizes_gp)
        site_preisindizes_ap = sp.get("preisindizes_ap", preisindizes_ap)
        site_ww_kwh_pro_m2 = sp.get("ww_kwh_pro_m2", ww_kwh_pro_m2)

        # --- 1. Betriebskosten der bisherigen Versorgung (§9 WärmeLV) ---
        brennstoff_kwh_col = "Brennstoff_kWh" if "Brennstoff_kWh" in group.columns else None
        brennstoff_kw_col = "Brennstoff_kW" if "Brennstoff_kW" in group.columns else None

        if brennstoff_kwh_col:
            verbrauch_values = group[brennstoff_kwh_col].dropna()
            verbrauch_values = verbrauch_values[verbrauch_values > 0]
            durchschnitt_verbrauch = verbrauch_values.mean() if len(verbrauch_values) > 0 else 0
            anzahl_zeitraeume = len(verbrauch_values)
        elif brennstoff_kw_col and site_betriebsstunden > 0:
            # Convert kW to kWh using Betriebsstunden
            kw_values = group[brennstoff_kw_col].dropna()
            kw_values = kw_values[kw_values > 0]
            kwh_values = kw_values * site_betriebsstunden
            durchschnitt_verbrauch = kwh_values.mean() if len(kwh_values) > 0 else 0
            anzahl_zeitraeume = len(kw_values)
        else:
            durchschnitt_verbrauch = 0
            anzahl_zeitraeume = 0

        # Kosten des letzten Abrechnungszeitraums
        last_row = group.iloc[-1]  # Last row = last period
        for _, r in group.iterrows():
            if r.get("Brennstoffkosten", 0) and r["Brennstoffkosten"] > 0:
                last_row = r

        brennstoffkosten = last_row.get("Brennstoffkosten", 0) or 0
        wartung = last_row.get("Wartung", 0) or 0
        schornsteinfeger = last_row.get("Schornsteinfeger", 0) or 0
        betriebsstrom = last_row.get("Betriebsstrom", 0) or 0

        # Durchschnittspreis letzter Abrechnungszeitraum
        last_verbrauch = last_row.get("Brennstoff_kWh", 0) or 0
        if last_verbrauch == 0 and brennstoff_kw_col and site_betriebsstunden > 0:
            last_kw = last_row.get("Brennstoff_kW", 0) or 0
            last_verbrauch = last_kw * site_betriebsstunden

        if last_verbrauch > 0:
            preis_ct_kwh = (brennstoffkosten / last_verbrauch) * 100
        else:
            preis_ct_kwh = 0

        verbrauchskosten = durchschnitt_verbrauch * preis_ct_kwh / 100
        sonstige_betriebskosten = wartung + schornsteinfeger + betriebsstrom
        betriebskosten_bisherig = verbrauchskosten + sonstige_betriebskosten

        # --- 2. Kosten der Wärmelieferung (§10 WärmeLV) ---
        nutzungsgrad = get_nutzungsgrad(row_first, nutzungsgrade, sp)
        waermemenge = durchschnitt_verbrauch * nutzungsgrad

        warmwasser_aktiv = str(row_first.get("Warmwasser", "nein")).strip().lower() == "ja"
        heizflaeche = row_first.get("Heizflaeche_m2", 0) or 0
        waermemenge_gesamt = calculate_warmwasser_anteil(
            waermemenge, warmwasser_aktiv, heizflaeche, site_ww_kwh_pro_m2
        )

        # Grundkosten (preisbereinigt) §10
        gp_bereinigt, formel_gp = calculate_preisbereinigung_gp(
            site_grundpreis, site_fix_gp, site_preisindizes_gp
        )
        grundkosten_netto_jahr = gp_bereinigt * 12
        grundkosten_brutto = grundkosten_netto_jahr * (1 + ust_satz)

        # Arbeitskosten (preisbereinigt) §10
        ap_bereinigt, formel_ap = calculate_preisbereinigung_ap(
            site_arbeitspreis, site_fix_ap, site_preisindizes_ap
        )
        arbeitskosten_netto = waermemenge_gesamt * ap_bereinigt / 100
        arbeitskosten_brutto = arbeitskosten_netto * (1 + ust_satz)

        # Gesamtkosten Wärmelieferung
        kosten_waermelieferung_brutto = grundkosten_brutto + arbeitskosten_brutto

        # Ergebnis §8
        bestanden = kosten_waermelieferung_brutto <= betriebskosten_bisherig
        differenz = betriebskosten_bisherig - kosten_waermelieferung_brutto

        # Abrechnungsperioden sammeln
        perioden = []
        if "Abrechnungsperiode" in group.columns:
            perioden = group["Abrechnungsperiode"].dropna().tolist()

        results.append({
            "Heizzentrale": site,
            "Brennstoffart": row_first.get("Brennstoffart", ""),
            "Technologie": row_first.get("Technologie", ""),
            "Leistung_kW": row_first.get("Leistung_kW", 0),
            "Heizflaeche_m2": heizflaeche,
            "Warmwasser": "ja" if warmwasser_aktiv else "nein",
            "Betriebsstunden": site_betriebsstunden,
            "Anzahl_Zeitraeume": anzahl_zeitraeume,
            "Abrechnungsperioden": " | ".join(str(p) for p in perioden),
            "Durchschnitt_Verbrauch_kWh": round(durchschnitt_verbrauch, 0),
            "Nutzungsgrad": nutzungsgrad,
            "Waermemenge_Heizung_kWh": round(waermemenge, 0),
            "Waermemenge_gesamt_kWh": round(waermemenge_gesamt, 0),
            "Preis_ct_kWh_Brennstoff": round(preis_ct_kwh, 3),
            "Verbrauchskosten_S9": round(verbrauchskosten, 2),
            "Sonstige_Betriebskosten_S9": round(sonstige_betriebskosten, 2),
            "Betriebskosten_bisherig_brutto": round(betriebskosten_bisherig, 2),
            "Grundpreis_Angebot_netto": round(site_grundpreis, 2),
            "Arbeitspreis_Angebot_netto_ct": round(site_arbeitspreis, 3),
            "GP_bereinigt": round(gp_bereinigt, 2),
            "AP_bereinigt_ct": round(ap_bereinigt, 3),
            "Formel_GP": formel_gp,
            "Formel_AP": formel_ap,
            "Grundkosten_brutto": round(grundkosten_brutto, 2),
            "Arbeitskosten_brutto": round(arbeitskosten_brutto, 2),
            "Kosten_Waermelieferung_brutto": round(kosten_waermelieferung_brutto, 2),
            "Differenz_Euro": round(differenz, 2),
            "Ergebnis": "✅ §8 erfüllt" if bestanden else "❌ §8 nicht erfüllt",
        })

    return pd.DataFrame(results)
