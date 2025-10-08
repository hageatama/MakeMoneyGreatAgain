import csv, json, subprocess, pathlib, sys, re, unicodedata, os
from datetime import datetime

# === 設定 ===
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")  # 必要なら env で差し替え
PROMPT_TEMPLATE = pathlib.Path("scripts/prompt.txt").read_text(encoding="utf-8")
DOCS_DIR = pathlib.Path("docs/companies")
DOCS_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_COLUMNS = ["コード", "銘柄名"]  # 必須

def slugify(text: str) -> str:
    # ファイル名安全化（全角→半角、記号除去）
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\\/:*?\"<>|]", "", text)  # Windows禁止文字
    text = re.sub(r"\s+", "-", text.strip())
    return text

def run_gemini(prompt: str) -> dict:
    # Gemini-CLI 非対話モード（JSON受け取り）
    # 環境変数 GEMINI_API_KEY があればキー運用、無ければ OAuth ログイン済みの環境を使用
    cmd = ["gemini", "-m", MODEL, "-p", prompt, "--output-format", "json"]
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out)

def yaml_dump(obj) -> str:
    try:
        import yaml
    except ImportError:
        raise SystemExit("PyYAML が未インストールです: pip install pyyaml")
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False)

def render_markdown(payload: dict, fm_extra: dict) -> str:
    # YAML Front Matter + 本文
    fm = {
        "title": f"{payload.get('company_name','')}" + (f" ({payload.get('code','')})" if payload.get('code') else ""),
        "code": payload.get("code"),
        "tags": payload.get("segments", []),
        "sources": payload.get("sources", []),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model_meta": fm_extra,  # ← ここに CSV のメタを格納
    }
    front = "---\n" + yaml_dump(fm) + "---\n"

    body_parts = []
    body_parts.append(f"## 事業概要\n{payload.get('business_summary','N/A')}\n")

    segs = payload.get("segments") or []
    if segs:
        body_parts.append("## セグメント\n" + "\n".join([f"- {s}" for s in segs]) + "\n")

    strengths = payload.get("moat_or_edge") or []
    if strengths:
        body_parts.append("## 強み\n" + "\n".join([f"- {s}" for s in strengths]) + "\n")

    risks = payload.get("risks") or []
    if risks:
        body_parts.append("## リスク\n" + "\n".join([f"- {s}" for s in risks]) + "\n")

    k = payload.get("kpis") or {}
    body_parts.append("## 主要KPI\n")
    body_parts.append(
f"""- 決算期: {k.get('fiscal_year','N/A')}
- 売上高(億円): {k.get('revenue_JPY_bil','N/A')}
- 営業利益率(%): {k.get('op_margin_pct','N/A')}
- ROE(%): {k.get('roe_pct','N/A')}
- PER: {k.get('per','N/A')}
- PBR: {k.get('pbr','N/A')}
- 配当利回り(%): {k.get('dividend_yield_pct','N/A')}
"""
    )

    sources = payload.get("sources") or []
    if sources:
        body_parts.append("## 出典\n" + "\n".join([f"- {u}" for u in sources]) + "\n")

    return front + "\n".join(body_parts)

def make_prompt(name: str, code: str) -> str:
    return f"""対象企業: {name}（証券コード:{code}）
{PROMPT_TEMPLATE}"""

def ensure_columns(header: list):
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise SystemExit(f"CSVに必須カラムがありません: {missing}（見出しを確認してください）")

def to_float_or_str(v):
    if v in (None, "", "N/A"):
        return "N/A"
    try:
        return float(v)
    except Exception:
        return str(v)

def main(csv_path="tickers.csv", limit=None):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        ensure_columns(reader.fieldnames or [])

        for i, row in enumerate(reader, start=1):
            if limit and i > limit:
                break

            code = str(row["コード"]).strip()
            name = str(row["銘柄名"]).strip()

            # Front-Matter へ格納する追加メタ（ある列だけ拾う）
            fm_extra = {}
            for key in ["fold","prob_up","pred","y_true","target_return","target_up","split_order","index"]:
                if key in row:
                    val = row[key]
                    # 数値っぽいものは数値化（Markdownでの検索性向上）
                    if key in ["prob_up","target_return"]:
                        fm_extra[key] = to_float_or_str(val)
                    elif key in ["fold","pred","y_true","target_up","index"]:
                        try:
                            fm_extra[key] = int(float(val))
                        except Exception:
                            fm_extra[key] = val
                    else:
                        fm_extra[key] = val

            prompt = make_prompt(name, code)

            # 生成＆保存
            fname = f"{code}-{slugify(name)}.md"
            outpath = DOCS_DIR / fname

            try:
                data = run_gemini(prompt)
                md = render_markdown(data, fm_extra)
            except subprocess.CalledProcessError as e:
                md = f"---\nerror: true\ncode: {code}\nname: {name}\n---\n\nCLI実行エラー:\n\n```\n{e}\n```"
            except json.JSONDecodeError as e:
                md = f"---\nerror: true\ncode: {code}\nname: {name}\n---\n\nJSONデコード失敗。プロンプトやモデル設定を見直してください。\n\n```\n{e}\n```"
            except Exception as e:
                md = f"---\nerror: true\ncode: {code}\nname: {name}\n---\n\n予期せぬエラー:\n\n```\n{e}\n```"

            outpath.write_text(md, encoding="utf-8")
            print("Wrote", outpath)

if __name__ == "__main__":
    # 例: python scripts/build.py your.csv  または  python scripts/build.py your.csv 50
    csv_path = sys.argv[1] if len(sys.argv) >= 2 else "tickers.csv"
    limit = int(sys.argv[2]) if len(sys.argv) >= 3 else None
    sys.exit(main(csv_path, limit))
