import json
import re
from datetime import datetime

import anthropic
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="AI Visibility Auditor", page_icon="🔎", layout="wide")

CLAUDE_MODEL = "claude-opus-4-1"
PERPLEXITY_MODEL = "sonar-pro"


@st.cache_resource
def get_claude_client():
    api_key = st.secrets.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def get_perplexity_key():
    return st.secrets.get("PERPLEXITY_API_KEY")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def build_brand_patterns(brand: str):
    brand = brand.strip()
    escaped = re.escape(brand)
    compact = re.escape(re.sub(r"[\s\-]+", "", brand))
    hyphen_flex = re.escape(brand).replace(r"\ ", r"[\s\-]?")
    patterns = [
        re.compile(rf"(?i)(?<!\w){escaped}(?!\w)"),
        re.compile(rf"(?i)(?<!\w){hyphen_flex}(?!\w)"),
        re.compile(rf"(?i)(?<!\w){compact}(?!\w)"),
    ]
    unique = []
    seen = set()
    for pattern in patterns:
        if pattern.pattern not in seen:
            unique.append(pattern)
            seen.add(pattern.pattern)
    return unique


def detect_brand_mention(answer: str, brand: str):
    text = normalize_text(answer)
    patterns = build_brand_patterns(brand)
    match_positions = []

    for pattern in patterns:
        match = pattern.search(text)
        if match:
            match_positions.append((match.start(), match.end()))

    if not match_positions:
        return {
            "mentioned": False,
            "rank_estimate": "not mentioned",
            "answer_preview": text[:220] + ("..." if len(text) > 220 else ""),
            "first_position": None,
        }

    start, end = sorted(match_positions, key=lambda x: x[0])[0]
    preview_start = max(0, start - 90)
    preview_end = min(len(text), end + 140)
    rank_estimate = "early mention" if start <= 200 else "later mention"

    return {
        "mentioned": True,
        "rank_estimate": rank_estimate,
        "answer_preview": text[preview_start:preview_end],
        "first_position": start,
    }


def score_positioning(answer: str, brand: str, mentioned: bool):
    if not mentioned:
        return "not mentioned"

    lower = answer.lower()
    positive_cues = [
        "best",
        "top",
        "recommended",
        "popular",
        "leading",
        "great",
        "strong choice",
        "well-known",
    ]
    negative_cues = [
        "avoid",
        "expensive",
        "weak",
        "poor",
        "not recommended",
        "controversy",
        "complaint",
    ]
    pos = sum(1 for cue in positive_cues if cue in lower)
    neg = sum(1 for cue in negative_cues if cue in lower)

    if pos > neg:
        return "recommended / positive"
    if neg > pos:
        return "negative / challenged"
    return "neutral mention"


