import streamlit as st
import pandas as pd
import io
import json
import os
from datetime import datetime
from calculation import calculate_kostenvergleich
from data_import import import_data, parse_german_number

st.set_page_config(page_title="Kostenvergleich §8 WärmeLV", layout="wide")
st.title("Kostenvergleich der Wärmelieferung gemäß §8 WärmeLV")
st.markdown("""
**Regulatorischer Hintergrund:**  
§8 WärmeLV schreibt vor, dass die Kosten der Wärmelieferung (§10) die bisherigen 
Betriebskosten der Eigenversorgung (§9) nicht übersteigen dürfen.
Dieses Tool berechnet beide Seiten und prüft die Einhaltung.
""")

# --- Sidebar: Anpassbare Parameter ---
st.sidebar.header("⚙️ Berechnungsparameter")

st.sidebar.subheader("Allgemein")
ust_satz = st.sidebar.number_input("USt-Satz (%)", value=19.0, step=0.1) / 100

st.sidebar.subheader("Jahresnutzungsgrade Altanlage (%)")
st.sidebar.markdown("*BMVBS-Pauschalwerte oder individuell*")
nutzungsgrade = {
    "Brennwert": st.sidebar.number_input("Brennwert", value=96.0, step=0.5) / 100,
    "Niedertemperatur": st.sidebar.number_input("Niedertemperatur", value=84.9, step=0.5) / 100,
    "Standardkessel": st.sidebar.number_input("Standardkessel", value=80.0, step=0.5) / 100,
    "Konstanttemperatur": st.sidebar.number_input("Konstanttemperatur", value=78.0, step=0.5) / 100,
}

st.sidebar.subheader("Warmwasser")
st.sidebar.markdown("*Bei zentraler WW-Aufbereitung*")
ww_kwh_pro_m2 = st.sidebar.number_input("WW-Pauschale (kWh/m²/a)", value=20.0, step=1.0,
    help="Typischer Wert: 20-30 kWh/m²/a für zentrale Warmwasseraufbereitung")

st.sidebar.subheader("Wärmelieferung – Angebotspreise (§10)")
st.sidebar.markdown("*Preise des Wärmelieferanten (netto)*")
default_grundpreis = st.sidebar.number_input("Grundpreis (€/Monat netto)", value=0.0, step=10.0,
    help="Monatlicher Grundpreis der Wärmelieferung")
default_arbeitspreis = st.sidebar.number_input("Arbeitspreis (ct/kWh netto)", value=0.0, step=0.1,
    help="Arbeitspreis pro kWh gelieferter Wärme")

st.sidebar.subheader("Preisgleitklausel (optional)")
st.sidebar.markdown("*Für Preisbereinigung GP/AP-Formeln*")
fix_gp = st.sidebar.number_input("FixGP (Fixanteil Grundpreis)", value=0.0, step=0.01, format="%.4f")
fix_ap = st.sidebar.number_input("FixAP (Fixanteil Arbeitspreis)", value=0.0, step=0.01, format="%.4f")

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
tab1, tab2, tab3, tab4 = st.tabs(["📁 Datenimport", "✏️ Manuelle Eingabe", "📊 Ergebnisse", "💾 Speichern/Laden"])

with tab1:
    st.header("Daten importieren")
    st.markdown("""
    Laden Sie eine CSV- oder Excel-Datei mit den Verbrauchsdaten hoch.  
    Spalten werden automatisch erkannt. Mehrere Abrechnungszeiträume pro Standort 
    werden als separate Zeilen mit gleichem Standortnamen erwartet.
    """)
    uploaded_file = st.file_uploader("CSV oder Excel-Datei hochladen", type=["csv", "xlsx", "xls"])

    if uploaded_file:
        df = import_data(uploaded_file)
        if df is not None:
            st.success(f"{len(df)} Zeilen importiert")
            st.dataframe(df, use_container_width=True)
            st.session_state["imported_data"] = df

with tab2:
    st.header("Manuelle Dateneingabe")
    st.markdown("Standorte manuell hinzufügen")

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
        if st.button("Manuelle Daten löschen"):
            st.session_state["manual_data"] = []
            st.rerun()

