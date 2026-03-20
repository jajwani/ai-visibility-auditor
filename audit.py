#!/usr/bin/env python3
"""
AI Visibility Auditor for Brands
Checks how often your brand appears in Claude's answers to realistic industry queries.
"""

import os
import json
import re
import sys
from datetime import datetime
import anthropic

# ── colour helpers ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def c(text, *codes): return "".join(codes) + str(text) + RESET
def hr(char="─", width=60): print(c(char * width, DIM))


# ── Claude helpers ────────────────────────────────────────────────────────────
def make_client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print(c("✗ ANTHROPIC_API_KEY environment variable not set.", RED, BOLD))
        print(f"  Run:  {c('export ANTHROPIC_API_KEY=sk-ant-...', CYAN)}")
        sys.exit(1)
    return anthropic.Anthropic(api_key=key)


def ask_claude(client, prompt, system=None):
    kwargs = dict(
        model="claude-opus-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system
    msg = client.messages.create(**kwargs)
    return msg.content[0].text


# ── core logic ────────────────────────────────────────────────────────────────
def generate_queries(client, brand, industry, count):
    print(f"\n{c('→', CYAN)} Generating {count} queries for {c(brand, BOLD)} in {c(industry, BOLD)}…")
    prompt = (
        f"Generate exactly {count} realistic questions a person might ask an AI assistant "
        f"when researching or shopping for {industry} solutions. "
        f"These should be natural queries where a brand like \"{brand}\" might realistically "
        f"appear in an AI answer. "
        f"Return ONLY a JSON array of question strings, nothing else."
    )
    raw = ask_claude(client, prompt,
                     system="Return only a valid JSON array of strings. No markdown, no backticks, no explanation.")
    clean = re.sub(r"```json|```", "", raw).strip()
    return json.loads(clean)


def audit_query(client, brand, query):
    response = ask_claude(client, query)
    mentioned = brand.lower() in response.lower()
    context = ""
    if mentioned:
        low = response.lower()
        idx = low.find(brand.lower())
        start = max(0, idx - 100)
        end   = min(len(response), idx + len(brand) + 150)
        context = ("…" if start else "") + response[start:end] + ("…" if end < len(response) else "")
    return {"query": query, "response": response, "mentioned": mentioned, "context": context}


# ── report ────────────────────────────────────────────────────────────────────
def print_report(brand, results):
    hits  = sum(1 for r in results if r["mentioned"])
    total = len(results)
    pct   = round(hits / total * 100)

    print("\n")
    hr("═")
    print(c(f"  AI VISIBILITY REPORT — {brand.upper()}", BOLD))
    hr("═")

    colour = GREEN if pct >= 60 else YELLOW if pct >= 30 else RED
    print(f"\n  Visibility rate : {c(f'{pct}%', colour, BOLD)}")
    print(f"  Queries audited : {total}")
    print(f"  Mentions found  : {hits}")
    print()
    hr()

    for i, r in enumerate(results, 1):
        icon  = c("✓", GREEN) if r["mentioned"] else c("✗", RED)
        label = c("MENTIONED",     GREEN) if r["mentioned"] else c("NOT MENTIONED", RED)
        print(f"\n  {icon}  [{label}]  {c(r['query'], BOLD)}")
        if r["mentioned"] and r["context"]:
            hi = re.sub(re.escape(brand), lambda m: c(m.group(), GREEN, BOLD), r["context"], flags=re.IGNORECASE)
            print(f"\n     {c('Context:', DIM)}")
            for line in hi.split("\n"):
                print(f"       {line}")
        elif not r["mentioned"]:
            snippet = r["response"][:200].replace("\n", " ")
            print(f"\n     {c(snippet + '…', DIM)}")

    print()
    hr("═")
    return hits, total, pct


def save_report(brand, results, hits, total, pct):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"audit_{brand.lower().replace(' ', '_')}_{ts}.json"
    data = {
        "brand": brand,
        "timestamp": datetime.now().isoformat(),
        "summary": {"visibility_rate_pct": pct, "queries": total, "mentions": hits},
        "results": [{"query": r["query"], "mentioned": r["mentioned"], "context": r["context"]} for r in results],
    }
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n  {c('✓', GREEN)} Report saved to {c(filename, CYAN)}\n")
    return filename


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    print(c("\n  AI Visibility Auditor for Brands", BOLD, CYAN))
    print(c("  Powered by Anthropic Claude\n", DIM))

    client = make_client()

    # ── inputs ────────────────────────────────────────────────────────────────
    brand    = input("  Brand name          : ").strip()
    industry = input("  Industry / category : ").strip()
    count_s  = input("  Number of queries   [6]: ").strip()
    count    = int(count_s) if count_s.isdigit() else 6

    if not brand or not industry:
        print(c("✗ Brand name and industry are required.", RED))
        sys.exit(1)

    # ── generate queries ──────────────────────────────────────────────────────
    queries = generate_queries(client, brand, industry, count)
    print(f"\n  {c('Generated queries:', DIM)}")
    for i, q in enumerate(queries, 1):
        print(f"    {c(i, DIM)}. {q}")

    edit = input("\n  Edit queries? (y/N) : ").strip().lower()
    if edit == "y":
        print("  Enter new queries one per line (blank line to finish):")
        custom = []
        while True:
            line = input("    > ").strip()
            if not line:
                break
            custom.append(line)
        if custom:
            queries = custom

    # ── audit ─────────────────────────────────────────────────────────────────
    print(f"\n  {c('Running audit…', CYAN)}")
    hr()
    results = []
    for i, q in enumerate(queries, 1):
        print(f"  [{i}/{len(queries)}] {q[:70]}{'…' if len(q)>70 else ''}", end="", flush=True)
        r = audit_query(client, brand, q)
        results.append(r)
        icon = c(" ✓", GREEN) if r["mentioned"] else c(" ✗", RED)
        print(icon)

    # ── report ────────────────────────────────────────────────────────────────
    hits, total, pct = print_report(brand, results)

    save = input("  Save JSON report? (Y/n) : ").strip().lower()
    if save != "n":
        save_report(brand, results, hits, total, pct)


if __name__ == "__main__":
    main()
