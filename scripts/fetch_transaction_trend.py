import os
import re
import sys

# Force UTF-8 output on Windows (cp1252 cannot encode CJK characters)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
import urllib3
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # headless — must be before pyplot import
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pytz
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROJECT_ROOT = os.getcwd()
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "csv")
SVG_DIR = os.path.join(PROJECT_ROOT, "data", "svg")

CSV_OUTPUT = os.path.join(DATA_DIR, "building_ownership_trend.csv")
SVG_OUTPUT = os.path.join(SVG_DIR, "building_ownership_trend.svg")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SVG_DIR, exist_ok=True)

# statis.moi.gov.tw API — funid c0510302 = 建物所有權登記 (quarterly)
# codspc0=0,50 → all areas (全國 total + all cities)
# codspc1=TYPE,1 → exactly 1 registration type
BASE_API = "https://statis.moi.gov.tw/micst/webMain.aspx"
FUNID = "c0510302"

# Registration type codes (codspc1 first value)
FETCH_TYPES = {"買賣": 3, "拍賣": 4, "繼承": 5, "贈與": 6, "夫妻贈與": 7}

# Target cities — must match statis.moi.gov.tw city labels exactly.
# Normalise 台→臺 so both writing styles work.
TARGET_CITIES = ["新北市", "臺北市", "桃園市", "新竹市", "新竹縣",
                 "苗栗縣", "臺中市", "臺南市", "高雄市"]

# Cities whose data in the API are already merged (post-reform).
# Old sub-labels like "臺中市(99年改制前)" should be skipped.
SKIP_SUFFIX = ("改制前", "臺北縣", "臺中縣", "臺南縣", "高雄縣",
               "桃園縣", "臺中市(99年")

# Align start quarter with existing housing_loan_default_rate.csv (ROC 98 Q1)
ALIGN_START = (98, 1)

# ── helpers ────────────────────────────────────────────────────────────────

def parse_quarter(q_str):
    m = re.match(r"(\d+)Q(\d+)", str(q_str))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def format_quarter_label(q_str):
    """ROC '098Q1' → Western '2009Q1' (matches existing chart labels)."""
    m = re.match(r"(\d+)Q(\d+)", str(q_str))
    if m:
        return f"{int(m.group(1)) + 1911}Q{m.group(2)}"
    return q_str


def normalise_city(name):
    """Unify 台/臺 variants."""
    return name.replace("台北", "臺北").replace("台中", "臺中") \
               .replace("台南", "臺南").replace("台東", "臺東")


