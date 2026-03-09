"""Generate matplotlib charts for keyword coverage and ATS score dashboard."""

import os
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ..models import ATSScoreResponse, KeywordHeatmapData


# Professional color palette (emerald green and slate gray theme)
COLOR_PALETTE = {
    "primary": "#10b981",      # Emerald green
    "secondary": "#06b6d4",    # Cyan
    "accent": "#f59e0b",       # Amber
    "danger": "#ef4444",       # Red
    "slate_dark": "#1e293b",   # Dark slate
    "slate_light": "#cbd5e1",  # Light slate
    "bg": "#f8fafc",          # White/off-white
}


def _ensure_chart_dir() -> Path:
    path = Path(os.getenv("CHARTS_DIR", "backend/charts"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def chart_keyword_coverage(
    score_response: ATSScoreResponse,
    output_dir: Optional[Path] = None,
) -> str:
    """Bar chart: matched vs missing keyword counts. Returns path to saved figure."""
    base = output_dir or _ensure_chart_dir()
    base.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    missing_count = len(score_response.missing_keywords)
    pct = max(0.01, min(99.99, score_response.keyword_match_percent))
    # Infer matched from missing and percentage: missing = total * (1 - pct/100) => total = missing / (1 - pct/100)
    total = round(missing_count / (1 - pct / 100)) if pct < 100 else missing_count
    if total < 1:
        total = 1
    matched_count = max(0, total - missing_count)
    fig, ax = plt.subplots(figsize=(6, 4))
    colors = [COLOR_PALETTE["primary"], COLOR_PALETTE["danger"]]
    bars = ax.bar(["Matched", "Missing"], [matched_count, missing_count], color=colors, edgecolor=COLOR_PALETTE["slate_dark"], linewidth=1.5)
    ax.set_ylabel("Count", fontsize=11, color=COLOR_PALETTE["slate_dark"], fontweight="bold")
    ax.set_title("Keyword Coverage", fontsize=12, fontweight="bold", color=COLOR_PALETTE["slate_dark"], pad=16)
    ax.set_ylim(0, max(matched_count, missing_count) * 1.1)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_PALETTE["slate_light"])
    ax.spines["bottom"].set_color(COLOR_PALETTE["slate_light"])
    ax.tick_params(colors=COLOR_PALETTE["slate_dark"])
    for i, v in enumerate([matched_count, missing_count]):
        ax.text(i, v + 0.5, str(v), ha="center", fontsize=10, fontweight="bold", color=COLOR_PALETTE["slate_dark"])
    path = base / "keyword_coverage.png"
    fig.patch.set_facecolor(COLOR_PALETTE["bg"])
    ax.patch.set_facecolor(COLOR_PALETTE["bg"])
    fig.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor=COLOR_PALETTE["bg"])
    plt.close(fig)
    return str(path)


def chart_match_pie(score_response: ATSScoreResponse, output_dir: Optional[Path] = None) -> str:
    """Pie chart: match vs missing share."""
    base = output_dir or _ensure_chart_dir()
    base.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    match_pct = max(0, min(100, score_response.keyword_match_percent))
    missing_pct = 100 - match_pct
    fig, ax = plt.subplots(figsize=(5, 5))
    colors = [COLOR_PALETTE["primary"], COLOR_PALETTE["danger"]]
    wedges, texts, autotexts = ax.pie([match_pct, missing_pct], labels=["Match", "Missing"], autopct="%1.0f%%", colors=colors, startangle=90, textprops={"color": COLOR_PALETTE["slate_dark"], "fontweight": "bold"})
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontweight("bold")
        autotext.set_fontsize(10)
    for text in texts:
        text.set_color(COLOR_PALETTE["slate_dark"])
        text.set_fontweight("bold")
    ax.set_title("Match vs Missing", fontsize=12, fontweight="bold", color=COLOR_PALETTE["slate_dark"], pad=16)
    path = base / "match_pie.png"
    fig.patch.set_facecolor(COLOR_PALETTE["bg"])
    fig.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor=COLOR_PALETTE["bg"])
    plt.close(fig)
    return str(path)


