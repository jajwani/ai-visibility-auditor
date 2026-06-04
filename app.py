import json
import re
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import anthropic

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
    for p in patterns:
        if p.pattern not in seen:
            unique.append(p)
            seen.add(p.pattern)
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
    if start <= 200:
        rank_estimate = "early mention"
    else:
        rank_estimate = "later mention"

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
        "best", "top", "recommended", "popular", "leading", "great", "strong choice", "well-known"
    ]
    negative_cues = [
        "avoid", "expensive", "weak", "poor", "not recommended", "controversy", "complaint"
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
        messages=[
            {"role": "user", "content": query}
        ],
    )
    return response.content[0].text


def run_perplexity_query(query: str):
    api_key = get_perplexity_key()
    if not api_key:
        raise ValueError("Add 