@st.cache_data(show_spinner=False)
def generate_queries(industry: str, n_queries: int):
    client = get_claude_client()
    if client is None:
        raise ValueError("ANTHROPIC_API_KEY is required to generate audit prompts.")

    prompt = f"""
Generate exactly {n_queries} realistic, neutral questions a person might ask an AI assistant when researching the category: {industry}.

Rules:
- No brand names.
- Vary intent: recommendations, comparisons, quality, price, trends, best options.
- Keep each query under 12 words when possible.
- Return only a valid JSON array of strings.
"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    start = raw.find("[")
    end = raw.rfind("]") + 1
    queries = json.loads(raw[start:end])

    if not isinstance(queries, list) or not queries:
        raise ValueError("Failed to generate queries.")

    return [normalize_text(q) for q in queries[:n_queries]]


def run_claude_query(query: str):
    client = get_claude_client()
    if client is None:
        raise ValueError("Add ANTHROPIC_API_KEY to Streamlit secrets.")

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=450,
        messages=[{"role": "user", "content": query}],
    )
    return response.content[0].text


def run_perplexity_query(query: str):
    api_key = get_perplexity_key()
    if not api_key:
        raise ValueError("Add PERPLEXITY_API_KEY to Streamlit secrets.")

    response = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": PERPLEXITY_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "Answer naturally and concisely. Do not use bullets unless helpful.",
                },
                {"role": "user", "content": query},
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def run_engine_query(engine: str, query: str):
    if engine == "Claude":
        return run_claude_query(query)
    if engine == "Perplexity":
        return run_perplexity_query(query)
    raise ValueError(f"Unsupported engine: {engine}")


def run_audit(brand: str, queries, engine: str, progress_slot, status_slot):
    rows = []
    for i, query in enumerate(queries, start=1):
        status_slot.text(f"{engine}: query {i}/{len(queries)} — {query}")
        answer = run_engine_query(engine, query)
        mention = detect_brand_mention(answer, brand)
        rows.append(
            {
                "engine": engine,
                "query": query,
                "mentioned": mention["mentioned"],
                "rank_estimate": mention["rank_estimate"],
                "positioning": score_positioning(answer, brand, mention["mentioned"]),
                "answer_preview": mention["answer_preview"],
                "full_answer": normalize_text(answer),
            }
        )
        progress_slot.progress(i / len(queries))

    progress_slot.empty()
    status_slot.empty()
    return rows


def summarize_results(df: pd.DataFrame):
    summary = (
        df.groupby("engine", dropna=False)
        .agg(hits=("mentioned", "sum"), total=("mentioned", "count"))
        .reset_index()
    )
    summary["visibility_pct"] = ((summary["hits"] / summary["total"]) * 100).round(0).astype(int)
    summary["visibility"] = summary["hits"].astype(str) + "/" + summary["total"].astype(str)
    return summary


st.title("🔎 AI Visibility Auditor")
st.markdown("Audit how often a brand appears in neutral category prompts across Claude and Perplexity.")

with st.sidebar:
    st.header("Setup")
    st.markdown("**Keys needed**")
    st.code("ANTHROPIC_API_KEY\nPERPLEXITY_API_KEY", language="bash")
    st.markdown("**Good demo brands**")
    st.markdown(
        "- Profound — LLM visibility / GEO\n"
        "- Adobe LLM Optimizer — LLM visibility / GEO\n"
        "- Alo — yoga activewear\n"
        "- FanDuel — sports betting"
    )

col1, col2, col3 = st.columns([2, 2, 1])
brand = col1.text_input("Brand name", placeholder="Profound, Zara, Alo, Adobe LLM Optimizer")
industry = col2.text_input("Industry / category", value="LLM visibility / GEO")
engine_mode = col3.selectbox("Engine", ["Both", "Claude", "Perplexity"])

st.caption("Use a plain-English category so the prompts stay neutral and realistic.")

n_queries = st.slider("Queries", min_value=3, max_value=12, value=6)
run = st.button("🚀 Run audit", type="primary", use_container_width=True)

if run:
    if not brand.strip():
        st.error("Enter a brand name.")
        st.stop()
    if not industry.strip():
        st.error("Enter an industry or category.")
        st.stop()

    engines = ["Claude", "Perplexity"] if engine_mode == "Both" else [engine_mode]

    missing = []
    if "Claude" in engines and get_claude_client() is None:
        missing.append("ANTHROPIC_API_KEY")
    if "Perplexity" in engines and not get_perplexity_key():
        missing.append("PERPLEXITY_API_KEY")
    if missing:
        st.error("Missing Streamlit secrets: " + ", ".join(missing))
        st.stop()

    try:
        with st.spinner("Generating neutral prompts..."):
            queries = generate_queries(industry, n_queries)
    except Exception as exc:
        st.error(f"Could not generate prompts: {exc}")
        st.stop()

    st.success(f"Generated {len(queries)} reusable prompts for {industry}.")
    with st.expander("See generated prompts", expanded=False):
        for i, q in enumerate(queries, start=1):
            st.markdown(f"{i}. {q}")

    all_rows = []
    st.subheader("Audit progress")
    progress_rows = st.columns(len(engines))
    progress_ui = {}

    for idx, engine in enumerate(engines):
        with progress_rows[idx]:
            st.markdown(f"**{engine}**")
            progress_ui[engine] = {
                "state": st.empty(),
                "progress": st.progress(0),
                "detail": st.empty(),
            }
            progress_ui[engine]["state"].info("Queued")

    for engine in engines:
        progress_ui[engine]["state"].warning("Running...")
        rows = []
        try:
            rows = run_audit(
                brand.strip(),
                queries,
                engine,
                progress_ui[engine]["progress"],
                progress_ui[engine]["detail"],
            )
            all_rows.extend(rows)
            hits = sum(1 for row in rows if row["mentioned"])
            progress_ui[engine]["state"].success(f"Complete — {hits}/{len(rows)} mentions")
        except Exception as exc:
            progress_ui[engine]["progress"].empty()
            progress_ui[engine]["detail"].empty()
            progress_ui[engine]["state"].error("Failed")
            st.error(f"{engine} audit failed: {exc}")

    if not all_rows:
        st.stop()

    results_df = pd.DataFrame(all_rows)
    summary_df = summarize_results(results_df)

    st.subheader("Visibility summary")
    metric_cols = st.columns(len(summary_df))
    for idx, row in summary_df.iterrows():
        metric_cols[idx].metric(row["engine"], f"{row['visibility_pct']}%", row["visibility"])

    display_summary = summary_df[["engine", "visibility_pct", "visibility"]].rename(
        columns={
            "engine": "Engine",
            "visibility_pct": "Visibility %",
            "visibility": "Hits",
        }
    )
    st.dataframe(display_summary, use_container_width=True, hide_index=True)

    st.subheader("Per-query results")
    pivot = results_df.pivot(index="query", columns="engine", values="mentioned")
    if not pivot.empty:
        pretty_pivot = pivot.apply(lambda col: col.map(lambda x: "✅" if x else "❌"))
        st.dataframe(pretty_pivot.reset_index(), use_container_width=True, hide_index=True)

    for engine in engines:
        st.markdown(f"### {engine} details")
        engine_df = results_df[results_df["engine"] == engine].reset_index(drop=True)
        for _, row in engine_df.iterrows():
            icon = "✅" if row["mentioned"] else "❌"
            with st.expander(f"{icon} {row['query']}"):
                st.markdown(f"**Mentioned:** {'Yes' if row['mentioned'] else 'No'}")
                st.markdown(f"**Estimated position:** {row['rank_estimate']}")
                st.markdown(f"**Positioning:** {row['positioning']}")
                st.markdown(f"**Preview:** {row['answer_preview']}")
                with st.popover("Full answer"):
                    st.write(row["full_answer"])

    export = {
        "brand": brand.strip(),
        "industry": industry.strip(),
        "engine_mode": engine_mode,
        "queries": queries,
        "timestamp": datetime.now().isoformat(),
        "summary": summary_df.to_dict(orient="records"),
        "results": results_df.to_dict(orient="records"),
    }

    st.download_button(
        "💾 Download JSON report",
        data=json.dumps(export, indent=2),
        file_name=f"visibility_audit_{brand.strip().lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
        use_container_width=True,
    )
