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


def _apply_sidebar_params(params=None):
    """Sidebar-Parameter aus einem Projekt-Dict in den Session State laden.
    Wird ohne Argument aufgerufen, um die Defaults zu setzen."""
    p = params or {}
    st.session_state["sb_ust"] = float(p.get("ust_satz", 0.19) * 100)
    st.session_state["sb_bst"] = max(0, int(p.get("betriebsstunden", 0) or 0))
    st.session_state["sb_ng_bw"] = max(0.0, float(p.get("ng_brennwert", 96.0)))
    st.session_state["sb_ng_nt"] = max(0.0, float(p.get("ng_niedertemperatur", 84.9)))
    st.session_state["sb_ng_sk"] = max(0.0, float(p.get("ng_standardkessel", 80.0)))
    st.session_state["sb_ng_kt"] = max(0.0, float(p.get("ng_konstanttemperatur", 78.0)))
    st.session_state["sb_ww"] = max(0.0, float(p.get("ww_kwh_pro_m2", 20.0)))
    st.session_state["sb_gp"] = max(0.0, float(p.get("grundpreis_netto", 0.0) or 0.0))
    st.session_state["sb_ap"] = max(0.0, float(p.get("arbeitspreis_netto", 0.0) or 0.0))
    st.session_state["sb_fix_gp"] = max(0.0, float(p.get("fix_gp", 0.0)))
    st.session_state["sb_fix_ap"] = max(0.0, float(p.get("fix_ap", 0.0)))
    pidx_list = p.get("preisindizes_gp", [])
    apidx_list = p.get("preisindizes_ap", [])
    st.session_state["sb_pidx_count"] = max(0, int(p.get("preisindex_count", len(pidx_list)) or 0))
    for i in range(5):
        gp_idx = pidx_list[i] if i < len(pidx_list) else {}
        ap_idx = apidx_list[i] if i < len(apidx_list) else {}
        st.session_state[f"sb_gi_{i}"] = float(gp_idx.get("anteil", 0.0))
        st.session_state[f"sb_gpib_{i}"] = max(0.0, float(gp_idx.get("basis", 100.0)))
        st.session_state[f"sb_gpi_{i}"] = max(0.0, float(gp_idx.get("aktuell", 100.0)))
        st.session_state[f"sb_ai_{i}"] = float(ap_idx.get("anteil", 0.0))
        st.session_state[f"sb_apib_{i}"] = max(0.0, float(ap_idx.get("basis", 100.0)))
        st.session_state[f"sb_api_{i}"] = max(0.0, float(ap_idx.get("aktuell", 100.0)))


# Sidebar-Defaults beim allerersten Start initialisieren
if "sb_initialized" not in st.session_state:
    _apply_sidebar_params()
    st.session_state["sb_initialized"] = True


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
            _apply_sidebar_params()  # Sidebar auf Defaults zurücksetzen
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
        _apply_sidebar_params(loaded.get("params", {}))  # Sidebar-Parameter aus Projekt laden
        st.rerun()

if st.session_state.get("current_project"):
    st.info(f"📂 **Projekt:** {st.session_state['current_project']}")

st.markdown("---")

# --- Sidebar: Default-Parameter ---
st.sidebar.header("⚙️ Default-Parameter")
st.sidebar.markdown("*Gelten für alle Standorte, sofern nicht individuell überschrieben*")

st.sidebar.subheader("Allgemein")
ust_satz = st.sidebar.number_input("USt-Satz (%)", min_value=0.0, step=0.1, key="sb_ust") / 100
default_betriebsstunden = st.sidebar.number_input("Betriebsstunden (h/a)", min_value=0, step=100, key="sb_bst",
    help="Nur nötig wenn Verbrauch in kW statt kWh angegeben ist. kWh = kW × Betriebsstunden")

st.sidebar.subheader("Jahresnutzungsgrade Altanlage (%)")
nutzungsgrade = {
    "Brennwert": st.sidebar.number_input("Brennwert", min_value=0.0, step=0.5, key="sb_ng_bw") / 100,
    "Niedertemperatur": st.sidebar.number_input("Niedertemperatur", min_value=0.0, step=0.5, key="sb_ng_nt") / 100,
    "Standardkessel": st.sidebar.number_input("Standardkessel", min_value=0.0, step=0.5, key="sb_ng_sk") / 100,
    "Konstanttemperatur": st.sidebar.number_input("Konstanttemperatur", min_value=0.0, step=0.5, key="sb_ng_kt") / 100,
}

st.sidebar.subheader("Warmwasser")
ww_kwh_pro_m2 = st.sidebar.number_input("WW-Pauschale (kWh/m²/a)", min_value=0.0, step=1.0, key="sb_ww")

