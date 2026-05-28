import pandas as pd
import re
import io

# Mapping of possible column names to standardized names
COLUMN_MAPPING = {
    "heizzentrale": "Heizzentrale",
    "standort": "Heizzentrale",
    "objekt": "Heizzentrale",
    "brennstoffart": "Brennstoffart",
    "brennstoff": "Brennstoffart",
    "kessel": "Kessel",
    "kesseltyp": "Kessel",
    "leistung": "Leistung_kW",
    "leistung kw": "Leistung_kW",
    "nennleistung": "Leistung_kW",
    "technologie": "Technologie",
    "baujahr": "Baujahr",
    "zentralisierte warmwasseraufbereitung": "Warmwasser",
    "warmwasser": "Warmwasser",
    "wwb": "Warmwasser",
    "abrechnungsperiode": "Abrechnungsperiode",
    "abrechungsperiode": "Abrechnungsperiode",
    "zeitraum": "Abrechnungsperiode",
    "periode": "Abrechnungsperiode",
    "brennstoff kwh": "Brennstoff_kWh",
    "brennstoff kw/h": "Brennstoff_kWh",
    "verbrauch kwh": "Brennstoff_kWh",
    "energieverbrauch": "Brennstoff_kWh",
    "brennstoffkosten": "Brennstoffkosten",
    "energiekosten": "Brennstoffkosten",
    "wartung": "Wartung",
    "schornsteinfeger": "Schornsteinfeger",
    "betriebsstrom": "Betriebsstrom",
    "summe": "Summe",
    "heizfläche": "Heizflaeche_m2",
    "heizfläche m²": "Heizflaeche_m2",
    "heizflaeche": "Heizflaeche_m2",
    "fläche": "Heizflaeche_m2",
    "€/m²/monat": "Euro_m2_Monat",
    "verbrauch kwh/m²": "Verbrauch_kWh_m2",
}


def parse_german_number(value):
    """Parse German number format (1.234,56 €) to float."""
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    # Remove currency symbols and whitespace
    s = re.sub(r'[€$\s]', '', s)
    # Handle German format: 1.234,56 -> 1234.56
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def parse_leistung(value):
    """Extract numeric kW value from strings like '130 kW'."""
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r'([\d.,]+)', str(value))
    if match:
        return parse_german_number(match.group(1))
    return 0.0


def map_columns(df):
    """Map DataFrame columns to standardized names."""
    new_columns = {}
    for col in df.columns:
        col_lower = str(col).strip().lower()
        if col_lower in COLUMN_MAPPING:
            new_columns[col] = COLUMN_MAPPING[col_lower]
        else:
            # Fuzzy match
            for key, mapped in COLUMN_MAPPING.items():
                if key in col_lower or col_lower in key:
                    new_columns[col] = mapped
                    break

    df = df.rename(columns=new_columns)
    return df


def import_data(uploaded_file):
    """Import and parse CSV or Excel file."""
    try:
        filename = uploaded_file.name.lower()
        if filename.endswith(".csv"):
            # Try different separators
            content = uploaded_file.read().decode("utf-8", errors="replace")
            for sep in [";", ",", "\t", "|"]:
                try:
                    df = pd.read_csv(io.StringIO(content), sep=sep)
                    if len(df.columns) > 3:
                        break
                except:
                    continue
        else:
            df = pd.read_excel(uploaded_file)

        # Map columns
        df = map_columns(df)

        # Parse numeric columns
        numeric_cols = ["Brennstoff_kWh", "Brennstoffkosten", "Wartung",
                       "Schornsteinfeger", "Betriebsstrom", "Summe",
                       "Heizflaeche_m2", "Euro_m2_Monat", "Verbrauch_kWh_m2"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(parse_german_number)

        if "Leistung_kW" in df.columns:
            df["Leistung_kW"] = df["Leistung_kW"].apply(parse_leistung)

        # Forward-fill site info for multi-period rows
        site_cols = ["Heizzentrale", "Brennstoffart", "Kessel", "Leistung_kW",
                    "Technologie", "Baujahr", "Warmwasser", "Heizflaeche_m2"]
        for col in site_cols:
            if col in df.columns:
                df[col] = df[col].ffill()

        return df
    except Exception as e:
        import streamlit as st
        st.error(f"Fehler beim Import: {e}")
        return None
