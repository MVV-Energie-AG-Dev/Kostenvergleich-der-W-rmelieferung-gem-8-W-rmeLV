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
    "verbrauch kwh": "Brennstoff_kWh",
    "energieverbrauch kwh": "Brennstoff_kWh",
    "brennstoff kw/h": "Brennstoff_kW",
    "brennstoff kw": "Brennstoff_kW",
    "leistung brennstoff": "Brennstoff_kW",
    "energieverbrauch": "Brennstoff_kW",
    "betriebsstunden": "Betriebsstunden",
    "vollbenutzungsstunden": "Betriebsstunden",
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
    """Parse German number format (1.234,56 €) to float.
    
    Handles:
    - 96.168 (German thousands separator, 3 digits after dot) -> 96168
    - 1.234,56 -> 1234.56
    - 13.232,82 -> 13232.82
    - 104.343 -> 104343
    """
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    # Remove currency symbols and whitespace
    s = re.sub(r'[€$\s]', '', s)
    if not s:
        return 0.0
    # Handle German format
    if ',' in s and '.' in s:
        # 1.234,56 -> 1234.56 (dot is thousands, comma is decimal)
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        # 1234,56 -> 1234.56 (comma is decimal)
        s = s.replace(',', '.')
    elif '.' in s:
        # Ambiguous: could be 96.168 (=96168) or 96.5 (=96.5)
        # Heuristic: if exactly 3 digits after dot -> thousands separator
        parts = s.split('.')
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) >= 1:
            # 96.168 -> 96168, 104.343 -> 104343
            s = s.replace('.', '')
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


def detect_energy_column_type(df, original_cols):
    """Detect whether energy data is in kW or kWh based on column headers.
    
    'Brennstoff KW/h' = kW (Leistung, braucht Betriebsstunden)
    'Brennstoff kWh' = kWh (Arbeit, direkt nutzbar)
    
    Returns:
        'kW' if values are power needing Betriebsstunden
        'kWh' if values are energy directly usable
    """
    for col in original_cols:
        col_lower = col.strip().lower()
        # "kw/h" ist NICHT kWh - es ist kW (Leistung)!
        if 'kw/h' in col_lower:
            return 'kW'
        if 'kwh' in col_lower and 'kw/h' not in col_lower:
            return 'kWh'
    return 'kW'  # Default: assume kW (safer, forces user to enter Betriebsstunden)


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

        # Store original column names for energy unit detection
        original_cols = list(df.columns)
        energy_type = detect_energy_column_type(df, original_cols)

        # Map columns
        df = map_columns(df)

        # If energy type is kW, ensure column is named Brennstoff_kW (not kWh)
        if energy_type == 'kW':
            if "Brennstoff_kWh" in df.columns and "Brennstoff_kW" not in df.columns:
                df = df.rename(columns={"Brennstoff_kWh": "Brennstoff_kW"})

        # Store energy type as attribute
        df.attrs['energy_type'] = energy_type

        # Parse numeric columns
        numeric_cols = ["Brennstoff_kWh", "Brennstoff_kW", "Brennstoffkosten", "Wartung",
                       "Schornsteinfeger", "Betriebsstrom", "Summe",
                       "Heizflaeche_m2", "Euro_m2_Monat", "Verbrauch_kWh_m2",
                       "Betriebsstunden"]
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