st.sidebar.subheader("Wärmelieferung – Angebotspreise (§10)")
default_grundpreis = st.sidebar.number_input("GPB – Grundpreis Basis (€/Monat netto)", min_value=0.0, step=10.0, key="sb_gp")
default_arbeitspreis = st.sidebar.number_input("APB – Arbeitspreis Basis (ct/kWh netto)", min_value=0.0, step=0.1, key="sb_ap")

st.sidebar.subheader("Preisgleitklausel")
st.sidebar.latex(r"GP = GPB \times (FixGP + G_1 \cdot \frac{GP_1}{GP_{1B}} + \ldots)")
st.sidebar.latex(r"AP = APB \times (FixAP + A_1 \cdot \frac{AP_1}{AP_{1B}} + \ldots)")

fix_gp = st.sidebar.number_input("FixGP", min_value=0.0, step=0.01, format="%.4f", key="sb_fix_gp")
fix_ap = st.sidebar.number_input("FixAP", min_value=0.0, step=0.01, format="%.4f", key="sb_fix_ap")

preisindex_count = st.sidebar.number_input("Anzahl Preisindizes", min_value=0, max_value=5, step=1, key="sb_pidx_count")
preisindizes_gp = []
preisindizes_ap = []
for i in range(int(preisindex_count)):
    st.sidebar.markdown(f"**Index {i+1}**")
    gi = st.sidebar.number_input(f"G{i+1}", step=0.0001, format="%.4f", key=f"sb_gi_{i}")
    gpi_basis = st.sidebar.number_input(f"GP{i+1}B (Basis)", min_value=0.0, step=1.0, key=f"sb_gpib_{i}")
    gpi_aktuell = st.sidebar.number_input(f"GP{i+1} (Aktuell)", min_value=0.0, step=1.0, key=f"sb_gpi_{i}")
    preisindizes_gp.append({"anteil": gi, "basis": gpi_basis, "aktuell": gpi_aktuell})
    ai = st.sidebar.number_input(f"A{i+1}", step=0.0001, format="%.4f", key=f"sb_ai_{i}")
    api_basis = st.sidebar.number_input(f"AP{i+1}B (Basis)", min_value=0.0, step=1.0, key=f"sb_apib_{i}")
    api_aktuell = st.sidebar.number_input(f"AP{i+1} (Aktuell)", min_value=0.0, step=1.0, key=f"sb_api_{i}")
    preisindizes_ap.append({"anteil": ai, "basis": api_basis, "aktuell": api_aktuell})

