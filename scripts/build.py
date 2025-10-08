import csv, json, subprocess, pathlib, sys

PROMPT_TEMPLATE = pathlib.Path("scripts/prompt.txt").read_text(encoding="utf-8")
DOCS_DIR = pathlib.Path("docs/companies")
DOCS_DIR.mkdir(parents=True, exist_ok=True)

def run_gemini(prompt: str) -> dict:
    # --output-format json で構造化出力を受け取る
    # モデルは速さ優先なら gemini-2.5-flash、精度重視なら gemini-2.5-pro
    cmd = ["gemini", "-m", "gemini-2.5-flash", "-p", prompt, "--output-format", "json"]
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out)

def render_markdown(payload: dict) -> str:
    # YAML Front Matter + 本文（四季報風）
    fm = {
      "title": f"{payload['company_name']} ({payload['code']})",
      "code": payload["code"],
      "tags": payload.get("segments", []),
      "sources": payload.get("sources", [])
    }
    import yaml  # PyYAML
    front = "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n"
    body = []
    body.append(f"## 事業概要\n{payload['business_summary']}\n")
    if payload.get("segments"):
        body.append("## セグメント\n" + "\n".join([f"- {s}" for s in payload["segments"]]) + "\n")
    if payload.get("moat_or_edge"):
        body.append("## 強み\n" + "\n".join([f"- {s}" for s in payload["moat_or_edge"]]) + "\n")
    if payload.get("risks"):
        body.append("## リスク\n" + "\n".join([f"- {s}" for s in payload["risks"]]) + "\n")
    k = payload.get("kpis", {})
    body.append("## 主要KPI\n")
    body.append(
      f"""
- 決算期: {k.get('fiscal_year','N/A')}
- 売上高(億円): {k.get('revenue_JPY_bil','N/A')}
- 営業利益率(%): {k.get('op_margin_pct','N/A')}
- ROE(%): {k.get('roe_pct','N/A')}
- PER: {k.get('per','N/A')}
- PBR: {k.get('pbr','N/A')}
- 配当利回り(%): {k.get('dividend_yield_pct','N/A')}
""")
    if payload.get("sources"):
        body.append("## 出典\n" + "\n".join([f"- {u}" for u in payload["sources"]]) + "\n")
    return front + "\n".join(body)

def main(csv_path="tickers.csv"):
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row["code"].strip()
            name = row["name"].strip()
            prompt = f"""対象企業: {name}（証券コード:{code}）
{PROMPT_TEMPLATE}"""
            data = run_gemini(prompt)
            md = render_markdown(data)
            out = DOCS_DIR / f"{code}-{name}.md"
            out.write_text(md, encoding="utf-8")
            print("Wrote", out)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "tickers.csv"))
