
import streamlit as st
import requests

BACKEND_URL = st.secrets.get("BACKEND_URL", "http://localhost:5000")

st.title("Wet Gas Compressor - BC Recommender")

st.write("Simulate real-time data and recommend boundary conditions.")

uploaded_file = st.file_uploader("Upload JSON data", type=["json"])
if uploaded_file:
    import json
    data = json.load(uploaded_file)
    st.write("Data uploaded:", data)
    if st.button("Recommend BC"):
        resp = requests.post(f"{BACKEND_URL}/recommend-bc", json=data)
        st.write("Recommended BC:", resp.json())
