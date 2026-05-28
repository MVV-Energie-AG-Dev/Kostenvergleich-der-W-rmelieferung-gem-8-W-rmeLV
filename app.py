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
    if not os.path.exists(PROJECTS_DIR):
        return []
    return sorted([f.replace(".json", "") for f in os.listdir(PROJECTS_DIR) if f.endswith(".json")])


def save_project(name, data):
    filepath = os.path.join(PROJECTS_DIR, f"{name}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def load_project(name):
    filepath = os.path.join(PROJECTS_DIR, f"{name}.json")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# --- Projekt-Verwaltung ---
st.title("Kostenvergleich der Wärmelieferung gemäß §8 WärmeLV")

proj_col1, proj_col2, proj_col3, proj_col4 = st.columns([3, 2, 2, 2])
with proj_col1:
    projects = get_project_list()
    if "current_project" not in st.session_state:
        st.session_state["current_project"] = None
    selected_project = st.selectbox("📂 Projekt", ["-- Neues Projekt --"] + projects, index=0)
with proj_col2:
    new_project_name = st.text_input("Projektname", placeholder="z.B. Quartier Nord 2026")
with proj_col3:
    if st.button("➕ Neues Projekt"):
        if new_project_name:
            save_project(new_project_name, {"name": new_project_name, "created": datetime.now().isoformat()})
            st.session_state["current_project"] = new_project_name
            st.session_state["imported_data"] = None
            st.session_state["manual_data"] = []
            st.session_state.pop("results", None)
            st.session_state["site_params"] = {}
            st.rerun()
with proj_col4:
    if st.button("📂 Laden") and selected_project != "-- Neues Projekt --":
        loaded = load_project(selected_project)
        st.session_state["current_project"] = selected_project
        st.session_state["imported_data"] = pd.DataFrame(loaded["imported_data"]) if loaded.get("imported_data") else None
        st.session_state["manual_data"] = loaded.get("manual_data", [])
        st.session_state["site_params"] = loaded.get("site_params", {})
        if loaded.get("results"):
            st.session_state["results"] = pd.DataFrame(loaded["results"])
        st.rerun()

if st.session_state.get("current_project"):
    st.info(f"📂 **Projekt:** {st.session_state['current_project']}")

st.markdown("---")

# --- Sidebar: Default-Parameter (werden pro Standort überschreibbar) ---
st.sidebar.header("⚙️ Default-Parameter")
st.sidebar.markdown("*Gelten für alle Standorte, sofern nicht individuell überschrieben*")

st.sidebar.subheader("Allgemein")
ust_satz = st.sidebar.number_input("USt-Satz (%)", value=19.0, step=0.1) / 100
default_betriebsstunden = st.sidebar.number_input("Betriebsstunden (h/a)", value=0, step=100,
    help="Nur nötig wenn Verbrauch in kW statt kWh angegeben ist. kWh = kW × Betriebsstunden")

st.sidebar.subheader("Jahresnutzungsgrade Altanlage (%)")
nutzungsgrade = {
    "Brennwert": st.sidebar.number_input("Brennwert", value=96.0, step=0.5) / 100,
    "Niedertemperatur": st.sidebar.number_input("Niedertemperatur", value=84.9, step=0.5) / 100,
    "Standardkessel": st.sidebar.number_input("Standardkessel", value=80.0, step=0.5) / 100,
    "Konstanttemperatur": st.sidebar.number_input("Konstanttemperatur", value=78.0, step=0.5) / 100,
}

st.sidebar.subheader("Warmwasser")
ww_kwh_pro_m2 = st.sidebar.number_input("WW-Pauschale (kWh/m²/a)", value=20.0, step=1.0)

st.sidebar.subheader("Wärmelieferung – Angebotspreise (§10)")
default_grundpreis = st.sidebar.number_input("GPB – Grundpreis Basis (€/Monat netto)", value=0.0, step=10.0)
default_arbeitspreis = st.sidebar.number_input("APB – Arbeitspreis Basis (ct/kWh netto)", value=0.0, step=0.1)

st.sidebar.subheader("Preisgleitklausel")
st.sidebar.latex(r"GP = GPB \times (FixGP + G_1 \cdot \frac{GP_1}{GP_{1B}} + G_2 \cdot \frac{GP_2}{GP_{2B}} + \ldots)")
st.sidebar.latex(r"AP = APB \times (FixAP + A_1 \cdot \frac{AP_1}{AP_{1B}} + A_2 \cdot \frac{AP_2}{AP_{2B}} + \ldots)")

fix_gp = st.sidebar.number_input("FixGP", value=0.0, step=0.01, format="%.4f")
fix_ap = st.sidebar.number_input("FixAP", value=0.0, step=0.01, format="%.4f")

preisindex_count = st.sidebar.number_input("Anzahl Preisindizes", value=0, min_value=0, max_value=5, step=1)
preisindizes_gp = []
preisindizes_ap = []
for i in range(int(preisindex_count)):
    st.sidebar.markdown(f"**Index {i+1}**")
    gi = st.sidebar.number_input(f"G{i+1}", value=0.0, key=f"gi_{i}", format="%.4f")
    gpi_basis = st.sidebar.number_input(f"GP{i+1}B (Basis)", value=100.0, key=f"gpib_{i}")
    gpi_aktuell = st.sidebar.number_input(f"GP{i+1} (Aktuell)", value=100.0, key=f"gpi_{i}")
    preisindizes_gp.append({"anteil": gi, "basis": gpi_basis, "aktuell": gpi_aktuell})
    ai = st.sidebar.number_input(f"A{i+1}", value=0.0, key=f"ai_{i}", format="%.4f")
    api_basis = st.sidebar.number_input(f"AP{i+1}B (Basis)", value=100.0, key=f"apib_{i}")
    api_aktuell = st.sidebar.number_input(f"AP{i+1} (Aktuell)", value=100.0, key=f"api_{i}")
    preisindizes_ap.append({"anteil": ai, "basis": api_basis, "aktuell": api_aktuell})

# Speichern
st.sidebar.markdown("---")
if st.sidebar.button("💾 Projekt speichern"):
    if st.session_state.get("current_project"):
        project_data = {
            "name": st.session_state["current_project"],
            "created": datetime.now().isoformat(),
            "params": {"ust_satz": ust_satz, "grundpreis_netto": default_grundpreis,
                       "arbeitspreis_netto": default_arbeitspreis, "betriebsstunden": default_betriebsstunden,
                       "fix_gp": fix_gp, "fix_ap": fix_ap, "ww_kwh_pro_m2": ww_kwh_pro_m2},
            "imported_data": st.session_state.get("imported_data").to_dict(orient="records") if st.session_state.get("imported_data") is not None else None,
            "manual_data": st.session_state.get("manual_data", []),
            "site_params": st.session_state.get("site_params", {}),
            "results": st.session_state["results"].to_dict(orient="records") if "results" in st.session_state else None,
        }
        save_project(st.session_state["current_project"], project_data)
        st.sidebar.success("Gespeichert!")

params = {
    "ust_satz": ust_satz,
    "nutzungsgrade": nutzungsgrade,
    "grundpreis_netto": default_grundpreis,
    "arbeitspreis_netto": default_arbeitspreis,
    "betriebsstunden": default_betriebsstunden,
    "fix_gp": fix_gp,
    "fix_ap": fix_ap,
    "preisindizes_gp": preisindizes_gp,
    "preisindizes_ap": preisindizes_ap,
    "ww_kwh_pro_m2": ww_kwh_pro_m2,
}

# --- Main Tabs ---
tab1, tab2, tab3 = st.tabs(["📁 Datenimport & Standort-Parameter", "📊 Ergebnisse", "ℹ️ Formeln & Methodik"])

with tab1:
    st.header("1. Daten importieren")
    uploaded_file = st.file_uploader("CSV oder Excel-Datei hochladen", type=["csv", "xlsx", "xls"])

    if uploaded_file:
        df = import_data(uploaded_file)
        if df is not None:
            st.session_state["imported_data"] = df

    # Show imported data
    if st.session_state.get("imported_data") is not None:
        df = st.session_state["imported_data"]
        if "Heizzentrale" in df.columns:
            standorte = df["Heizzentrale"].dropna().unique()
            st.success(f"✅ {len(df)} Zeilen – **{len(standorte)} Standort(e)** erkannt")

            # --- 2. Standort-spezifische Parameter ---
            st.header("2. Parameter je Standort")
            st.markdown("Individuelle Angaben pro Standort (überschreiben die Defaults links).")

            if "site_params" not in st.session_state:
                st.session_state["site_params"] = {}

            for site in standorte:
                site_data = df[df["Heizzentrale"] == site]
                sp = st.session_state["site_params"].get(site, {})

                with st.expander(f"⚙️ {site}", expanded=False):
                    # Abrechnungsperioden anzeigen
                    if "Abrechnungsperiode" in site_data.columns:
                        perioden = site_data["Abrechnungsperiode"].dropna().tolist()
                        if perioden:
                            st.markdown("**Abrechnungsperioden:**")
                            for i, p in enumerate(perioden):
                                verbrauch = site_data.iloc[i].get("Brennstoff_kWh", 0)
                                st.write(f"  📅 {p} — {verbrauch:,.0f} kWh")

                    sc1, sc2, sc3 = st.columns(3)
                    with sc1:
                        st.markdown("**Anlagenparameter**")
                        site_betriebsstunden = st.number_input(
                            "Betriebsstunden (h/a)", value=sp.get("betriebsstunden", default_betriebsstunden),
                            step=100, key=f"bst_{site}",
                            help="Für Umrechnung kW → kWh")
                        site_nutzungsgrad = st.number_input(
                            "Nutzungsgrad (%)", value=sp.get("nutzungsgrad", 0.0) * 100 if sp.get("nutzungsgrad") else 0.0,
                            step=0.5, key=f"ng_{site}",
                            help="0 = automatisch aus Technologie") / 100
                        site_ww = st.number_input(
                            "WW-Pauschale (kWh/m²/a)", value=sp.get("ww_kwh_pro_m2", ww_kwh_pro_m2),
                            step=1.0, key=f"ww_{site}")

                    with sc2:
                        st.markdown("**Angebotspreise WL**")
                        site_gp = st.number_input(
                            "GPB (€/Monat netto)", value=sp.get("grundpreis_netto", 0.0),
                            step=10.0, key=f"gp_{site}",
                            help="0 = Default aus Sidebar")
                        site_ap = st.number_input(
                            "APB (ct/kWh netto)", value=sp.get("arbeitspreis_netto", 0.0),
                            step=0.1, key=f"ap_{site}",
                            help="0 = Default aus Sidebar")

                    with sc3:
                        st.markdown("**Preisgleitklausel**")
                        site_fix_gp = st.number_input(
                            "FixGP", value=sp.get("fix_gp", fix_gp),
                            step=0.01, format="%.4f", key=f"sfgp_{site}")
                        site_fix_ap = st.number_input(
                            "FixAP", value=sp.get("fix_ap", fix_ap),
                            step=0.01, format="%.4f", key=f"sfap_{site}")

                    # Save site params
                    st.session_state["site_params"][site] = {
                        "betriebsstunden": site_betriebsstunden,
                        "nutzungsgrad": site_nutzungsgrad if site_nutzungsgrad > 0 else None,
                        "ww_kwh_pro_m2": site_ww,
                        "grundpreis_netto": site_gp if site_gp > 0 else None,
                        "arbeitspreis_netto": site_ap if site_ap > 0 else None,
                        "fix_gp": site_fix_gp,
                        "fix_ap": site_fix_ap,
                        "preisindizes_gp": preisindizes_gp,  # Use global for now
                        "preisindizes_ap": preisindizes_ap,
                    }

            # Berechnung starten
            st.markdown("---")
            if st.button("🔄 Alle Standorte berechnen", type="primary"):
                results = calculate_kostenvergleich(df, params, st.session_state.get("site_params", {}))
                st.session_state["results"] = results
                st.rerun()
        else:
            st.warning("Spalte 'Heizzentrale' nicht erkannt.")
            st.dataframe(df.head(), use_container_width=True)

with tab2:
    st.header("📊 Ergebnisse Kostenvergleich §8 WärmeLV")

    if "results" in st.session_state and not st.session_state["results"].empty:
        results = st.session_state["results"]

        # KPIs
        n_bestanden = len(results[results["Ergebnis"].str.contains("erfüllt") & ~results["Ergebnis"].str.contains("nicht")])
        n_nicht = len(results) - n_bestanden
        m1, m2, m3 = st.columns(3)
        m1.metric("Standorte", len(results))
        m2.metric("§8 erfüllt ✅", n_bestanden)
        m3.metric("§8 nicht erfüllt ❌", n_nicht)

        # Übersichtstabelle
        summary = results[["Heizzentrale", "Abrechnungsperioden", "Betriebskosten_bisherig_brutto",
                         "Kosten_Waermelieferung_brutto", "Differenz_Euro", "Ergebnis"]].copy()
        summary.columns = ["Standort", "Abrechnungsperioden", "§9 Bisherige Kosten (€/a)",
                         "§10 Wärmelieferung (€/a)", "Differenz (€/a)", "Ergebnis §8"]

        def highlight_result(val):
            if "erfüllt" in str(val) and "nicht" not in str(val):
                return "background-color: #90EE90"
            elif "nicht erfüllt" in str(val):
                return "background-color: #FFB6C1"
            return ""

        st.dataframe(summary.style.map(highlight_result, subset=["Ergebnis §8"]), use_container_width=True)

        # Detailansicht je Standort
        st.subheader("Detailansicht")
        standort_filter = st.selectbox("Standort", ["Alle"] + list(results["Heizzentrale"].unique()))
        results_show = results if standort_filter == "Alle" else results[results["Heizzentrale"] == standort_filter]

        for idx, row in results_show.iterrows():
            with st.expander(f"{'✅' if 'nicht' not in row['Ergebnis'] else '❌'} {row['Heizzentrale']}", expanded=(standort_filter != "Alle")):
                # Abrechnungsperioden klar darstellen
                if row.get("Abrechnungsperioden"):
                    st.markdown("**📅 Abrechnungsperioden:**")
                    for p in str(row["Abrechnungsperioden"]).split(" | "):
                        st.write(f"  • {p}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown("**§9 Bisherige Versorgung**")
                    st.metric("Betriebskosten", f"{row['Betriebskosten_bisherig_brutto']:.2f} €/a")
                    st.write(f"Ø Verbrauch: {row['Durchschnitt_Verbrauch_kWh']:,.0f} kWh/a")
                    st.write(f"Zeiträume: {row['Anzahl_Zeitraeume']}")
                    st.write(f"Brennstoffpreis: {row['Preis_ct_kWh_Brennstoff']:.2f} ct/kWh")
                    st.write(f"Verbrauchskosten: {row['Verbrauchskosten_S9']:.2f} €/a")
                    st.write(f"Sonstige Kosten: {row['Sonstige_Betriebskosten_S9']:.2f} €/a")
                    if row.get("Betriebsstunden", 0) > 0:
                        st.write(f"Betriebsstunden: {row['Betriebsstunden']} h/a")

                with c2:
                    st.markdown("**§10 Wärmelieferung**")
                    st.metric("Kosten WL", f"{row['Kosten_Waermelieferung_brutto']:.2f} €/a")
                    st.write(f"Nutzungsgrad: {row['Nutzungsgrad']*100:.1f}%")
                    st.write(f"Wärmemenge Heiz.: {row['Waermemenge_Heizung_kWh']:,.0f} kWh/a")
                    st.write(f"Wärmemenge ges.: {row['Waermemenge_gesamt_kWh']:,.0f} kWh/a")
                    st.write(f"Warmwasser: {row['Warmwasser']}")
                    st.write(f"Grundkosten: {row['Grundkosten_brutto']:.2f} €/a")
                    st.write(f"Arbeitskosten: {row['Arbeitskosten_brutto']:.2f} €/a")

                with c3:
                    st.markdown("**§8 Ergebnis**")
                    diff = row['Differenz_Euro']
                    if diff >= 0:
                        st.metric("Ersparnis", f"{diff:.2f} €/a", delta=f"+{diff:.2f}")
                    else:
                        st.metric("Mehrkosten", f"{abs(diff):.2f} €/a", delta=f"{diff:.2f}")

                # Formel-Anzeige
                st.markdown("---")
                st.markdown("**📐 Angewandte Preisformeln:**")
                st.code(row.get("Formel_GP", ""), language=None)
                st.code(row.get("Formel_AP", ""), language=None)

        # Export
        st.subheader("Export")
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            csv = results.to_csv(index=False, sep=";", decimal=",")
            st.download_button("📥 CSV", csv, "kostenvergleich.csv", "text/csv")
        with col_e2:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
                results.to_excel(w, index=False, sheet_name="Ergebnisse")
            st.download_button("📥 Excel", buf.getvalue(), "kostenvergleich.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Noch keine Ergebnisse. Bitte Daten importieren und berechnen.")

with tab3:
    st.header("ℹ️ Formeln & Methodik")
    st.markdown("""
    ### §8 WärmeLV – Kostenvergleich
    
    Die Kosten der Wärmelieferung (§10) dürfen die bisherigen Betriebskosten (§9) **nicht übersteigen**.
    
    ---
    
    ### §9 – Betriebskosten der bisherigen Versorgung
    
    **Verbrauchskosten** = Ø Energieverbrauch (letzte 3 Zeiträume) × Durchschnittspreis letzter Zeitraum
    
    **Sonstige Betriebskosten** = Wartung + Schornsteinfeger + Betriebsstrom
    
    **Gesamt** = Verbrauchskosten + Sonstige Betriebskosten
    
    ---
    
    ### §10 – Kosten der Wärmelieferung
    
    **Wärmemenge** = Ø Energieverbrauch × Jahresnutzungsgrad Altanlage
    
    Bei zentraler Warmwasseraufbereitung:  
    **Wärmemenge gesamt** = Wärmemenge Heizung + (Heizfläche × WW-Pauschale kWh/m²/a)
    
    ---
    
    ### Preisgleitklausel
    """)

    st.latex(r"GP = GPB \times \left( FixGP + G_1 \cdot \frac{GP_1}{GP_{1B}} + G_2 \cdot \frac{GP_2}{GP_{2B}} + \ldots \right)")
    st.latex(r"AP = APB \times \left( FixAP + A_1 \cdot \frac{AP_1}{AP_{1B}} + A_2 \cdot \frac{AP_2}{AP_{2B}} + \ldots \right)")

    st.markdown("""
    | Variable | Bedeutung |
    |----------|-----------|
    | **GPB** | Grundpreis Basis (€/Monat netto) |
    | **APB** | Arbeitspreis Basis (ct/kWh netto) |
    | **FixGP/FixAP** | Fixer Anteil (nicht preisgleitend) |
    | **G₁, G₂, …** | Anteile der Preisindizes am Grundpreis |
    | **A₁, A₂, …** | Anteile der Preisindizes am Arbeitspreis |
    | **GP₁, GP₂, …** | Aktuelle Indexwerte |
    | **GP₁B, GP₂B, …** | Basis-Indexwerte (zum Vertragsbeginn) |
    
    **Prüfregel:** FixGP + G₁ + G₂ + … = 1,0 (bzw. FixAP + A₁ + A₂ + … = 1,0)
    
    ---
    
    ### Betriebsstunden (kW → kWh Umrechnung)
    
    Falls der Energieverbrauch in **kW** (Leistung) statt **kWh** (Arbeit) angegeben ist:
    
    **Energieverbrauch (kWh)** = Brennstoffleistung (kW) × Betriebsstunden (h/a)
    
    Typische Werte:
    - Wohngebäude: 1.500–2.000 h/a
    - Gewerbe: 2.000–3.000 h/a
    - Industrie: 4.000–6.000 h/a
    
    ---
    
    ### Jahresnutzungsgrade (BMVBS-Pauschalwerte)
    
    | Technologie | Nutzungsgrad |
    |-------------|-------------|
    | Brennwert | 96,0% |
    | Niedertemperatur | 84,9% |
    | Standardkessel | 80,0% |
    | Konstanttemperatur | 78,0% |
    """)
