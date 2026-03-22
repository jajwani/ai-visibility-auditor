import streamlit as st
import anthropic
import json
import pandas as pd
from datetime import datetime

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
st.markdown("**Tests if brands appear in Claude's natural responses to generic industry queries**")

# NEW SIDEBAR: Examples  
st.sidebar.header("💡 Try these examples")
st.sidebar.markdown("""
**Profound** – `LLM visibility / GEO`  
 
**Adobe LLM Optimizer** – `LLM visibility / GEO`  
 
**Zara** – `fast fashion retail`  
 
**Alo** – `yoga activewear`  
 
**Lululemon** – `athletic apparel`  
 
**Aritzia** – `women's fashion`  
 
**Audi** – `luxury automotive`  
 
**Mohegan Sun** – `casino resort`  
 
**Allbirds** – `sustainable footwear`  
 
**Glossier** – `clean beauty`  
 
**Starbucks** – `coffee cafes`  
 
**FanDuel** – `sports betting`  
 
**DraftKings** – `sports betting`
""")
# Inputs with guidance
col1, col2 = st.columns([3,1])
brand = col1.text_input(
    "Brand name", 
    placeholder="MGM Sun, Profound, Zara, etc."
)

industry = col1.text_input(
    "Industry", 
    value="luxury automotive"
)

st.caption("Describe the space in plain English so Claude knows what kind of questions to generate (e.g., ‘LLM visibility / GEO', ‘yoga activewear', ‘casino resort', ‘fast fashion retail'). Not a SIC/NAICS code or a long keyword list.")

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
        
        Return ONLY valid JSON array of strings. 
        Generic questions only—no specific brands.
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
            st.success(f"✅ Generated {len(queries)} generic queries")
        except:
            st.error("Failed to parse queries. Try again.")
            st.stop()
        
        # STEP 2: Audit each query naturally  
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, query in enumerate(queries):
            status_text.text(f"Query {i+1}/{len(queries)}: {query[:60]}...")
            
            resp = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=400,
                messages=[{"role": "user", "content": query}]
            )
            
            answer = resp.content[0].text.lower()
            
            # Check for brand mentions (case-insensitive, variants)
            brand_lower = brand.lower()
            variants = [brand_lower, brand_lower.replace(" ", ""), brand_lower.replace("-", "")]
            mentioned = any(variant in answer for variant in variants)
            
            # Context if mentioned
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
            
            progress_bar.progress((i+1) / len(queries))
        
        # STEP 3: Results
        hits = sum(1 for r in results if r["mentioned"])
        pct = round((hits / len(results)) * 100)
        
        st.balloons()
        st.metric(label="Visibility", value=f"{pct}%", delta=f"{hits}/{len(results)}")
        
        # Results table
        st.subheader("Query Results")
        df = pd.DataFrame(results)
        for idx, row in df.iterrows():
            icon = "✅" if row["mentioned"] else "❌"
            with st.expander(f"{icon} {row['query'][:70]}..."):
                st.markdown(f"**Mentioned:** {'Yes' if row['mentioned'] else 'No'}")
                st.markdown(f"**Answer preview:** {row['answer_preview']}")
        
        # Download JSON
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
            f"audit_{brand.lower().replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "application/json"
        )
