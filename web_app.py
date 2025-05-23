import streamlit as st
import yaml
import tempfile
from src.parser import parse_incident_file
from src.analyzer import calculate_mttr, calculate_ttd, calculate_ttm
from src.generator import generate_postmortem

st.set_page_config(page_title="AI Incident Helper", layout="wide")

st.title("🧠 AI Incident Helper")
st.markdown("Carica un file YAML con i dati dell'incidente e genera un report post-mortem AI.")

uploaded_file = st.file_uploader("📁 Carica un file YAML", type=["yaml", "yml"])

if uploaded_file is not None:
    try:
        # 🔁 Leggi il file una volta sola
        content = uploaded_file.read()
        raw_content = content.decode("utf-8")

        # Mostra il contenuto YAML raw
        st.subheader("📄 Contenuto YAML caricato")
        st.code(raw_content, language="yaml")

        # Scrive contenuto su file temporaneo per il parser
        with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp_file:
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        # Parsing
        incident = parse_incident_file(tmp_file_path)

        if not incident:
            st.error("❌ Parsing fallito. Verifica che il file YAML sia valido.")
            st.stop()

        st.success("✅ Parsing completato con successo.")
        st.subheader("📋 Dati normalizzati")
        st.json(incident)

        # Calcolo metriche
        mttr = calculate_mttr(incident)
        ttd = calculate_ttd(incident)
        ttm = calculate_ttm(incident)

        st.metric("⏱️ MTTR", str(mttr))
        st.metric("🚨 Time to Detect", str(ttd))
        st.metric("🛠️ Time to Mitigate", str(ttm))

        # Generazione del report
        if st.button("🧠 Genera Report Post-Mortem AI"):
            with st.spinner("🧠 Generazione in corso..."):
                report = generate_postmortem(incident, mttr, ttd, ttm)

            st.subheader("📄 Report Generato")
            st.code(report, language="markdown")

            # Download del report
            st.download_button(
                label="💾 Scarica .md",
                data=report,
                file_name=f"{incident['incident_id']}_postmortem.md",
                mime="text/markdown"
            )

    except Exception as e:
        st.error(f"❌ Errore durante l'elaborazione: {e}")

