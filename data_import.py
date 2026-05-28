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
    "brennstoff kw": "Brennstoff_kW",
    "leistung brennstoff": "Brennstoff_kW",
    "verbrauch kwh": "Brennstoff_kWh",
    "energieverbrauch": "Brennstoff_kWh",
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
    - 96.168 (German thousands separator) -> 96168
    - 1.234,56 -> 1234.56
    - 13.232,82 -> 13232.82
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
        # Heuristic: if exactly 3 digits after dot and no other dots -> thousands separator
        parts = s.split('.')
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) >= 1:
            # 96.168 -> 96168 (thousands separator)
            s = s.replace('.', '')
        # else: 96.5 stays as 96.5 (decimal)
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


def detect_energy_unit(df):
    """Detect whether the energy column is in kWh or kW.
    
    Returns:
        'kWh' if values are energy (kWh)
        'kW' if values appear to be power (kW) needing multiplication with hours
        None if cannot determine
    """
    # Check column name hints
    for col in df.columns:
        col_lower = str(col).strip().lower()
        if 'kwh' in col_lower:
            return 'kWh'
        if col_lower in ['brennstoff kw', 'brennstoff kw/h', 'leistung brennstoff']:
            # "kW/h" is often a misspelling of kWh in German context
            # but could also mean kW (power)
            return 'ambiguous'
    return None


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


def parse_abrechnungsperiode(value):
    """Parse Abrechnungsperiode and extract start/end dates.
    
    Handles formats like:
    - "01.01.2024 - 31.12.2024"
    - "01.01.2024 bis 31.12.2024"
    - "2024"
    - "01/2024 - 12/2024"
    
    Returns the original string (for display) but validates it.
    """
    if pd.isna(value):
        return None
    s = str(value).strip()
    if not s:
        return None
    return s


def import_data(uploaded_file):
    """Import and parse CSV or Excel file.
    
    Handles:
    - Automatic separator detection (CSV)
    - German number format (96.168 = 96168)
    - Column name fuzzy matching
    - Forward-fill for multi-period rows
    - Detection of kW vs kWh in energy column
    """
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

        # Store original column names for unit detection
        original_cols = list(df.columns)

        # Map columns
        df = map_columns(df)

        # Check if "Brennstoff KW/h" was the original header -> likely kWh in German notation
        energy_unit_hint = None
        for orig_col in original_cols:
            col_lower = orig_col.strip().lower()
            if 'kw/h' in col_lower or 'kwh' in col_lower:
                energy_unit_hint = 'kWh'
            elif col_lower == 'brennstoff kw' or col_lower == 'leistung kw brennstoff':
                energy_unit_hint = 'kW'

        # Store the detected unit hint in the dataframe attributes
        if energy_unit_hint:
            df.attrs['energy_unit_hint'] = energy_unit_hint

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

        # If we have Brennstoff_kW but not Brennstoff_kWh, note it
        # The app will handle the conversion with Betriebsstunden
        if "Brennstoff_kW" in df.columns and "Brennstoff_kWh" not in df.columns:
            df.attrs['needs_betriebsstunden'] = True

        # Parse Abrechnungsperiode
        if "Abrechnungsperiode" in df.columns:
            df["Abrechnungsperiode"] = df["Abrechnungsperiode"].apply(parse_abrechnungsperiode)

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
