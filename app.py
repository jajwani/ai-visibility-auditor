import streamlit as st
import subprocess
import json
import os
from datetime import datetime

st.title("🤖 AI Visibility Auditor")
st.markdown("**Test brand visibility in Claude's answers to realistic queries**")

# Your results sidebar
st.sidebar.header("Your Benchmark Results")
st.sidebar.markdown("""
| Brand | Visibility |
|-------|------------|
| Profound | **100%** (6/6) ⭐ |
| Adobe LLM Optimizer | 0% (0/6) |
| Brandlight | 0% (0/6) |
""")

brand = st.text_input("Brand name", value="YourBrand")
industry = st.text_input("Industry", value="LLM visibility / GEO")
queries = st.number_input("Queries", 3, 12, 6)

if st.button("🚀 Run Audit", type="primary"):
    with st.spinner("Generating queries → auditing Claude..."):
        # Run your CLI tool as subprocess
        cmd = f"echo '{brand}' | echo '{industry}' | echo '{queries}' | python audit.py"
        
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True,
            env={**os.environ, "ANTHROPIC_API_KEY": st.secrets["ANTHROPIC_API_KEY"]}
        )
        
        st.subheader("Results")
        st.code(result.stdout)
