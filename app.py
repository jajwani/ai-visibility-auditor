import streamlit as st
import anthropic
import json

# Load API key securely
try:
    API_KEY = st.secrets["ANTHROPIC_API_KEY"]
    client = anthropic.Anthropic(api_key=API_KEY)
except:
    st.error("❌ Add ANTHROPIC_API_KEY to Streamlit Secrets")
    st.stop()

st.title("🤖 AI Visibility Auditor")
st.markdown("Tests if brands appear in Claude's answers to realistic industry queries")

# Your benchmark results
st.sidebar.header("Benchmark Results")
st.sidebar.markdown("""
| Brand                | Visibility |
|----------------------|------------|
| **Profound**         | **100%** ⭐ |
| Adobe LLM Optimizer  | **0%**     |
| Brandlight           | **0%**     |
""")

# Inputs
col1, col2 = st.columns(2)
brand = col1.text_input("Brand name")
industry = col2.text_input("Industry", value="LLM visibility / GEO")
n_queries = st.slider("Queries", 3, 12, 6)

if st.button("🚀 Run Audit", type="primary") and brand:
    with st.spinner("Claude generating queries → answering → analyzing..."):
        # Step 1: Generate queries
        gen_prompt = f"""
        Generate exactly {n_queries} realistic questions about {industry} 
        where a brand like "{brand}" might appear. 
        Return ONLY JSON array of strings.
        """
        
        queries_raw = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": gen_prompt}]
        ).content[0].text
        
        # Extract JSON
        start = queries_raw.find('[')
        end = queries_raw.rfind(']') + 1
        queries = json.loads(queries_raw[start:end])
        
        # Step 2: Audit each query
        results = []
        for i, query in enumerate(queries, 1):
            st.status(f"Query {i}/{len(queries)}: {query[:60]}...")
            
            resp = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=400,
                messages=[{"role": "user", "content": query}]
            )
            
            answer = resp.content[0].text.lower()
            mentioned = brand.lower() in answer
            
            results.append({
                "query": query,
                "mentioned": mentioned,
                "preview": answer[:150] + "..." if not mentioned else answer
            })
        
        # Step 3: Results
        hits = sum(1 for r in results if r["mentioned"])
        pct = round(hits / len(results) * 100)
        
        st.success(f"**Visibility: {pct}% ({hits}/{len(results)})**")
        
        st.subheader("Detailed Results")
        for r in results:
            icon = "✅" if r["mentioned"] else "❌"
            with st.expander(f"{icon} {r['query'][:80]}..."):
                st.write(f"**Mentioned:** {'Yes' if r['mentioned'] else 'No'}")
                st.write("**Preview:**", r["preview"])
        
        # Download JSON
        data = {"brand": brand, "industry": industry, "results": results}
        st.download_button("💾 Download JSON", 
                          json.dumps(data, indent=2), 
                          f"audit_{brand.lower().replace(' ','_')}.json")
