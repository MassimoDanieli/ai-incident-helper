import streamlit as st

# App internals
from src.parser import parse_incident_file
from src.analyzer import calculate_mttr, calculate_ttd, calculate_ttm
from src.generator import generate_postmortem

import yaml
import tempfile
import os
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="AI Incident Helper", layout="wide")

# Sidebar
st.sidebar.title("🧭 Navigazione")
view = st.sidebar.radio("Seleziona vista", ["🧠 Analisi Singolo Incidente", "📊 Dashboard Multi-Incidente"])

# -------------------------------
# 🧠 ANALISI SINGOLA
# -------------------------------
if view == "🧠 Analisi Singolo Incidente":
    st.title("🧠 AI Incident Helper – Singolo Incidente")

    uploaded_file = st.file_uploader("📁 Carica un file YAML", type=["yaml", "yml"], key="single")

    if uploaded_file:
        try:
            content = uploaded_file.read()
            raw_content = content.decode("utf-8")
            st.subheader("📄 Contenuto YAML caricato")
            st.code(raw_content, language="yaml")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp_file:
                tmp_file.write(content)
                tmp_file_path = tmp_file.name

            incident = parse_incident_file(tmp_file_path)
            if not incident:
                st.error("❌ Parsing fallito.")
                st.stop()

            st.success("✅ Parsing riuscito.")
            st.json(incident)

            mttr = calculate_mttr(incident)
            ttd = calculate_ttd(incident)
            ttm = calculate_ttm(incident)

            st.metric("⏱️ MTTR", str(mttr))
            st.metric("🚨 TTD", str(ttd))
            st.metric("🛠️ TTM", str(ttm))

            if st.button("🧠 Genera Post-Mortem"):
                with st.spinner("Generazione in corso..."):
                    report = generate_postmortem(incident, mttr, ttd, ttm)

                st.subheader("📄 Report Generato")
                st.code(report, language="markdown")
                st.download_button("💾 Scarica .md", data=report,
                                   file_name=f"{incident['incident_id']}_postmortem.md",
                                   mime="text/markdown")

        except Exception as e:
            st.error(f"❌ Errore: {e}")

# -------------------------------
# 📊 DASHBOARD MULTI-INCIDENTE
# -------------------------------
if view == "📊 Dashboard Multi-Incidente":
    st.title("📊 Dashboard Multi-Incidente")

    uploaded_files = st.file_uploader("📁 Carica uno o più file YAML", type=["yaml", "yml"],
                                       accept_multiple_files=True, key="multi")

    incident_rows = []

    if uploaded_files:
        for f in uploaded_files:
            try:
                content = f.read()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp_file:
                    tmp_file.write(content)
                    tmp_file_path = tmp_file.name

                incident = parse_incident_file(tmp_file_path)
                if not incident:
                    st.warning(f"⚠️ Parsing fallito: {f.name}")
                    continue

                mttr = calculate_mttr(incident).total_seconds() / 60
                ttd = calculate_ttd(incident).total_seconds() / 60
                ttm = calculate_ttm(incident).total_seconds() / 60

                incident_rows.append({
                    "Incident ID": incident["incident_id"],
                    "MTTR (min)": round(mttr, 2),
                    "TTD (min)": round(ttd, 2),
                    "TTM (min)": round(ttm, 2)
                })

            except Exception as e:
                st.error(f"❌ Errore con {f.name}: {e}")

    if incident_rows:
        df = pd.DataFrame(incident_rows)
        st.subheader("📋 Tabella Incidenti")
        st.dataframe(df, use_container_width=True)

        st.subheader("📈 Media Metriche")
        col1, col2, col3 = st.columns(3)
        col1.metric("MTTR medio", f"{df['MTTR (min)'].mean():.2f} min")
        col2.metric("TTD medio", f"{df['TTD (min)'].mean():.2f} min")
        col3.metric("TTM medio", f"{df['TTM (min)'].mean():.2f} min")

        fig = px.bar(df, x="Incident ID", y="MTTR (min)", title="MTTR per incidente", text="MTTR (min)")
        st.plotly_chart(fig, use_container_width=True)