def setup_font():
    cjk_fonts = [
        "Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Sans CJK SC",
        "Microsoft JhengHei", "Arial Unicode MS", "WenQuanYi Micro Hei",
        "TakaoPGothic", "sans-serif",
    ]
    for font_name in cjk_fonts:
        if any(font_name in f.name for f in fm.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [font_name, "sans-serif"]
            return
    plt.rcParams["font.sans-serif"] = ["sans-serif"]


# ── data fetch ─────────────────────────────────────────────────────────────

def _current_ym_end():
    """Return API ym parameter for 2 months ago to ensure data is published."""
    t = datetime.now(timezone.utc) - timedelta(days=60)
    roc_year = t.year - 1911
    return f"{roc_year}{t.month:02d}"


def _fetch_type_cities(type_code, ym_start="09801", ym_end=None):
    """Return {period: {city: (count, area)}} for all valid cities, one type."""
    if ym_end is None:
        ym_end = _current_ym_end()
    url = (
        f"{BASE_API}?sys=220&kind=21&type=1&funid={FUNID}"
        f"&cycle=2&outmode=12&utf=1&compmode=0&outkind=3&fldlst=111"
        f"&codspc0=0,50&codspc1={type_code},1"
        f"&rdm=py&ym={ym_start}&ymt={ym_end}"
    )
    r = requests.get(url, timeout=30, verify=False)
    text = r.content.decode("utf-8-sig", errors="replace")

    result = {}
    for line in text.strip().splitlines():
        # Skip lines that don't have area/city info
        if "/" not in line or "," not in line:
            continue
        # Skip old-name duplicates
        if any(s in line for s in SKIP_SUFFIX):
            continue

        parts = line.split(",")
        period_raw = parts[0].strip().strip('"').split("/")[0].strip()
        city_raw   = parts[0].strip().strip('"').split("/")[1].strip() \
                     if len(parts[0].split("/")) > 1 else ""
        city = normalise_city(city_raw)

        # Parse "X年 第Y季"
        m = re.match(r"(\d+)年\s+第(\d+)季", period_raw)
        if not m:
            continue
        roc_y, q = int(m.group(1)), int(m.group(2))
        key = f"{roc_y:03d}Q{q}" if roc_y < 100 else f"{roc_y}Q{q}"

        try:
            count = int(float(parts[1].strip().strip('"')))
            area  = float(parts[2].strip().strip('"')) if len(parts) > 2 else 0.0
        except (ValueError, TypeError):
            count = 0
            area  = 0.0

        result.setdefault(key, {})[city] = (count, area)

    return result


def download_data():
    print("從 statis.moi.gov.tw 下載建物所有權登記分類資料（主要城市）...")
    raw = {}
    for name, code in FETCH_TYPES.items():
        print(f"  下載 {name}（code={code}）...")
        raw[name] = _fetch_type_cities(code)

    # Union of all periods
    all_periods = sorted(
        set().union(*[d.keys() for d in raw.values()]),
        key=parse_quarter,
    )

    # Build flat CSV: period, city, 買賣, 拍賣, 繼承, 贈與
    rows = []
    for period in all_periods:
        # Collect all city names seen in this period
        cities_seen = set()
        for d in raw.values():
            if period in d:
                cities_seen |= d[period].keys()

        for city in sorted(cities_seen):
            rows.append({
                "period": period,
                "city":   city,
                "買賣_棟數":   raw["買賣"].get(period, {}).get(city, (0, 0))[0],
                "買賣_面積":   raw["買賣"].get(period, {}).get(city, (0, 0))[1],
                "拍賣_棟數":   raw["拍賣"].get(period, {}).get(city, (0, 0))[0],
                "拍賣_面積":   raw["拍賣"].get(period, {}).get(city, (0, 0))[1],
                "繼承_棟數":   raw["繼承"].get(period, {}).get(city, (0, 0))[0],
                "繼承_面積":   raw["繼承"].get(period, {}).get(city, (0, 0))[1],
                "贈與_棟數":   (raw["贈與"].get(period, {}).get(city, (0, 0))[0]
                               + raw["夫妻贈與"].get(period, {}).get(city, (0, 0))[0]),
                "贈與_面積":   (raw["贈與"].get(period, {}).get(city, (0, 0))[1]
                               + raw["夫妻贈與"].get(period, {}).get(city, (0, 0))[1]),
            })

    df = pd.DataFrame(rows)
    df.to_csv(CSV_OUTPUT, index=False, encoding="utf-8-sig")
    print(f"資料已儲存：{CSV_OUTPUT}（{len(df)} 行）")
    return True


# ── plot ───────────────────────────────────────────────────────────────────

STACK_COLORS = ["#2196F3", "#FF5722", "#4CAF50", "#FFC107"]
STACK_LABELS = ["買賣移轉", "拍賣", "繼承", "贈與（含夫妻）"]


def plot():
    print("繪製各城市堆疊面積圖...")
    df = pd.read_csv(CSV_OUTPUT, encoding="utf-8-sig")
    df["city"] = df["city"].map(normalise_city)

    # Filter target cities only
    df = df[df["city"].isin(TARGET_CITIES)].copy()
    df = df.sort_values("period", key=lambda s: s.map(parse_quarter))

    # Align start quarter with major_cities_default_rate.svg (098Q1)
    df = df[df["period"].map(lambda q: parse_quarter(q) >= ALIGN_START)]

    all_periods = sorted(df["period"].unique(), key=parse_quarter)
    n = len(all_periods)
    period_idx = {p: i for i, p in enumerate(all_periods)}

    setup_font()
    plt.rcParams["axes.unicode_minus"] = False

    # ── layout identical to fetch_and_plot.py ─────────────────────────────
    fig, axes = plt.subplots(
        nrows=len(TARGET_CITIES), ncols=1,
        sharex=True,
        figsize=(12, 3 * len(TARGET_CITIES)),
    )

    for i, city in enumerate(TARGET_CITIES):
        ax = axes[i]
        city_df = df[df["city"] == city].copy()
        city_df = city_df.sort_values("period", key=lambda s: s.map(parse_quarter))

        # Reindex to all_periods so gaps become 0
        city_df = city_df.set_index("period").reindex(all_periods, fill_value=0)

        x      = [period_idx[p] for p in all_periods]
        y_sale = city_df["買賣_棟數"].values   / 1_000
        y_auct = city_df["拍賣_棟數"].values   / 1_000
        y_inh  = city_df["繼承_棟數"].values   / 1_000
        y_gift = city_df["贈與_棟數"].values   / 1_000

        ax.stackplot(
            x, y_sale, y_auct, y_inh, y_gift,
            labels=STACK_LABELS,
            colors=STACK_COLORS,
            alpha=0.85,
        )

        ax.set_title(city, loc="left", fontsize=16, fontweight="bold")
        ax.set_ylabel("棟數（千棟）", fontsize=10)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.set_ylim(bottom=0)

        # Show legend only on first subplot
        if i == 0:
            ax.legend(loc="upper right", fontsize=10, ncol=4)

    # ── x-axis tick logic identical to fetch_and_plot.py ─────────────────
    if n > 20:
        step = max(1, n // 15)
        axes[-1].set_xticks(list(range(0, n, step)))
        axes[-1].set_xticklabels(
            [format_quarter_label(all_periods[j]) for j in range(0, n, step)],
            rotation=45, fontsize=12,
        )
    else:
        axes[-1].set_xticks(list(range(n)))
        axes[-1].set_xticklabels(
            [format_quarter_label(p) for p in all_periods],
            rotation=45, fontsize=12,
        )
    axes[-1].set_xlabel("Quarter", fontsize=12)

    fig.suptitle(
        "Quarterly Building Ownership Registration by Type — Major Cities\n"
        "（主要城市建物所有權登記棟數分類堆疊）",
        fontsize=18,
    )
    plt.tight_layout(rect=[0, 0.03, 1, 0.97])
    plt.savefig(SVG_OUTPUT, format="svg")
    print(f"圖表已輸出：{SVG_OUTPUT}")


# ── README timestamp ───────────────────────────────────────────────────────

def update_readme_timestamp():
    taipei_tz = pytz.timezone("Asia/Taipei")
    now = datetime.now(taipei_tz)
    timestamp_str = now.strftime("Update time: %Y-%m-%d %H:%M:%S CST")

    readme_path = "README.md"
    if not os.path.exists(readme_path):
        return

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    section_header = "### 資料視覺化- 建物所有權登記堆疊趨勢"
    image_prefix = "![建物所有權登記堆疊趨勢]"
    update_pattern = r"^Update time: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} CST$"

    lines = content.splitlines()
    section_start = next(
        (i for i, l in enumerate(lines) if l.strip() == section_header), None
    )
    if section_start is None:
        return

    section_end = next(
        (i for i in range(section_start + 1, len(lines)) if lines[i].startswith("### ")),
        len(lines),
    )

    section_lines = [l for l in lines[section_start:section_end]
                     if not re.match(update_pattern, l.strip())]

    image_index = next(
        (idx for idx, l in enumerate(section_lines) if l.strip().startswith(image_prefix)),
        None,
    )
    insert_at = image_index if image_index is not None else len(section_lines)
    while insert_at > 0 and section_lines[insert_at - 1].strip() == "":
        insert_at -= 1
    section_lines.insert(insert_at, "")
    section_lines.insert(insert_at, timestamp_str)

    # Deduplicate blank lines
    normalized, prev_blank = [], False
    for line in section_lines:
        cur_blank = line.strip() == ""
        if not (cur_blank and prev_blank):
            normalized.append(line)
        prev_blank = cur_blank

    merged = lines[:section_start] + normalized + lines[section_end:]
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("\n".join(merged).rstrip() + "\n")
    print(f"README 已更新：{timestamp_str}")


# ── main ───────────────────────────────────────────────────────────────────

def main():
    fresh = False
    try:
        fresh = download_data()
    except Exception as e:
        if not os.path.exists(CSV_OUTPUT):
            print(f"錯誤：無法下載且無既有資料：{e}")
            sys.exit(2)
        print(f"下載失敗，使用既有資料：{e}")

    try:
        plot()
    except Exception as e:
        print(f"繪圖失敗：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)

    if fresh:
        update_readme_timestamp()
    else:
        print("使用既有資料，不更新 README 時間戳。")

    sys.exit(0 if fresh else 1)


if __name__ == "__main__":
    main()
