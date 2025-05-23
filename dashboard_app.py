import streamlit as st
import yaml
import tempfile
import os
import pandas as pd
import plotly.express as px
from src.parser import parse_incident_file
from src.analyzer import calculate_mttr, calculate_ttd, calculate_ttm

st.set_page_config(page_title="📊 Incident Dashboard", layout="wide")
st.title("📊 Incident Dashboard")
st.markdown("Carica più file `.yaml` di incidenti per visualizzare metriche aggregate.")

uploaded_files = st.file_uploader("📁 Carica uno o più file YAML", type=["yaml", "yml"], accept_multiple_files=True)

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
            st.error(f"❌ Errore con il file {f.name}: {e}")

if incident_rows:
    df = pd.DataFrame(incident_rows)
    st.subheader("📋 Incident Table")
    st.dataframe(df, use_container_width=True)

    st.subheader("📈 Media Metriche")
    avg_mttr = df["MTTR (min)"].mean()
    avg_ttd = df["TTD (min)"].mean()
    avg_ttm = df["TTM (min)"].mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Avg MTTR", f"{avg_mttr:.2f} min")
    col2.metric("📊 Avg TTD", f"{avg_ttd:.2f} min")
    col3.metric("📊 Avg TTM", f"{avg_ttm:.2f} min")

    st.subheader("📉 Grafico MTTR per incidente")
    fig = px.bar(df, x="Incident ID", y="MTTR (min)", title="MTTR per incidente", text="MTTR (min)")
    st.plotly_chart(fig, use_container_width=True)

