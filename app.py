import streamlit as st
import pandas as pd
import io
import json
import os
from datetime import datetime
from calculation import calculate_kostenvergleich
from data_import import import_data, parse_german_number

# --- Projekte-Verzeichnis ---
PROJECTS_DIR = "projekte"
os.makedirs(PROJECTS_DIR, exist_ok=True)

st.set_page_config(page_title="Kostenvergleich §8 WärmeLV", layout="wide")


def get_project_list():
    """Liste aller gespeicherten Projekte."""
    if not os.path.exists(PROJECTS_DIR):
        return []
    return sorted([f.replace(".json", "") for f in os.listdir(PROJECTS_DIR) if f.endswith(".json")])


def save_project(name, data):
    """Projekt als JSON speichern."""
    filepath = os.path.join(PROJECTS_DIR, f"{name}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def load_project(name):
    """Projekt aus JSON laden."""
    filepath = os.path.join(PROJECTS_DIR, f"{name}.json")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_project(name):
    """Projekt löschen."""
    filepath = os.path.join(PROJECTS_DIR, f"{name}.json")
    if os.path.exists(filepath):
        os.remove(filepath)


# --- Projekt-Verwaltung (immer sichtbar oben) ---
st.title("Kostenvergleich der Wärmelieferung gemäß §8 WärmeLV")

# Projekt-Auswahl
proj_col1, proj_col2, proj_col3, proj_col4 = st.columns([3, 2, 2, 2])

with proj_col1:
    projects = get_project_list()
    if "current_project" not in st.session_state:
        st.session_state["current_project"] = None

    selected_project = st.selectbox(
        "📂 Projekt auswählen",
        ["-- Neues Projekt --"] + projects,
        index=0
    )

with proj_col2:
    new_project_name = st.text_input("Projektname", placeholder="z.B. Quartier Nord 2026")

with proj_col3:
    if st.button("➕ Neues Projekt anlegen"):
        if new_project_name:
            project_data = {
                "name": new_project_name,
                "created": datetime.now().isoformat(),
                "params": {},
                "imported_data": None,
                "manual_data": [],
                "results": None,
            }
            save_project(new_project_name, project_data)
            st.session_state["current_project"] = new_project_name
            st.session_state["imported_data"] = None
            st.session_state["manual_data"] = []
            st.session_state.pop("results", None)
            st.rerun()
        else:
            st.error("Bitte Projektnamen eingeben")

with proj_col4:
    if st.button("📂 Projekt laden") and selected_project != "-- Neues Projekt --":
        loaded = load_project(selected_project)
        st.session_state["current_project"] = selected_project
        if loaded.get("imported_data"):
            st.session_state["imported_data"] = pd.DataFrame(loaded["imported_data"])
        else:
            st.session_state["imported_data"] = None
        st.session_state["manual_data"] = loaded.get("manual_data", [])
        if loaded.get("results"):
            st.session_state["results"] = pd.DataFrame(loaded["results"])
        else:
            st.session_state.pop("results", None)
        # Load params into session
        if loaded.get("params"):
            st.session_state["loaded_params"] = loaded["params"]
        st.rerun()

# Aktuelles Projekt anzeigen
if st.session_state.get("current_project"):
    st.info(f"📂 **Aktuelles Projekt:** {st.session_state['current_project']}")
else:
    st.markdown("*Kein Projekt ausgewählt – erstellen Sie ein neues Projekt oder wählen Sie ein vorhandenes.*")

st.markdown("---")

# --- Sidebar: Anpassbare Parameter ---
st.sidebar.header("⚙️ Berechnungsparameter")

# Load saved params if available
lp = st.session_state.get("loaded_params", {})

st.sidebar.subheader("Allgemein")
ust_satz = st.sidebar.number_input("USt-Satz (%)", value=lp.get("ust_satz", 0.19) * 100 if lp.get("ust_satz") else 19.0, step=0.1) / 100

st.sidebar.subheader("Jahresnutzungsgrade Altanlage (%)")
st.sidebar.markdown("*BMVBS-Pauschalwerte oder individuell*")
lp_ng = lp.get("nutzungsgrade", {})
nutzungsgrade = {
    "Brennwert": st.sidebar.number_input("Brennwert", value=lp_ng.get("Brennwert", 0.96) * 100 if lp_ng.get("Brennwert") else 96.0, step=0.5) / 100,
    "Niedertemperatur": st.sidebar.number_input("Niedertemperatur", value=lp_ng.get("Niedertemperatur", 0.849) * 100 if lp_ng.get("Niedertemperatur") else 84.9, step=0.5) / 100,
    "Standardkessel": st.sidebar.number_input("Standardkessel", value=lp_ng.get("Standardkessel", 0.80) * 100 if lp_ng.get("Standardkessel") else 80.0, step=0.5) / 100,
    "Konstanttemperatur": st.sidebar.number_input("Konstanttemperatur", value=lp_ng.get("Konstanttemperatur", 0.78) * 100 if lp_ng.get("Konstanttemperatur") else 78.0, step=0.5) / 100,
}

st.sidebar.subheader("Warmwasser")
ww_kwh_pro_m2 = st.sidebar.number_input("WW-Pauschale (kWh/m²/a)", value=lp.get("ww_kwh_pro_m2", 20.0), step=1.0)

st.sidebar.subheader("Wärmelieferung – Angebotspreise (§10)")
st.sidebar.markdown("*Preise des Wärmelieferanten (netto)*")
default_grundpreis = st.sidebar.number_input("Grundpreis (€/Monat netto)", value=lp.get("grundpreis_netto", 0.0), step=10.0)
default_arbeitspreis = st.sidebar.number_input("Arbeitspreis (ct/kWh netto)", value=lp.get("arbeitspreis_netto", 0.0), step=0.1)

st.sidebar.subheader("Preisgleitklausel (optional)")
fix_gp = st.sidebar.number_input("FixGP", value=lp.get("fix_gp", 0.0), step=0.01, format="%.4f")
fix_ap = st.sidebar.number_input("FixAP", value=lp.get("fix_ap", 0.0), step=0.01, format="%.4f")

preisindex_count = st.sidebar.number_input("Anzahl Preisindizes", value=0, min_value=0, max_value=5, step=1)
preisindizes_gp = []
preisindizes_ap = []
for i in range(int(preisindex_count)):
    st.sidebar.markdown(f"**Index {i+1}**")
    gi = st.sidebar.number_input(f"G{i+1} (Anteil GP)", value=0.0, key=f"gi_{i}", format="%.4f")
    gpi_basis = st.sidebar.number_input(f"GP{i+1}B (Basis)", value=100.0, key=f"gpib_{i}")
    gpi_aktuell = st.sidebar.number_input(f"GP{i+1} (Aktuell)", value=100.0, key=f"gpi_{i}")
    preisindizes_gp.append({"anteil": gi, "basis": gpi_basis, "aktuell": gpi_aktuell})

    ai = st.sidebar.number_input(f"A{i+1} (Anteil AP)", value=0.0, key=f"ai_{i}", format="%.4f")
    api_basis = st.sidebar.number_input(f"AP{i+1}B (Basis)", value=100.0, key=f"apib_{i}")
    api_aktuell = st.sidebar.number_input(f"AP{i+1} (Aktuell)", value=100.0, key=f"api_{i}")
    preisindizes_ap.append({"anteil": ai, "basis": api_basis, "aktuell": api_aktuell})

# Projekt speichern Button in Sidebar
st.sidebar.markdown("---")
if st.sidebar.button("💾 Projekt speichern"):
    if st.session_state.get("current_project"):
        project_data = {
            "name": st.session_state["current_project"],
            "created": datetime.now().isoformat(),
            "params": {
                "ust_satz": ust_satz,
                "grundpreis_netto": default_grundpreis,
                "arbeitspreis_netto": default_arbeitspreis,
                "fix_gp": fix_gp,
                "fix_ap": fix_ap,
                "ww_kwh_pro_m2": ww_kwh_pro_m2,
                "preisindizes_gp": preisindizes_gp,
                "preisindizes_ap": preisindizes_ap,
                "nutzungsgrade": {k: v for k, v in nutzungsgrade.items()},
            },
            "imported_data": st.session_state.get("imported_data").to_dict(orient="records") if st.session_state.get("imported_data") is not None else None,
            "manual_data": st.session_state.get("manual_data", []),
            "results": st.session_state["results"].to_dict(orient="records") if "results" in st.session_state else None,
        }
        save_project(st.session_state["current_project"], project_data)
        st.sidebar.success(f"Projekt '{st.session_state['current_project']}' gespeichert!")
    else:
        st.sidebar.error("Bitte erst ein Projekt anlegen oder laden.")

params = {
    "ust_satz": ust_satz,
    "nutzungsgrade": nutzungsgrade,
    "grundpreis_netto": default_grundpreis,
    "arbeitspreis_netto": default_arbeitspreis,
    "fix_gp": fix_gp,
    "fix_ap": fix_ap,
    "preisindizes_gp": preisindizes_gp,
    "preisindizes_ap": preisindizes_ap,
    "ww_kwh_pro_m2": ww_kwh_pro_m2,
}

# --- Main Tabs ---
tab1, tab2, tab3 = st.tabs(["📁 Datenimport & Berechnung", "✏️ Manuelle Eingabe", "📊 Ergebnisse je Standort"])

with tab1:
    st.header("Daten importieren")
    st.markdown("""
    Laden Sie eine CSV- oder Excel-Datei mit den Verbrauchsdaten hoch.  
    Die Datei wird automatisch nach **Standorten (Heizzentrale)** aufgeteilt und berechnet.
    """)

    if default_grundpreis == 0 and default_arbeitspreis == 0:
        st.warning("⚠️ Bitte zuerst die **Angebotspreise** in der Sidebar eingeben (Grundpreis und/oder Arbeitspreis).")

    uploaded_file = st.file_uploader("CSV oder Excel-Datei hochladen", type=["csv", "xlsx", "xls"])

    if uploaded_file:
        df = import_data(uploaded_file)
        if df is not None:
            st.session_state["imported_data"] = df

            # Automatische Erkennung der Standorte
            if "Heizzentrale" in df.columns:
                standorte = df["Heizzentrale"].dropna().unique()
                st.success(f"✅ {len(df)} Zeilen importiert – **{len(standorte)} Standort(e)** erkannt")

                # Anzeige der erkannten Standorte mit Zeiträumen
                with st.expander("📋 Erkannte Standorte und Zeiträume", expanded=True):
                    for site in standorte:
                        site_data = df[df["Heizzentrale"] == site]
                        n_periods = len(site_data)
                        verbrauch_col = "Brennstoff_kWh" if "Brennstoff_kWh" in site_data.columns else None
                        if verbrauch_col:
                            values = site_data[verbrauch_col].dropna()
                            values = values[values > 0]
                            n_valid = len(values)
                        else:
                            n_valid = 0
                        st.write(f"**{site}** – {n_periods} Zeile(n), {n_valid} Verbrauchswert(e)")
            else:
                st.warning("⚠️ Spalte 'Heizzentrale' nicht erkannt. Bitte prüfen Sie die Spaltennamen.")
                st.dataframe(df.head(), use_container_width=True)

            # Automatische Berechnung
            st.markdown("---")
            if st.button("🔄 Alle Standorte berechnen", type="primary"):
                results = calculate_kostenvergleich(df, params)
                st.session_state["results"] = results
                # Auto-save to project
                if st.session_state.get("current_project"):
                    project_data = {
                        "name": st.session_state["current_project"],
                        "created": datetime.now().isoformat(),
                        "params": {
                            "ust_satz": ust_satz,
                            "grundpreis_netto": default_grundpreis,
                            "arbeitspreis_netto": default_arbeitspreis,
                            "fix_gp": fix_gp,
                            "fix_ap": fix_ap,
                            "ww_kwh_pro_m2": ww_kwh_pro_m2,
                            "preisindizes_gp": preisindizes_gp,
                            "preisindizes_ap": preisindizes_ap,
                            "nutzungsgrade": {k: v for k, v in nutzungsgrade.items()},
                        },
                        "imported_data": df.to_dict(orient="records"),
                        "manual_data": st.session_state.get("manual_data", []),
                        "results": results.to_dict(orient="records"),
                    }
                    save_project(st.session_state["current_project"], project_data)

            # Ergebnisübersicht direkt anzeigen
            if "results" in st.session_state and not st.session_state["results"].empty:
                results = st.session_state["results"]
                st.markdown("---")
                st.subheader("📊 Ergebnis-Übersicht")

                # Zusammenfassung
                n_bestanden = len(results[results["Ergebnis"].str.contains("erfüllt") & ~results["Ergebnis"].str.contains("nicht")])
                n_nicht = len(results) - n_bestanden
                met_col1, met_col2, met_col3 = st.columns(3)
                met_col1.metric("Standorte gesamt", len(results))
                met_col2.metric("§8 erfüllt ✅", n_bestanden)
                met_col3.metric("§8 nicht erfüllt ❌", n_nicht)

                # Übersichtstabelle
                summary = results[["Heizzentrale", "Betriebskosten_bisherig_brutto",
                                 "Kosten_Waermelieferung_brutto", "Differenz_Euro", "Ergebnis"]].copy()
                summary.columns = ["Standort", "§9 Bisherige Kosten (€/a)",
                                 "§10 Wärmelieferung (€/a)", "Differenz (€/a)", "Ergebnis §8"]

                def highlight_result(val):
                    if "erfüllt" in str(val) and "nicht" not in str(val):
                        return "background-color: #90EE90"
                    elif "nicht erfüllt" in str(val):
                        return "background-color: #FFB6C1"
                    return ""

                st.dataframe(
                    summary.style.map(highlight_result, subset=["Ergebnis §8"]),
                    use_container_width=True
                )

                # Export
                st.subheader("Export")
                col_exp1, col_exp2 = st.columns(2)
                with col_exp1:
                    csv = results.to_csv(index=False, sep=";", decimal=",")
                    st.download_button("📥 CSV Export", csv, "kostenvergleich_ergebnisse.csv", "text/csv")
                with col_exp2:
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                        results.to_excel(writer, index=False, sheet_name="Ergebnisse")
                    st.download_button("📥 Excel Export", buffer.getvalue(),
                                     "kostenvergleich_ergebnisse.xlsx",
                                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab2:
    st.header("Manuelle Dateneingabe")
    st.markdown("Standorte manuell hinzufügen (alternativ zum Dateiimport)")

    if "manual_data" not in st.session_state:
        st.session_state["manual_data"] = []

    with st.form("add_site"):
        col1, col2, col3 = st.columns(3)
        with col1:
            heizzentrale = st.text_input("Heizzentrale")
            brennstoffart = st.selectbox("Brennstoffart", ["Erdgas", "Heizöl", "Pellets", "Fernwärme"])
            technologie = st.selectbox("Technologie", ["Brennwert", "Niedertemperatur", "Standardkessel", "Konstanttemperatur"])
        with col2:
            kessel = st.text_input("Kessel")
            leistung_kw = st.number_input("Leistung (kW)", value=0.0)
            baujahr = st.text_input("Baujahr")
            warmwasser = st.selectbox("Zentrale Warmwasseraufbereitung", ["ja", "nein"])
        with col3:
            heizflaeche = st.number_input("Heizfläche (m²)", value=0.0)

        st.markdown("**Abrechnungszeiträume (bis zu 3)**")
        periods = []
        for p in range(3):
            st.markdown(f"Zeitraum {p+1}")
            pc1, pc2, pc3, pc4, pc5 = st.columns(5)
            with pc1:
                periode = st.text_input(f"Periode {p+1}", key=f"per_{p}")
            with pc2:
                brennstoff_kwh = st.number_input(f"Brennstoff kWh {p+1}", value=0.0, key=f"bkwh_{p}")
            with pc3:
                brennstoffkosten = st.number_input(f"Brennstoffkosten € {p+1}", value=0.0, key=f"bk_{p}")
            with pc4:
                wartung = st.number_input(f"Wartung € {p+1}", value=0.0, key=f"w_{p}")
                schornsteinfeger = st.number_input(f"Schornsteinfeger € {p+1}", value=0.0, key=f"sf_{p}")
            with pc5:
                betriebsstrom = st.number_input(f"Betriebsstrom € {p+1}", value=0.0, key=f"bs_{p}")
            if periode:
                periods.append({
                    "periode": periode,
                    "brennstoff_kwh": brennstoff_kwh,
                    "brennstoffkosten": brennstoffkosten,
                    "wartung": wartung,
                    "schornsteinfeger": schornsteinfeger,
                    "betriebsstrom": betriebsstrom,
                })

        submitted = st.form_submit_button("Standort hinzufügen")
        if submitted and heizzentrale:
            for period in periods:
                st.session_state["manual_data"].append({
                    "Heizzentrale": heizzentrale,
                    "Brennstoffart": brennstoffart,
                    "Kessel": kessel,
                    "Leistung_kW": leistung_kw,
                    "Technologie": technologie,
                    "Baujahr": baujahr,
                    "Warmwasser": warmwasser,
                    "Abrechnungsperiode": period["periode"],
                    "Brennstoff_kWh": period["brennstoff_kwh"],
                    "Brennstoffkosten": period["brennstoffkosten"],
                    "Wartung": period["wartung"],
                    "Schornsteinfeger": period["schornsteinfeger"],
                    "Betriebsstrom": period["betriebsstrom"],
                    "Heizflaeche_m2": heizflaeche,
                })
            st.success(f"Standort '{heizzentrale}' mit {len(periods)} Zeiträumen hinzugefügt")

    if st.session_state["manual_data"]:
        df_manual = pd.DataFrame(st.session_state["manual_data"])
        st.dataframe(df_manual, use_container_width=True)

        man_col1, man_col2 = st.columns(2)
        with man_col1:
            if st.button("🔄 Manuelle Daten berechnen"):
                results = calculate_kostenvergleich(df_manual, params)
                st.session_state["results"] = results
                st.rerun()
        with man_col2:
            if st.button("🗑️ Manuelle Daten löschen"):
                st.session_state["manual_data"] = []
                st.rerun()

with tab3:
    st.header("📊 Ergebnisse je Standort")

    if "results" in st.session_state and not st.session_state["results"].empty:
        results = st.session_state["results"]

        # Standort-Filter
        standort_filter = st.selectbox(
            "Standort auswählen",
            ["Alle Standorte"] + list(results["Heizzentrale"].unique())
        )

        if standort_filter != "Alle Standorte":
            results_filtered = results[results["Heizzentrale"] == standort_filter]
        else:
            results_filtered = results

        for idx, row in results_filtered.iterrows():
            with st.expander(f"{'✅' if 'nicht' not in row['Ergebnis'] else '❌'} {row['Heizzentrale']}", expanded=(standort_filter != "Alle Standorte")):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown("**§9 Bisherige Versorgung**")
                    st.metric("Betriebskosten bisher", f"{row['Betriebskosten_bisherig_brutto']:.2f} €/a")
                    st.write(f"Ø Energieverbrauch: {row['Durchschnitt_Verbrauch_kWh']:.0f} kWh/a")
                    st.write(f"Anzahl Zeiträume: {row['Anzahl_Zeitraeume']}")
                    st.write(f"Brennstoffpreis: {row['Preis_ct_kWh_Brennstoff']:.2f} ct/kWh")
                    st.write(f"Verbrauchskosten: {row['Verbrauchskosten_S9']:.2f} €/a")
                    st.write(f"Sonstige Kosten: {row['Sonstige_Betriebskosten_S9']:.2f} €/a")
                with c2:
                    st.markdown("**§10 Wärmelieferung**")
                    st.metric("Kosten Wärmelieferung", f"{row['Kosten_Waermelieferung_brutto']:.2f} €/a")
                    st.write(f"Nutzungsgrad Altanlage: {row['Nutzungsgrad']*100:.1f}%")
                    st.write(f"Wärmemenge Heizung: {row['Waermemenge_Heizung_kWh']:.0f} kWh/a")
                    st.write(f"Wärmemenge gesamt: {row['Waermemenge_gesamt_kWh']:.0f} kWh/a")
                    st.write(f"Warmwasser: {row['Warmwasser']}")
                    st.write(f"Grundkosten: {row['Grundkosten_brutto']:.2f} €/a")
                    st.write(f"Arbeitskosten: {row['Arbeitskosten_brutto']:.2f} €/a")
                with c3:
                    st.markdown("**§8 Ergebnis**")
                    differenz = row['Differenz_Euro']
                    if differenz >= 0:
                        st.metric("Ersparnis", f"{differenz:.2f} €/a", delta=f"{differenz:.2f}")
                    else:
                        st.metric("Mehrkosten", f"{abs(differenz):.2f} €/a", delta=f"{differenz:.2f}")
                    st.write(f"Technologie: {row['Technologie']}")
                    st.write(f"Brennstoffart: {row['Brennstoffart']}")
                    st.write(f"Leistung: {row['Leistung_kW']} kW")
                    st.write(f"Heizfläche: {row['Heizflaeche_m2']:.0f} m²")
    else:
        st.info("Noch keine Ergebnisse. Bitte Daten importieren und Berechnung starten.")