def chart_top_missing(missing_keywords: list[str], output_dir: Optional[Path] = None) -> str:
    """Horizontal bar chart of top missing keywords."""
    base = output_dir or _ensure_chart_dir()
    base.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    top = (missing_keywords or [])[:15]
    if not top:
        top = ["(none)"]
    fig, ax = plt.subplots(figsize=(8, 5))
    y_pos = range(len(top))
    colors = [COLOR_PALETTE["danger"] if i < 5 else COLOR_PALETTE["accent"] for i in range(len(top))]
    ax.barh(y_pos, [1] * len(top), color=colors, edgecolor=COLOR_PALETTE["slate_dark"], linewidth=1)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(top, fontsize=9, color=COLOR_PALETTE["slate_dark"])
    ax.set_xlim(0, 1.5)
    ax.set_xticks([])
    ax.set_title("Top Missing Keywords / Skills", fontsize=12, fontweight="bold", color=COLOR_PALETTE["slate_dark"], pad=16)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_PALETTE["slate_light"])
    ax.spines["bottom"].set_color(COLOR_PALETTE["slate_light"])
    ax.invert_yaxis()
    path = base / "top_missing.png"
    fig.patch.set_facecolor(COLOR_PALETTE["bg"])
    ax.patch.set_facecolor(COLOR_PALETTE["bg"])
    fig.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor=COLOR_PALETTE["bg"])
    plt.close(fig)
    return str(path)


def chart_similarity_gauge(score_response: ATSScoreResponse, output_dir: Optional[Path] = None) -> str:
    """Gauge-style display of final ATS score (0–100)."""
    base = output_dir or _ensure_chart_dir()
    base.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    score = max(0, min(100, score_response.final_ats_score))
    
    # Color based on score - use professional palette
    if score >= 70:
        color = COLOR_PALETTE["primary"]
    elif score >= 50:
        color = COLOR_PALETTE["accent"]
    else:
        color = COLOR_PALETTE["danger"]
    
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.barh([0], [score], height=0.5, color=color, edgecolor=COLOR_PALETTE["slate_dark"], linewidth=2)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0", "25", "50", "75", "100"], color=COLOR_PALETTE["slate_dark"])
    ax.set_xlabel("ATS Score %", fontsize=11, color=COLOR_PALETTE["slate_dark"], fontweight="bold")
    ax.set_title(f"Final ATS Score: {score:.0f}%", fontsize=12, fontweight="bold", color=COLOR_PALETTE["slate_dark"], pad=16)
    ax.set_yticks([])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_PALETTE["slate_light"])
    # Add score label on bar
    ax.text(score / 2, 0, f"{score:.0f}%", ha="center", va="center", fontsize=14, fontweight="bold", color="white")
    path = base / "similarity_gauge.png"
    fig.patch.set_facecolor(COLOR_PALETTE["bg"])
    ax.patch.set_facecolor(COLOR_PALETTE["bg"])
    fig.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor=COLOR_PALETTE["bg"])
    plt.close(fig)
    return str(path)


