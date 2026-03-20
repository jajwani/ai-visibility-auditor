import streamlit as st
import anthropic
import json
import re

# Secure API key from Streamlit Secrets
@st.cache_resource
def get_client():
    try:
        API_KEY = st.secrets["ANTHROPIC_API_KEY"]
        return anthropic.Anthropic(api_key=API_KEY)
    except:
        st.error("❌ Add ANTHROPIC_API_KEY to Streamlit Cloud Secrets")
        st.stop()

client = get_client()

st.title("🤖 AI Visibility Auditor")
st.markdown("**Tests brand visibility in Claude's natural responses to generic industry queries**")

# Your benchmark results (sidebar)
st.sidebar.header("Your GEO Benchmark")
st.sidebar.markdown("""
| Brand                | Visibility |
|----------------------|------------|
| **Profound**         | **100%** (6/6) ⭐ |
| Adobe LLM Optimizer  | **0%** (0/6)    |
| Brandlight           | **0%** (0/6)    |
""")
st.sidebar.markdown("[GitHub](https://github.com/yourusername/ai-visibility-auditor)")

# Inputs (clean layout)
col1, col2 = st.columns([2,1])
brand = col1.text_input("Brand name", placeholder="MGM Sun, Profound, etc.")
industry = col1.text_input("Industry", value="casino", placeholder="casino, GEO, analytics")
n_queries = col2.number_input("Queries", 3, 12, 6, help="More = better accuracy")

if st.button("🚀 Run Audit", type="primary") and brand.strip():
    with st.spinner(f"Auditing {brand} across {n_queries} generic {industry} queries..."):
        
        # STEP 1: Generate GENERIC queries (NO BRAND BIAS)
        gen_prompt = f"""
        Generate exactly {n_queries} realistic, generic questions people ask about {industry}.
        
        Examples for "casino":
        - "best casinos in Las Vegas?"
        - "top casino loyalty programs?"
        - "casino tournaments worth attending?"
        
        Return ONLY valid JSON array of strings. Generic questions only—no brand names.
        """
        
        queries_raw = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": gen_prompt}]
        ).content[0].text
        
        # Parse JSON safely
        try:
            start = queries_raw.find('[')
            end = queries_raw.rfind(']') + 1
            queries = json.loads(queries_raw[start:end])
        except:
            st.error("Failed to parse queries. Try again.")
            st.stop()
        
        st.info(f"✅ Generated {len(queries)} generic queries")
        
        # STEP 2: Audit each query naturally
        results = []
        progress = st.progress(0)
        
        for i, query in enumerate(queries):
            # Ask Claude naturally (no brand priming)
            resp = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=400,
                messages=[{"role": "user", "content": query}]
            )
            
            answer = resp.content[0].text.lower()
            
            # Check for brand mentions (case-insensitive, multiple variants)
            brand_lower = brand.lower()
            variants = [brand_lower, brand_lower.replace(" ", ""), brand_lower.replace("-", "")]
            mentioned = any(variant in answer for variant in variants)
            
            # Context snippet (if mentioned)
            context = ""
            if mentioned:
                idx = answer.find(brand_lower)
                start = max(0, idx - 80)
                end = min(len(answer), idx + len(brand) + 100)
                context = answer[start:end].replace('\n', ' ')
            
            results.append({
                "query": query,
                "mentioned": mentioned,
                "answer_preview": answer[:120] + "..." if not mentioned else context
            })
            
            progress.progress((i+1) / len(queries))
        
        # STEP 3: Results
        hits = sum(1 for r in results if r["mentioned"])
        pct = round((hits / len(results)) * 100)
        
        st.success(f"**{brand}: {pct}% visibility ({hits}/{len(results)})**")
        st.metric("Mentions", f"{hits}/{len(results)}", f"{pct}%")
        
        # Results table
        df = pd.DataFrame(results)
        st.subheader("Query Results")
        for idx, row in df.iterrows():
            icon = "✅" if row["mentioned"] else "❌"
            with st.expander(f"{icon} {row['query'][:70]}..."):
                st.markdown(f"**Answer:** {row['answer_preview']}")
                st.caption(f"Brand mentioned: {'Yes' if row['mentioned'] else 'No'}")
        
        # Download
        data = {
            "brand": brand,
            "industry": industry,
            "queries": n_queries,
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "visibility_pct": pct
        }
        st.download_button(
            "💾 Download JSON Report",
            json.dumps(data, indent=2),
            f"audit_{brand.lower().replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.json",
            "application/json"
        )

st.caption("Pure methodology: generic queries → natural Claude answers → brand mention detection")
