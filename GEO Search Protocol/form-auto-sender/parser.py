"""
parser.py  —  MDリスト読み込みモジュール

対応フォーマット（スクレイパー出力）:
  - **会社名**（★評価 / 口コミ数 / Webあり）
    - 住所: ...
    - Web: https://...
    - 電話: 03-XXXX-XXXX
    - placeId: ChIJ...

ファイル名パターン: YYYY-MM-DD_業種名_エリア名.md
"""

from __future__ import annotations

import re
import sys
import json
import argparse
from pathlib import Path
from typing import Optional

from config import VAULT_ROOT


# ─── 正規表現パターン ───────────────────────────────────────────────────────────

# ファイル名: 2026-05-12_美容クリニック_港区.md
FILENAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(.+?)_(.+?)\.md$")
PILOT_FILENAME_RE = re.compile(
    r"^ARI-(Pilot(-Form-Friendly-\d+|-Timeout-Retry|-\d+)|Canary-[A-Za-z0-9-]+)\.md$"
)

# 会社名ブロック開始: - **麻布台美容皮膚科クリニック**（★4.8 / 84件 / Webあり）
COMPANY_RE = re.compile(
    r"^- \*\*(.+?)\*\*（★([\d.]+) / (\d+)件"
)

# フィールド行（パイロット MD のメタデータ行を含む）
FIELD_RE = re.compile(
    r"^\s+- (住所|Web|電話|placeId|業種|ソース|選定理由|フォームURL): (.+)$"
)

# リストMDヘッダ: - Tier: 業種1 / エリア1
TIER_HEADER_RE = re.compile(r"^- Tier:\s*業種(\d+)\s*/\s*エリア(\d+)")


# ─── パース処理 ────────────────────────────────────────────────────────────────

def _resolve_path(raw: str) -> Path:
    """
    Obsidian の @プレフィックスを除去し、絶対パスに解決する。
    - "@40_Sales/..." → VAULT_ROOT / "40_Sales/..."
    - 絶対パスはそのまま
    - 相対パスはカレントディレクトリ基準
    """
    stripped = raw.lstrip("@").strip()
    p = Path(stripped)
    if p.is_absolute():
        return p
    # Vault ルートからの相対パスを試みる
    vault_candidate = VAULT_ROOT / stripped
    if vault_candidate.exists():
        return vault_candidate
    # カレントディレクトリ基準
    return Path.cwd() / stripped


def _parse_filename(path: Path) -> tuple[str, str, str]:
    """ファイル名から (date, industry_name, area_name) を抽出する。"""
    m = FILENAME_RE.match(path.name)
    if m:
        return m.group(1), m.group(2), m.group(3)
    if PILOT_FILENAME_RE.match(path.name):
        return "2026-08-09", "ARI-Pilot", "東京都台東区"
    raise ValueError(
        f"ファイル名が期待パターンに一致しません: {path.name}\n"
        "期待パターン: YYYY-MM-DD_業種名_エリア名.md または ARI-Pilot-N.md"
    )


def _clean_url(url: str) -> str:
    """UTM パラメータ等を含む URL をそのまま返す（仕様上は保持）。"""
    return url.strip()


def parse_md_file(md_path_raw: str) -> list[dict]:
    """
    MDファイルを読み込み、企業リストを返す。

    Args:
        md_path_raw: ファイルパス（@プレフィックス可・絶対/相対どちらも可）

    Returns:
        list[dict]:  仕様書 §1 の出力データ構造に準拠したリスト
    """
    path = _resolve_path(md_path_raw)
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {path}")

    date, industry_name, area_name = _parse_filename(path)

    text = path.read_text(encoding="utf-8")
    industry_tier: Optional[int] = None
    area_tier: Optional[int] = None
    for line in text.splitlines():
        m_tier = TIER_HEADER_RE.match(line.strip())
        if m_tier:
            industry_tier = int(m_tier.group(1))
            area_tier = int(m_tier.group(2))
            break

    companies: list[dict] = []
    current: Optional[dict] = None

    for line in text.splitlines():
        # 会社名行
        m_company = COMPANY_RE.match(line)
        if m_company:
            if current:
                companies.append(current)
            current = {
                "company_name":  m_company.group(1).strip(),
                "rating":        float(m_company.group(2)),
                "review_count":  int(m_company.group(3)),
                "website_url":   None,
                "phone":         None,
                "address":       None,
                "place_id":      None,
                "industry_name": industry_name,
                "area_name":     area_name,
                "date":          date,
                "industry_tier": industry_tier,
                "area_tier":     area_tier,
            }
            continue

        # フィールド行
        if current:
            m_field = FIELD_RE.match(line)
            if m_field:
                key, val = m_field.group(1), m_field.group(2).strip()
                if key == "住所":
                    current["address"] = val
                elif key == "Web":
                    current["website_url"] = _clean_url(val)
                elif key == "電話":
                    current["phone"] = val
                elif key == "placeId":
                    current["place_id"] = val
                elif key == "業種":
                    current["industry_name"] = val
                elif key == "ソース":
                    current["source_list"] = val
                elif key == "選定理由":
                    current["selection_reason"] = val
                elif key == "フォームURL":
                    current["form_url"] = val

    if current:
        companies.append(current)

    return companies


def parse_md_list(input_path: str) -> list[dict]:
    """
    ディレクトリまたは単一ファイルを受け取り、全企業リストを返す。
    main.py から呼び出される公開インターフェース。
    """
    p = _resolve_path(input_path)
    results: list[dict] = []

    if p.is_dir():
        for md_file in sorted(p.glob("*.md")):
            try:
                results.extend(parse_md_file(str(md_file)))
            except (ValueError, FileNotFoundError) as e:
                print(f"[WARN] {md_file.name} をスキップ: {e}", file=sys.stderr)
    else:
        results = parse_md_file(input_path)

    return results


# ─── --test モード ─────────────────────────────────────────────────────────────

def _run_test(file_arg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  parser.py テストモード")
    print(f"  入力: {file_arg}")
    print(f"{'='*60}\n")

    try:
        companies = parse_md_file(file_arg)
    except (ValueError, FileNotFoundError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"✅ パース成功: {len(companies)} 件\n")

    for i, c in enumerate(companies, 1):
        print(f"[{i:02d}] {c['company_name']}")
        it = c.get("industry_tier")
        at = c.get("area_tier")
        tier_part = ""
        if it is not None:
            tier_part = f"  /  業種tier: T{it}"
        if at is not None:
            tier_part += f"  /  エリアtier: T{at}"
        print(
            f"      業種: {c['industry_name']}{tier_part}  /  エリア: {c['area_name']}  /  日付: {c['date']}"
        )
        print(f"      評価: ★{c['rating']} ({c['review_count']}件)")
        print(f"      Web: {c['website_url']}")
        print(f"      Tel: {c['phone']}")
        print(f"      住所: {c['address']}")
        print(f"      placeId: {c['place_id']}")
        print()

    print("─── JSON プレビュー（先頭1件） ───")
    print(json.dumps(companies[0], ensure_ascii=False, indent=2))
    print(f"\n{'='*60}\n")


# ─── エントリーポイント ────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="MDリストパーサー")
    ap.add_argument("--test", metavar="FILE", help="テストモード: 指定ファイルをパースして内容を表示")
    args = ap.parse_args()

    if args.test:
        _run_test(args.test)
    else:
        ap.print_help()