def chart_keyword_heatmap(
    heatmap_data: KeywordHeatmapData,
    output_dir: Optional[Path] = None,
) -> str:
    """Heatmap visualization of keyword frequencies."""
    base = output_dir or _ensure_chart_dir()
    base.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    
    if not heatmap_data.keywords:
        # Return empty chart if no data
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No keyword data", ha="center", va="center", fontsize=12, color=COLOR_PALETTE["slate_dark"])
        ax.axis("off")
        path = base / "keyword_heatmap.png"
        fig.patch.set_facecolor(COLOR_PALETTE["bg"])
        fig.tight_layout()
        fig.savefig(path, dpi=100, bbox_inches="tight", facecolor=COLOR_PALETTE["bg"])
        plt.close(fig)
        return str(path)
    
    fig, ax = plt.subplots(figsize=(10, len(heatmap_data.keywords) * 0.3 + 2))
    
    # Create color map based on importance scores - use professional palette
    colors = [COLOR_PALETTE["primary"] if importance >= 0.7 else COLOR_PALETTE["accent"] if importance >= 0.4 else COLOR_PALETTE["secondary"] 
              for importance in heatmap_data.importance_scores]
    
    y_pos = range(len(heatmap_data.keywords))
    bars = ax.barh(y_pos, heatmap_data.frequencies, color=colors, edgecolor=COLOR_PALETTE["slate_dark"], linewidth=0.5)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(heatmap_data.keywords, fontsize=10, color=COLOR_PALETTE["slate_dark"])
    ax.set_xlabel("Frequency in Resume", fontsize=11, color=COLOR_PALETTE["slate_dark"], fontweight="bold")
    ax.set_title("Keyword Heatmap - Importance & Frequency", fontsize=12, fontweight="bold", color=COLOR_PALETTE["slate_dark"], pad=16)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_PALETTE["slate_light"])
    ax.spines["bottom"].set_color(COLOR_PALETTE["slate_light"])
    ax.tick_params(colors=COLOR_PALETTE["slate_dark"])
    ax.invert_yaxis()
    
    # Add frequency labels
    for i, (bar, freq) in enumerate(zip(bars, heatmap_data.frequencies)):
        if freq > 0:
            ax.text(freq + 0.1, bar.get_y() + bar.get_height()/2, str(freq), va="center", fontsize=9, fontweight="bold", color=COLOR_PALETTE["slate_dark"])
    
    path = base / "keyword_heatmap.png"
    fig.patch.set_facecolor(COLOR_PALETTE["bg"])
    ax.patch.set_facecolor(COLOR_PALETTE["bg"])
    fig.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor=COLOR_PALETTE["bg"])
    plt.close(fig)
    return str(path)


def chart_skill_gap(
    matched: int,
    missing: int,
    output_dir: Optional[Path] = None,
) -> str:
    """Donut chart for skill gap. Returns placeholder if data is unavailable."""
    base = output_dir or _ensure_chart_dir()
    base.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    
    # Safety check: if both values are zero, generate placeholder
    if matched == 0 and missing == 0:
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.text(
            0.5, 0.5,
            "No Skill Data Available",
            ha="center",
            va="center",
            fontsize=14,
            fontweight="bold",
            color=COLOR_PALETTE["slate_dark"]
        )
        ax.axis("off")
        ax.set_title("Skill Gap Analysis", fontsize=12, fontweight="bold", color=COLOR_PALETTE["slate_dark"], pad=16)
        path = base / "skill_gap.png"
        fig.patch.set_facecolor(COLOR_PALETTE["bg"])
        fig.tight_layout()
        fig.savefig(path, dpi=100, bbox_inches="tight", facecolor=COLOR_PALETTE["bg"])
        plt.close(fig)
        return str(path)
    
    fig, ax = plt.subplots(figsize=(5, 5))
    
    colors = [COLOR_PALETTE["primary"], COLOR_PALETTE["danger"]]
    wedges, texts, autotexts = ax.pie(
        [matched, missing],
        labels=["Matched", "Missing"],
        autopct="%1.0f%%",
        colors=colors,
        startangle=90,
        counterclock=False,
        textprops={"color": COLOR_PALETTE["slate_dark"], "fontweight": "bold"}
    )
    
    # Draw circle for donut
    centre_circle = plt.Circle((0, 0), 0.70, fc=COLOR_PALETTE["bg"])
    ax.add_artist(centre_circle)
    
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontweight("bold")
        autotext.set_fontsize(10)
    
    for text in texts:
        text.set_color(COLOR_PALETTE["slate_dark"])
    
    ax.set_title("Skill Gap Analysis", fontsize=12, fontweight="bold", color=COLOR_PALETTE["slate_dark"], pad=16)
    path = base / "skill_gap.png"
    fig.patch.set_facecolor(COLOR_PALETTE["bg"])
    fig.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor=COLOR_PALETTE["bg"])
    plt.close(fig)
    return str(path)


