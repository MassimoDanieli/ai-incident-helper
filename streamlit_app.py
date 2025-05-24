
# ... omissis (tutta la tua app come prima) ...

    if incident_rows:
        df = pd.DataFrame(incident_rows)
        st.subheader("📋 Tabella Incidenti")
        st.dataframe(df, use_container_width=True)

        st.download_button(
            label="⬇️ Scarica CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="incident_dashboard.csv",
            mime="text/csv"
        )

        st.subheader("📈 Media Metriche")
        col1, col2, col3 = st.columns(3)
        col1.metric("MTTR medio", f"{df['MTTR (min)'].mean():.2f} min")
        col2.metric("TTD medio", f"{df['TTD (min)'].mean():.2f} min")
        col3.metric("TTM medio", f"{df['TTM (min)'].mean():.2f} min")

        fig = px.bar(df, x="Incident ID", y="MTTR (min)", title="MTTR per incidente", text="MTTR (min)")
        st.plotly_chart(fig, use_container_width=True)