# Speichern
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
                "betriebsstunden": default_betriebsstunden,
                "fix_gp": fix_gp,
                "fix_ap": fix_ap,
                "ww_kwh_pro_m2": ww_kwh_pro_m2,
                "ng_brennwert": st.session_state.get("sb_ng_bw", 96.0),
                "ng_niedertemperatur": st.session_state.get("sb_ng_nt", 84.9),
                "ng_standardkessel": st.session_state.get("sb_ng_sk", 80.0),
                "ng_konstanttemperatur": st.session_state.get("sb_ng_kt", 78.0),
                "preisindex_count": int(st.session_state.get("sb_pidx_count", 0) or 0),
                "preisindizes_gp": preisindizes_gp,
                "preisindizes_ap": preisindizes_ap,
            },
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
            # Clear old results when new data is imported
            st.session_state.pop("results", None)

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
                        period_rows = site_data[site_data["Abrechnungsperiode"].notna()]
                        if not period_rows.empty:
                            st.markdown("**📅 Abrechnungsperioden:**")
                            for _, prow in period_rows.iterrows():
                                p = prow["Abrechnungsperiode"]
                                if "Brennstoff_kWh" in site_data.columns:
                                    verbrauch = prow.get("Brennstoff_kWh") or 0
                                    unit = "kWh"
                                elif "Brennstoff_kW" in site_data.columns:
                                    verbrauch = prow.get("Brennstoff_kW") or 0
                                    unit = "kW"
                                else:
                                    verbrauch, unit = 0, "kWh"
                                st.write(f"  • {p} — {verbrauch:,.0f} {unit}")

                    sc1, sc2, sc3 = st.columns(3)
                    with sc1:
                        st.markdown("**Anlagenparameter**")
                        site_betriebsstunden = st.number_input(
                            "Betriebsstunden (h/a)", value=int(sp.get("betriebsstunden", default_betriebsstunden) or 0),
                            step=100, key=f"bst_{site}",
                            help="Für Umrechnung kW → kWh")
                        # Live kWh-Vorschau wenn Verbrauch in kW vorliegt
                        if "Brennstoff_kW" in site_data.columns:
                            kw_vals = site_data["Brennstoff_kW"].dropna()
                            kw_vals = kw_vals[kw_vals > 0]
                            if len(kw_vals) > 0:
                                if site_betriebsstunden > 0:
                                    kwh_preview = kw_vals * site_betriebsstunden
                                    st.success(
                                        f"⚡ Ø **{kwh_preview.mean():,.0f} kWh/a**  \n"
                                        f"({kw_vals.mean():,.1f} kW × {site_betriebsstunden} h/a, {len(kw_vals)} Zeitraum/e)"
                                    )
                                else:
                                    st.warning("⚠️ Verbrauch in **kW** erkannt – Betriebsstunden eintragen!")
                        site_nutzungsgrad_val = sp.get("nutzungsgrad", 0) or 0
                        site_nutzungsgrad = st.number_input(
                            "Nutzungsgrad (%)", value=float(site_nutzungsgrad_val * 100),
                            step=0.5, key=f"ng_{site}",
                            help="0 = automatisch aus Technologie") / 100
                        site_ww = st.number_input(
                            "WW-Pauschale (kWh/m²/a)", value=float(sp.get("ww_kwh_pro_m2", ww_kwh_pro_m2)),
                            step=1.0, key=f"ww_{site}")

                    with sc2:
                        st.markdown("**Angebotspreise WL**")
                        site_gp = st.number_input(
                            "GPB (€/Monat netto)", value=float(sp.get("grundpreis_netto", 0) or 0),
                            step=10.0, key=f"gp_{site}",
                            help="0 = Default aus Sidebar")
                        site_ap = st.number_input(
                            "APB (ct/kWh netto)", value=float(sp.get("arbeitspreis_netto", 0) or 0),
                            step=0.1, key=f"ap_{site}",
                            help="0 = Default aus Sidebar")

                    with sc3:
                        st.markdown("**Preisgleitklausel**")
                        site_fix_gp = st.number_input(
                            "FixGP", value=float(sp.get("fix_gp", fix_gp)),
                            step=0.01, format="%.4f", key=f"sfgp_{site}")
                        site_fix_ap = st.number_input(
                            "FixAP", value=float(sp.get("fix_ap", fix_ap)),
                            step=0.01, format="%.4f", key=f"sfap_{site}")
                        site_own_pidx = st.checkbox(
                            "🔧 Eigene Preisindizes",
                            value=bool(sp.get("own_preisindizes", False)),
                            key=f"own_pidx_{site}",
                            help="Eigene Preisindizes für diesen Standort verwenden (überschreibt Sidebar-Defaults)")

                    # Per-Standort Preisindizes (volle Breite, nur wenn aktiviert)
                    if site_own_pidx:
                        st.markdown("**📊 Eigene Preisindizes für diesen Standort:**")
                        sp_pidx_count = int(sp.get("preisindex_count", 0) if sp.get("own_preisindizes") else 0)
                        site_pidx_count = st.number_input(
                            "Anzahl Preisindizes", value=sp_pidx_count,
                            min_value=0, max_value=5, step=1, key=f"sp_pidx_count_{site}")
                        sp_gp_saved = sp.get("preisindizes_gp", []) if sp.get("own_preisindizes") else []
                        sp_ap_saved = sp.get("preisindizes_ap", []) if sp.get("own_preisindizes") else []
                        site_preisindizes_gp_own = []
                        site_preisindizes_ap_own = []
                        for j in range(int(site_pidx_count)):
                            gp_j = sp_gp_saved[j] if j < len(sp_gp_saved) else {}
                            ap_j = sp_ap_saved[j] if j < len(sp_ap_saved) else {}
                            st.markdown(f"*Index {j+1}*")
                            c_a, c_b, c_c, c_d, c_e, c_f = st.columns(6)
                            gi_j = c_a.number_input(f"G{j+1}", value=float(gp_j.get("anteil", 0.0)), step=0.0001, format="%.4f", key=f"sp_gi_{site}_{j}")
                            gpib_j = c_b.number_input(f"GP{j+1}B", value=float(gp_j.get("basis", 100.0)), min_value=0.0, step=1.0, key=f"sp_gpib_{site}_{j}")
                            gpi_j = c_c.number_input(f"GP{j+1}", value=float(gp_j.get("aktuell", 100.0)), min_value=0.0, step=1.0, key=f"sp_gpi_{site}_{j}")
                            ai_j = c_d.number_input(f"A{j+1}", value=float(ap_j.get("anteil", 0.0)), step=0.0001, format="%.4f", key=f"sp_ai_{site}_{j}")
                            apib_j = c_e.number_input(f"AP{j+1}B", value=float(ap_j.get("basis", 100.0)), min_value=0.0, step=1.0, key=f"sp_apib_{site}_{j}")
                            api_j = c_f.number_input(f"AP{j+1}", value=float(ap_j.get("aktuell", 100.0)), min_value=0.0, step=1.0, key=f"sp_api_{site}_{j}")
                            site_preisindizes_gp_own.append({"anteil": gi_j, "basis": gpib_j, "aktuell": gpi_j})
                            site_preisindizes_ap_own.append({"anteil": ai_j, "basis": apib_j, "aktuell": api_j})
                        final_site_pidx_gp = site_preisindizes_gp_own
                        final_site_pidx_ap = site_preisindizes_ap_own
                    else:
                        site_pidx_count = 0
                        final_site_pidx_gp = preisindizes_gp
                        final_site_pidx_ap = preisindizes_ap

                    # Save site params
                    st.session_state["site_params"][site] = {
                        "betriebsstunden": site_betriebsstunden,
                        "nutzungsgrad": site_nutzungsgrad if site_nutzungsgrad > 0 else None,
                        "ww_kwh_pro_m2": site_ww,
                        "grundpreis_netto": site_gp if site_gp > 0 else None,
                        "arbeitspreis_netto": site_ap if site_ap > 0 else None,
                        "fix_gp": site_fix_gp,
                        "fix_ap": site_fix_ap,
                        "own_preisindizes": site_own_pidx,
                        "preisindex_count": int(site_pidx_count),
                        "preisindizes_gp": final_site_pidx_gp,
                        "preisindizes_ap": final_site_pidx_ap,
                    }

            # Berechnung starten
            st.markdown("---")
            if st.button("🔄 Alle Standorte berechnen", type="primary"):
                try:
                    results = calculate_kostenvergleich(df, params, st.session_state.get("site_params", {}))
                    if results.empty:
                        st.error("⚠️ Berechnung lieferte keine Ergebnisse. Prüfe ob 'Heizzentrale'-Spalte vorhanden ist und Daten korrekt importiert wurden.")
                    else:
                        st.session_state["results"] = results
                        st.rerun()
                except Exception as e:
                    import traceback
                    st.error(f"❌ Fehler bei der Berechnung: {e}")
                    st.code(traceback.format_exc())
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

        # Übersichtstabelle - nur vorhandene Spalten verwenden
        summary_cols = ["Heizzentrale", "Betriebskosten_bisherig_brutto",
                       "Kosten_Waermelieferung_brutto", "Differenz_Euro", "Ergebnis"]
        summary_names = ["Standort", "§9 Bisherige Kosten (€/a)",
                        "§10 Wärmelieferung (€/a)", "Differenz (€/a)", "Ergebnis §8"]

        # Abrechnungsperioden einfügen wenn vorhanden
        if "Abrechnungsperioden" in results.columns:
            summary_cols.insert(1, "Abrechnungsperioden")
            summary_names.insert(1, "Perioden")

        summary = results[summary_cols].copy()
        summary.columns = summary_names

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
                perioden_str = row.get("Abrechnungsperioden", "")
                if perioden_str:
                    st.markdown("**📅 Abrechnungsperioden:**")
                    for p in str(perioden_str).split(" | "):
                        if p.strip():
                            st.write(f"  • {p.strip()}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown("**§9 Bisherige Versorgung**")
                    st.metric("Betriebskosten", f"{row['Betriebskosten_bisherig_brutto']:.2f} €/a")
                    st.write(f"Ø Verbrauch: {row['Durchschnitt_Verbrauch_kWh']:,.0f} kWh/a")
                    st.write(f"Zeiträume: {row['Anzahl_Zeitraeume']}")
                    st.write(f"Brennstoffpreis: {row['Preis_ct_kWh_Brennstoff']:.2f} ct/kWh")
                    st.write(f"Verbrauchskosten: {row['Verbrauchskosten_S9']:.2f} €/a")
                    st.write(f"Sonstige Kosten: {row['Sonstige_Betriebskosten_S9']:.2f} €/a")
                    if row.get("Betriebsstunden", 0) and row["Betriebsstunden"] > 0:
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
                formel_gp = row.get("Formel_GP", "")
                formel_ap = row.get("Formel_AP", "")
                if formel_gp:
                    st.code(formel_gp, language=None)
                else:
                    st.code("GP = (keine Preisgleitklausel konfiguriert)", language=None)
                if formel_ap:
                    st.code(formel_ap, language=None)
                else:
                    st.code("AP = (keine Preisgleitklausel konfiguriert)", language=None)

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