def chart_quality_breakdown(
    readability: float,
    formatting: float,
    content: float,
    keyword_density: float,
    output_dir: Optional[Path] = None,
) -> str:
    """Radar/bar chart for resume quality breakdown. Returns placeholder if all scores are zero."""
    base = output_dir or _ensure_chart_dir()
    base.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    
    categories = ["Readability", "Formatting", "Content", "Keywords"]
    scores = [readability, formatting, content, keyword_density]
    
    # Safety check: if all scores are zero, generate placeholder
    if all(s == 0 for s in scores):
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.text(
            0.5, 0.5,
            "No Quality Data Available",
            ha="center",
            va="center",
            fontsize=14,
            fontweight="bold",
            color=COLOR_PALETTE["slate_dark"]
        )
        ax.axis("off")
        ax.set_title("Resume Quality Breakdown", fontsize=12, fontweight="bold", color=COLOR_PALETTE["slate_dark"], pad=16)
        path = base / "quality_breakdown.png"
        fig.patch.set_facecolor(COLOR_PALETTE["bg"])
        fig.tight_layout()
        fig.savefig(path, dpi=100, bbox_inches="tight", facecolor=COLOR_PALETTE["bg"])
        plt.close(fig)
        return str(path)
    
    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(categories))
    colors = [COLOR_PALETTE["primary"] if s >= 70 else COLOR_PALETTE["accent"] if s >= 50 else COLOR_PALETTE["danger"] for s in scores]
    bars = ax.bar(x, scores, color=colors, edgecolor=COLOR_PALETTE["slate_dark"], linewidth=1.5)
    
    ax.set_ylabel("Score", fontsize=11, color=COLOR_PALETTE["slate_dark"], fontweight="bold")
    ax.set_title("Resume Quality Breakdown", fontsize=12, fontweight="bold", color=COLOR_PALETTE["slate_dark"], pad=16)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10, color=COLOR_PALETTE["slate_dark"])
    ax.set_ylim(0, 100)
    ax.axhline(y=70, color=COLOR_PALETTE["primary"], linestyle="--", alpha=0.4, linewidth=2, label="Good (70%)")
    ax.axhline(y=50, color=COLOR_PALETTE["accent"], linestyle="--", alpha=0.4, linewidth=2, label="Fair (50%)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_PALETTE["slate_light"])
    ax.spines["bottom"].set_color(COLOR_PALETTE["slate_light"])
    ax.tick_params(colors=COLOR_PALETTE["slate_dark"])
    ax.legend(fontsize=9, loc="upper right", facecolor=COLOR_PALETTE["bg"], edgecolor=COLOR_PALETTE["slate_light"])
    
    # Add score labels
    for bar, score in zip(bars, scores):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 1, f"{score:.0f}", ha="center", va="bottom", fontsize=10, fontweight="bold", color=COLOR_PALETTE["slate_dark"])
    
    path = base / "quality_breakdown.png"
    fig.patch.set_facecolor(COLOR_PALETTE["bg"])
    ax.patch.set_facecolor(COLOR_PALETTE["bg"])
    fig.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor=COLOR_PALETTE["bg"])
    plt.close(fig)
    return str(path)


def generate_all_charts(
    score_response: ATSScoreResponse,
    output_dir: Optional[Path] = None,
) -> dict[str, str]:
    """Generate all dashboard charts and return map of name -> file path."""
    base = output_dir or _ensure_chart_dir()
    paths = {}
    paths["keyword_coverage"] = chart_keyword_coverage(score_response, base)
    paths["match_pie"] = chart_match_pie(score_response, base)
    paths["top_missing"] = chart_top_missing(score_response.missing_keywords, base)
    paths["similarity_gauge"] = chart_similarity_gauge(score_response, base)
    return paths