with tab3:
    st.header("Ergebnisse Kostenvergleich §8 WärmeLV")

    # Check if prices are set
    if default_grundpreis == 0 and default_arbeitspreis == 0:
        st.warning("⚠️ **Bitte Angebotspreise der Wärmelieferung in der Sidebar eingeben** "
                   "(Grundpreis €/Monat und/oder Arbeitspreis ct/kWh), damit der Vergleich "
                   "nach §10 WärmeLV durchgeführt werden kann.")

    # Combine data sources
    dfs = []
    if "imported_data" in st.session_state and st.session_state["imported_data"] is not None:
        dfs.append(st.session_state["imported_data"])
    if st.session_state.get("manual_data"):
        dfs.append(pd.DataFrame(st.session_state["manual_data"]))

    if dfs:
        df_all = pd.concat(dfs, ignore_index=True)

        if st.button("🔄 Berechnung starten"):
            results = calculate_kostenvergleich(df_all, params)
            st.session_state["results"] = results

        if "results" in st.session_state:
            results = st.session_state["results"]

            # Summary table
            st.subheader("Übersicht")
            st.markdown("""
            | Spalte | Bedeutung |
            |--------|-----------|
            | **Betriebskosten bisher** | Kosten der Eigenversorgung nach §9 WärmeLV |
            | **Kosten Wärmelieferung** | Kosten des Wärmelieferangebots nach §10 WärmeLV |
            | **Differenz** | Positiv = Kostenersparnis durch WL, Negativ = WL teurer |
            """)

            summary = results[["Heizzentrale", "Betriebskosten_bisherig_brutto",
                             "Kosten_Waermelieferung_brutto", "Differenz_Euro", "Ergebnis"]].copy()
            summary.columns = ["Standort", "§9 Betriebskosten bisher (€/a)",
                             "§10 Kosten Wärmelieferung (€/a)", "Differenz (€/a)", "Ergebnis §8"]

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

            # Detail view
            st.subheader("Detailansicht")
            for idx, row in results.iterrows():
                with st.expander(f"{row['Heizzentrale']} - {row['Ergebnis']}"):
                    st.markdown("---")
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
                        st.write(f"Heizfläche: {row['Heizflaeche_m2']:.0f} m²")

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
    else:
        st.info("Bitte importieren Sie Daten oder geben Sie Standorte manuell ein.")

with tab4:
    st.header("💾 Ergebnisse Speichern / Laden")
    st.markdown("Speichern Sie den kompletten Berechnungsstand (Daten + Parameter + Ergebnisse) als JSON-Datei.")

    col_save, col_load = st.columns(2)

    with col_save:
        st.subheader("Speichern")
        if st.button("💾 Aktuellen Stand speichern"):
            save_data = {
                "timestamp": datetime.now().isoformat(),
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
            }
            if "imported_data" in st.session_state and st.session_state["imported_data"] is not None:
                save_data["imported_data"] = st.session_state["imported_data"].to_dict(orient="records")
            if st.session_state.get("manual_data"):
                save_data["manual_data"] = st.session_state["manual_data"]
            if "results" in st.session_state:
                save_data["results"] = st.session_state["results"].to_dict(orient="records")

            json_str = json.dumps(save_data, ensure_ascii=False, indent=2, default=str)
            filename = f"kostenvergleich_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            st.download_button("📥 JSON herunterladen", json_str, filename, "application/json")

    with col_load:
        st.subheader("Laden")
        uploaded_json = st.file_uploader("Gespeicherte JSON-Datei laden", type=["json"], key="json_upload")
        if uploaded_json:
            try:
                loaded = json.loads(uploaded_json.read().decode("utf-8"))
                st.success(f"Datei geladen (gespeichert am: {loaded.get('timestamp', 'unbekannt')})")

                if "imported_data" in loaded:
                    st.session_state["imported_data"] = pd.DataFrame(loaded["imported_data"])
                if "manual_data" in loaded:
                    st.session_state["manual_data"] = loaded["manual_data"]
                if "results" in loaded:
                    st.session_state["results"] = pd.DataFrame(loaded["results"])

                st.info("Daten geladen. Wechseln Sie zum Tab 'Ergebnisse' um die Ergebnisse zu sehen, "
                       "oder starten Sie eine neue Berechnung mit den geladenen Daten.")
            except Exception as e:
                st.error(f"Fehler beim Laden: {e}")
