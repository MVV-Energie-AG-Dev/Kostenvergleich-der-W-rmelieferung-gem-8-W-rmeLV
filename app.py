import streamlit as st
import pandas as pd
import io
from calculation import calculate_kostenvergleich
from data_import import import_data, parse_german_number

st.set_page_config(page_title="Kostenvergleich §8 WärmeLV", layout="wide")
st.title("Kostenvergleich der Wärmelieferung gemäß §8 WärmeLV")
st.markdown("Bulk-Berechnung für mehrere Standorte")

# --- Sidebar: Anpassbare Parameter ---
st.sidebar.header("Berechnungsparameter")

ust_satz = st.sidebar.number_input("USt-Satz (%)", value=19.0, step=0.1) / 100

st.sidebar.subheader("Heizwerte (kWh/Einheit)")
heizwerte = {
    "Erdgas": st.sidebar.number_input("Erdgas (kWh/m³)", value=10.0, step=0.1),
    "Heizöl": st.sidebar.number_input("Heizöl (kWh/l)", value=10.0, step=0.1),
    "Pellets": st.sidebar.number_input("Pellets (kWh/kg)", value=4.9, step=0.1),
    "Fernwärme": st.sidebar.number_input("Fernwärme (kWh/kWh)", value=1.0, step=0.1),
}

st.sidebar.subheader("Jahresnutzungsgrade (%)")
nutzungsgrade = {
    "Brennwert": st.sidebar.number_input("Brennwert", value=96.0, step=0.5) / 100,
    "Niedertemperatur": st.sidebar.number_input("Niedertemperatur", value=84.9, step=0.5) / 100,
    "Standardkessel": st.sidebar.number_input("Standardkessel", value=80.0, step=0.5) / 100,
    "Konstanttemperatur": st.sidebar.number_input("Konstanttemperatur", value=78.0, step=0.5) / 100,
}

st.sidebar.subheader("Wärmelieferung - Preise")
default_grundpreis = st.sidebar.number_input("Default Grundpreis (€/Monat netto)", value=0.0, step=10.0)
default_arbeitspreis = st.sidebar.number_input("Default Arbeitspreis (ct/kWh netto)", value=0.0, step=0.1)

st.sidebar.subheader("Preisindizes")
st.sidebar.markdown("Für Preisbereinigung (GP/AP-Formeln)")
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
    "heizwerte": heizwerte,
    "nutzungsgrade": nutzungsgrade,
    "grundpreis_netto": default_grundpreis,
    "arbeitspreis_netto": default_arbeitspreis,
    "fix_gp": fix_gp,
    "fix_ap": fix_ap,
    "preisindizes_gp": preisindizes_gp,
    "preisindizes_ap": preisindizes_ap,
}

# --- Main: Datenimport ---
tab1, tab2, tab3 = st.tabs(["📁 Datenimport", "✏️ Manuelle Eingabe", "📊 Ergebnisse"])

with tab1:
    st.header("Daten importieren")
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

        st.markdown("**Abrechnungszeiträume**")
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
    st.header("Ergebnisse Kostenvergleich")

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
            summary = results[["Heizzentrale", "Betriebskosten_bisherig_brutto",
                             "Kosten_Waermelieferung_brutto", "Ergebnis"]].copy()
            summary.columns = ["Standort", "Betriebskosten bisher (€/a)",
                             "Kosten Wärmelieferung (€/a)", "Ergebnis"]

            def highlight_result(val):
                if val == "✅ Bestanden":
                    return "background-color: #90EE90"
                elif val == "❌ Nicht bestanden":
                    return "background-color: #FFB6C1"
                return ""

            st.dataframe(
                summary.style.applymap(highlight_result, subset=["Ergebnis"]),
                use_container_width=True
            )

            # Detail view
            st.subheader("Detailansicht")
            for idx, row in results.iterrows():
                with st.expander(f"{row['Heizzentrale']} - {row['Ergebnis']}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.metric("Betriebskosten bisher", f"{row['Betriebskosten_bisherig_brutto']:.2f} €/a")
                        st.write(f"Ø Energieverbrauch: {row['Durchschnitt_Verbrauch_kWh']:.0f} kWh/a")
                        st.write(f"Ø Wärmemenge: {row['Waermemenge_kWh']:.0f} kWh/a")
                        st.write(f"Jahresnutzungsgrad: {row['Nutzungsgrad']*100:.1f}%")
                    with c2:
                        st.metric("Kosten Wärmelieferung", f"{row['Kosten_Waermelieferung_brutto']:.2f} €/a")
                        st.write(f"Grundkosten: {row['Grundkosten_brutto']:.2f} €/a")
                        st.write(f"Arbeitskosten: {row['Arbeitskosten_brutto']:.2f} €/a")

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
