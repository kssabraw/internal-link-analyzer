"""Read the internal-links data from a Website Auditor export.

Output DataFrame has guaranteed columns: `source_url`, `target_url`,
`anchor_text`, `link_type`. The URL columns are normalized to paths via
`engine.classifier.normalize_url`, so they collate with `PageClassification.raw_path`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from engine.classifier import normalize_url

# Per-column aliases tried in order. The Website Auditor "All pages (Links to
# page)" export uses "Linking Page" / "Linked URL" / "Anchor / Alt Text"; older
# / generic exports may use different headers.
_COLUMN_ALIASES: dict[str, list[str]] = {
    "source_url": ["Linking Page", "Source URL", "Source", "From URL", "source_url"],
    "target_url": ["Linked URL", "Target URL", "Target", "To URL", "target_url"],
    "anchor_text": [
        "Anchor / Alt Text",
        "Anchor Text",
        "Anchor",
        "Link text",
        "anchor_text",
    ],
    "link_type": ["Link Type", "Type", "Location", "link_type"],
}

# Website Auditor's "Found in" column flags the HTML element the link was
# discovered in. Only standard <a> links are page-to-page navigation; everything
# else (canonical tags, pagination, redirects, picture sources) is filtered out.
_FOUND_IN_KEEP = "<a>"


def read_links(input_dir: Path) -> pd.DataFrame:
    """Load `links.xlsx` or `links.csv` from `input_dir`.

    Returns a DataFrame with the contract columns. Both URL columns are
    normalized to paths (e.g. `/foo/bar`) and rows where either URL is empty
    or fails to normalize are dropped.
    """
    xlsx_path = input_dir / "links.xlsx"
    csv_path = input_dir / "links.csv"

    if xlsx_path.exists():
        raw = pd.read_excel(xlsx_path)
    elif csv_path.exists():
        raw = pd.read_csv(csv_path, low_memory=False)
    else:
        raise FileNotFoundError(
            f"No links.xlsx or links.csv found in {input_dir}"
        )

    if "Found in" in raw.columns:
        raw = raw[raw["Found in"] == _FOUND_IN_KEEP].copy()

    out = pd.DataFrame()
    for target_col, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in raw.columns:
                out[target_col] = raw[alias]
                break
        else:
            out[target_col] = None

    out = out.dropna(subset=["source_url", "target_url"]).copy()
    out["source_url"] = out["source_url"].astype(str).map(normalize_url)
    out["target_url"] = out["target_url"].astype(str).map(normalize_url)
    out["anchor_text"] = out["anchor_text"].fillna("").astype(str)

    return out.reset_index(drop=True)
