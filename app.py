    st.markdown("---")
    st.markdown("### Abonnements actifs & CA projeté")

    if not has_abos:
        st.info("Aucune donnée CSV d’inscriptions importée – impossible de calculer les abonnements actifs.")
    else:
        today = datetime.today().date()
        df_active, stats_abos = compute_active_abos_stats(df_abos, today)

        if stats_abos["nb_actifs"] == 0:
            st.info("Aucun abonnement récurrent actif détecté à ce jour (hors carnets / events).")
        else:
            nb_actifs = stats_abos["nb_actifs"]
            ca_actifs = stats_abos["ca_actifs"]
            ca_proj_next = stats_abos["ca_proj_next"]
            next_label = stats_abos["next_month_label"]

            cA1, cA2, cA3 = st.columns(3)
            cA1.metric("Abonnements actifs (aujourd’hui)", nb_actifs)
            cA2.metric("CA mensuel associé", f"{ca_actifs:,.0f} €".replace(",", " "))
            if next_label is not None:
                cA3.metric(f"CA projeté – {next_label}", f"{ca_proj_next:,.0f} €".replace(",", " "))
            else:
                cA3.metric("CA projeté (mois suivant)", f"{ca_proj_next:,.0f} €".replace(",", " "))

            # Détail par type d’abonnement
            df_type = (
                df_active.groupby("sous_type", as_index=False)
                .agg(
                    Nb=("offre", "count"),
                    CA=("prix_effectif", "sum"),
                )
                .sort_values("CA", ascending=False)
            )
            df_type["% des abos"] = (df_type["Nb"] / df_type["Nb"].sum() * 100).round(1)

            col_chart_actif, col_tab_actif = st.columns((1.2, 1))
            with col_chart_actif:
                chart_actif = donut_chart(
                    df_type.rename(columns={"sous_type": "Type d’abonnement", "CA": "CA"}),
                    "Type d’abonnement",
                    "CA",
                    "Répartition des abonnements actifs"
                )
                if chart_actif is not None:
                    st.altair_chart(chart_actif, use_container_width=True)
            with col_tab_actif:
                st.dataframe(df_type)
