diff --git a/app.py b/app.py
new file mode 100644
index 0000000000000000000000000000000000000000..3aa220855aca1a14b04bf955b8b78087f6bf4f1d
--- /dev/null
+++ b/app.py
@@ -0,0 +1,476 @@
+"""Streamlit application for analysing CrossFit sales data."""
+from __future__ import annotations
+
+import sys
+import tempfile
+from pathlib import Path
+from typing import Iterable, List
+
+import pandas as pd
+import streamlit as st
+
+from helios import get_build_label
+from helios.ai_assistant import ChatGPTInsights, DEFAULT_MODEL
+from helios.data_loader import LoadedData, load_file
+from helios.data_processing import (
+    ColumnDetectionError,
+    PreparedData,
+    month_over_month,
+    monthly_summary,
+    prepare_sales_dataframe,
+)
+from helios.visualization import (
+    category_distribution,
+    month_over_month_chart,
+    monthly_sales_bar,
+)
+
+
+def _load_uploaded_file(uploaded) -> LoadedData:
+    suffix = Path(uploaded.name).suffix
+    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
+        tmp.write(uploaded.getbuffer())
+        tmp_path = Path(tmp.name)
+    try:
+        loaded = load_file(tmp_path)
+    finally:
+        tmp_path.unlink(missing_ok=True)
+    return LoadedData(source=Path(uploaded.name), dataframe=loaded.dataframe)
+
+
+def _prepare_dataframes(loaded: Iterable[LoadedData]) -> List[PreparedData]:
+    prepared: List[PreparedData] = []
+    for dataset in loaded:
+        try:
+            prepared.append(prepare_sales_dataframe(dataset.dataframe))
+        except ColumnDetectionError as err:
+            st.error(f"{dataset.source}: {err}")
+        except Exception as exc:  # pragma: no cover - user data variability
+            st.error(f"Erreur lors du traitement de {dataset.source}: {exc}")
+    return prepared
+
+
+def main() -> None:
+    st.set_page_config(page_title="Helios - Pilotage des ventes", layout="wide")
+
+    build_label = get_build_label()
+
+    st.markdown(
+        """
+        <style>
+        :root {
+            color-scheme: dark;
+        }
+        .helios-app {
+            background: radial-gradient(120% 120% at 15% 15%, rgba(56, 189, 248, 0.25), transparent 55%),
+                        radial-gradient(140% 140% at 85% -10%, rgba(99, 102, 241, 0.35), transparent 60%),
+                        #020617;
+            min-height: 100vh;
+            padding-bottom: 3rem;
+        }
+        .block-container {
+            padding-top: 2.5rem;
+            padding-bottom: 2.5rem;
+        }
+        .helios-hero {
+            position: relative;
+            padding: 2.75rem 3rem;
+            border-radius: 1.75rem;
+            background: rgba(15, 23, 42, 0.75);
+            backdrop-filter: blur(28px);
+            border: 1px solid rgba(148, 163, 184, 0.18);
+            color: #e2e8f0;
+            margin-bottom: 2rem;
+            overflow: hidden;
+            box-shadow: 0 30px 80px rgba(14, 116, 144, 0.25);
+        }
+        .helios-hero::before {
+            content: "";
+            position: absolute;
+            inset: -15% -10% auto auto;
+            height: 320px;
+            width: 320px;
+            background: radial-gradient(circle, rgba(56, 189, 248, 0.4), transparent 65%);
+            opacity: 0.85;
+        }
+        .helios-hero::after {
+            content: "";
+            position: absolute;
+            inset: auto auto -25% -10%;
+            height: 240px;
+            width: 420px;
+            background: radial-gradient(circle, rgba(129, 140, 248, 0.4), transparent 70%);
+            transform: rotate(-18deg);
+            opacity: 0.7;
+        }
+        .helios-hero__grid {
+            position: relative;
+            z-index: 1;
+            display: grid;
+            gap: 2.5rem;
+            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
+        }
+        .helios-hero__badge {
+            display: inline-flex;
+            align-items: center;
+            gap: 0.5rem;
+            padding: 0.55rem 1.1rem;
+            border-radius: 999px;
+            background: linear-gradient(120deg, rgba(34, 211, 238, 0.35), rgba(14, 165, 233, 0.65));
+            color: #f8fafc;
+            font-weight: 600;
+            letter-spacing: 0.04em;
+            text-transform: uppercase;
+            font-size: 0.75rem;
+        }
+        .helios-hero__title {
+            font-size: clamp(2.4rem, 4vw, 3.2rem);
+            font-weight: 700;
+            margin: 1rem 0 0.75rem;
+            letter-spacing: -0.01em;
+        }
+        .helios-hero__subtitle {
+            margin: 0;
+            color: rgba(226, 232, 240, 0.85);
+            font-size: 1.1rem;
+            line-height: 1.6;
+        }
+        .helios-hero__stats {
+            display: grid;
+            gap: 1.1rem;
+            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
+            margin-top: 1.75rem;
+        }
+        .helios-hero__stat {
+            padding: 1rem 1.25rem;
+            border-radius: 1rem;
+            background: rgba(15, 23, 42, 0.75);
+            border: 1px solid rgba(148, 163, 184, 0.12);
+            box-shadow: inset 0 1px 0 rgba(226, 232, 240, 0.08);
+        }
+        .helios-hero__stat span {
+            display: block;
+            font-size: 0.8rem;
+            text-transform: uppercase;
+            letter-spacing: 0.08em;
+            color: rgba(148, 163, 184, 0.8);
+        }
+        .helios-hero__stat strong {
+            display: block;
+            margin-top: 0.4rem;
+            font-size: 1.4rem;
+            color: #f8fafc;
+        }
+        .helios-feature-grid {
+            display: grid;
+            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
+            gap: 1.5rem;
+            margin-bottom: 2.5rem;
+        }
+        .helios-feature-card {
+            position: relative;
+            padding: 1.5rem;
+            border-radius: 1.25rem;
+            background: rgba(15, 23, 42, 0.72);
+            border: 1px solid rgba(148, 163, 184, 0.12);
+            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.45);
+            color: rgba(226, 232, 240, 0.92);
+        }
+        .helios-feature-icon {
+            font-size: 1.45rem;
+            margin-bottom: 0.75rem;
+        }
+        .helios-feature-card h3 {
+            margin: 0 0 0.5rem;
+            font-size: 1.05rem;
+            color: #f8fafc;
+        }
+        .helios-feature-card p {
+            margin: 0;
+            font-size: 0.9rem;
+            line-height: 1.55;
+            color: rgba(226, 232, 240, 0.75);
+        }
+        .helios-step-card {
+            padding: 1.4rem 1.6rem;
+            border-radius: 1.2rem;
+            background: rgba(15, 23, 42, 0.65);
+            border: 1px solid rgba(148, 163, 184, 0.14);
+            box-shadow: inset 0 1px 0 rgba(226, 232, 240, 0.05);
+            color: rgba(226, 232, 240, 0.9);
+            height: 100%;
+        }
+        .helios-step-card h3 {
+            margin: 0 0 0.45rem;
+            font-size: 1.02rem;
+            color: #f8fafc;
+        }
+        .helios-step-card p {
+            margin: 0;
+            font-size: 0.88rem;
+            line-height: 1.55;
+            color: rgba(226, 232, 240, 0.7);
+        }
+        .helios-panel {
+            padding: 1.75rem;
+            border-radius: 1.5rem;
+            background: rgba(15, 23, 42, 0.7);
+            border: 1px solid rgba(148, 163, 184, 0.14);
+            box-shadow: inset 0 1px 0 rgba(226, 232, 240, 0.06);
+            margin-bottom: 1.5rem;
+        }
+        .helios-panel h1 {
+            margin: 0 0 0.5rem;
+            font-size: 1.6rem;
+            color: #f8fafc;
+        }
+        .helios-panel p {
+            margin: 0;
+            color: rgba(226, 232, 240, 0.8);
+        }
+        .helios-sidebar {
+            background: rgba(15, 23, 42, 0.85) !important;
+        }
+        .helios-sidebar .stCheckbox, .helios-sidebar .stTextInput, .helios-sidebar .stSelectbox {
+            color: #e2e8f0;
+        }
+        </style>
+        <script>
+        const root = window.parent.document.querySelector('.main');
+        if (root) {
+            root.classList.add('helios-app');
+        }
+        const sidebar = window.parent.document.querySelector('section[data-testid="stSidebar"] > div');
+        if (sidebar) {
+            sidebar.classList.add('helios-sidebar');
+        }
+        </script>
+        """,
+        unsafe_allow_html=True,
+    )
+
+    st.markdown(
+        f"""
+        <div class="helios-hero">
+            <div class="helios-hero__grid">
+                <div>
+                    <div class="helios-hero__badge">Nouvelle expérience 2024</div>
+                    <h1 class="helios-hero__title">Helios Control Center</h1>
+                    <p class="helios-hero__subtitle">
+                        Un cockpit moderne pour suivre vos abonnements, ventes boutique et performances mensuelles.
+                        Déposez vos relevés PDF, CSV ou Excel pour obtenir des analyses instantanées.
+                    </p>
+                    <div class="helios-hero__stats">
+                        <div class="helios-hero__stat">
+                            <span>Analyse multi-sources</span>
+                            <strong>PDF · CSV · Excel</strong>
+                        </div>
+                        <div class="helios-hero__stat">
+                            <span>Comparaison</span>
+                            <strong>Mois par mois</strong>
+                        </div>
+                        <div class="helios-hero__stat">
+                            <span>Version installée</span>
+                            <strong>Helios {build_label}</strong>
+                        </div>
+                    </div>
+                </div>
+                <div>
+                    <div class="helios-feature-card" style="height:100%;">
+                        <div class="helios-feature-icon">🤖</div>
+                        <h3>Assistant IA embarqué</h3>
+                        <p>
+                            Activez l'analyse ChatGPT pour générer des insights sur vos progressions, alertes de churn et
+                            opportunités de ventes additionnelles.
+                        </p>
+                    </div>
+                </div>
+            </div>
+        </div>
+        """,
+        unsafe_allow_html=True,
+    )
+
+    st.markdown(
+        """
+        <div class="helios-feature-grid">
+            <div class="helios-feature-card">
+                <div class="helios-feature-icon">📈</div>
+                <h3>Tableaux de bord dynamiques</h3>
+                <p>Visualisez immédiatement les tendances de CA et vos catégories clés avec des graphiques interactifs.</p>
+            </div>
+            <div class="helios-feature-card">
+                <div class="helios-feature-icon">⚡️</div>
+                <h3>Workflow drag &amp; drop</h3>
+                <p>Déposez vos documents sur la page d'accueil et laissez Helios détecter les colonnes pertinentes.</p>
+            </div>
+            <div class="helios-feature-card">
+                <div class="helios-feature-icon">🧭</div>
+                <h3>Navigation par onglets</h3>
+                <p>Alternez entre synthèse, graphiques et données tabulaires sans perdre vos filtres.</p>
+            </div>
+        </div>
+        """,
+        unsafe_allow_html=True,
+    )
+
+    step_cols = st.columns(3)
+    step_descriptions = [
+        ("1. Déposer", "Glissez vos PDF, CSV ou fichiers Excel sur cette page"),
+        ("2. Filtrer", "Choisissez les mois et catégories à comparer"),
+        ("3. Analyser", "Explorez les graphiques et déclenchez l'analyse IA"),
+    ]
+    for col, (title, description) in zip(step_cols, step_descriptions):
+        col.markdown(
+            f"""
+            <div class="helios-step-card">
+                <h3>{title}</h3>
+                <p>{description}</p>
+            </div>
+            """,
+            unsafe_allow_html=True,
+        )
+
+    st.caption(
+        "Astuce : videz le cache Streamlit (`streamlit cache clear`) si l'interface n'affiche pas la nouvelle expérience."
+    )
+
+    with st.sidebar:
+        st.header("Paramètres")
+        api_key = st.text_input("Clé API OpenAI", type="password")
+        model = st.text_input("Modèle OpenAI", value=DEFAULT_MODEL)
+        generate_ai = st.checkbox("Générer une analyse IA", value=False)
+        st.caption(f"Version installée : Helios {build_label}")
+
+    uploaded_files = st.file_uploader(
+        "Déposez vos fichiers de ventes (PDF, Excel ou CSV)",
+        accept_multiple_files=True,
+        type=None,
+        help="Les documents PDF, CSV, XLSX et XLS sont acceptés. Les autres formats seront ignorés.",
+    )
+
+    if not uploaded_files:
+        st.info("Chargez un ou plusieurs fichiers pour commencer l'analyse.")
+        st.stop()
+
+    loaded_datasets: List[LoadedData] = []
+    for uploaded in uploaded_files:
+        extension = Path(uploaded.name).suffix.lower()
+        if extension not in {".xlsx", ".xls", ".csv", ".pdf"}:
+            st.warning(
+                f"{uploaded.name}: format non pris en charge. "
+                "Formats acceptés : PDF, CSV, XLSX ou XLS."
+            )
+            continue
+        try:
+            loaded_datasets.append(_load_uploaded_file(uploaded))
+            st.success(f"{uploaded.name} importé avec succès.")
+        except Exception as exc:
+            st.error(f"Impossible de lire {uploaded.name}: {exc}")
+
+    if not loaded_datasets:
+        st.stop()
+
+    prepared_datasets = _prepare_dataframes(loaded_datasets)
+
+    if not prepared_datasets:
+        st.stop()
+
+    all_data = pd.concat([item.dataframe for item in prepared_datasets], ignore_index=True)
+
+    months = sorted(all_data["month"].unique())
+    selected_months = st.multiselect("Mois à analyser", options=months, default=months)
+
+    categories = sorted(all_data["category"].unique())
+    selected_categories = st.multiselect(
+        "Catégories", options=categories, default=categories, help="Décochez pour masquer des activités."
+    )
+
+    filtered = all_data[
+        all_data["month"].isin(selected_months) & all_data["category"].isin(selected_categories)
+    ]
+
+    if filtered.empty:
+        st.warning("Aucune donnée disponible pour les filtres sélectionnés.")
+        st.stop()
+
+    summary = monthly_summary(filtered)
+    mom = month_over_month(filtered)
+
+    highlighted_months = ", ".join(selected_months) if selected_months else "Aucun mois sélectionné"
+    total_revenue = float(filtered["amount"].sum())
+    average_ticket = float(filtered["amount"].mean()) if not filtered.empty else 0.0
+    month_count = filtered["month"].nunique()
+
+    overview_tab, charts_tab, tables_tab = st.tabs([
+        "Vue d'ensemble",
+        "Graphiques",
+        "Données tabulaires",
+    ])
+
+    with overview_tab:
+        st.markdown(
+            f"""
+            <div class="helios-panel">
+                <h1>Résumé des filtres</h1>
+                <p>Période : {highlighted_months or '—'} · Catégories actives : {len(selected_categories)}</p>
+            </div>
+            """,
+            unsafe_allow_html=True,
+        )
+        m1, m2, m3 = st.columns(3)
+        m1.metric("Revenu total", f"{total_revenue:,.2f} €".replace(",", " "))
+        m2.metric("Ticket moyen", f"{average_ticket:,.2f} €".replace(",", " "))
+        m3.metric("Nombre de mois", month_count)
+
+        st.caption("Aperçu des transactions filtrées")
+        st.dataframe(filtered.head(100))
+
+    with charts_tab:
+        col1, col2 = st.columns([2, 1])
+        with col1:
+            st.plotly_chart(monthly_sales_bar(summary), use_container_width=True)
+        with col2:
+            st.plotly_chart(category_distribution(filtered), use_container_width=True)
+
+        line_fig, mom_fig = month_over_month_chart(mom)
+        col3, col4 = st.columns(2)
+        with col3:
+            st.plotly_chart(line_fig, use_container_width=True)
+        with col4:
+            st.plotly_chart(mom_fig, use_container_width=True)
+
+    with tables_tab:
+        st.write("### Revenus par mois et catégorie")
+        st.dataframe(summary)
+
+        st.write("### Evolution mois par mois")
+        st.dataframe(mom)
+
+    if generate_ai:
+        try:
+            insights = ChatGPTInsights(api_key=api_key or None, model=model)
+            with st.spinner("Analyse des données par l'IA en cours..."):
+                report = insights.summarise(summary, mom)
+            st.subheader("Analyse IA")
+            st.markdown(report)
+        except Exception as exc:
+            st.error(f"Impossible de générer le résumé IA: {exc}")
+    else:
+        st.info("Activez l'analyse IA dans le panneau de gauche pour obtenir un résumé automatique.")
+
+
+def _run_with_streamlit() -> None:
+    from streamlit.web import cli as stcli
+
+    sys.argv = ["streamlit", "run", str(Path(__file__).resolve())]
+    stcli.main()
+
+
+if __name__ == "__main__":
+    if getattr(st, "_is_running_with_streamlit", False):
+        main()
+    else:
+        _run_with_streamlit()
+elif getattr(st, "_is_running_with_streamlit", False):
+    main()
