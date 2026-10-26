"""Fitch-styled regulatory filing extractor (mock mode — no LLM calls)."""
import html
import io
import json
import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from mock_data import PROFILES, TEMPLATES, extract

try:
    from pypdf import PdfReader
except ImportError:  # page count is optional
    PdfReader = None

st.set_page_config(
    page_title="Fitch Ratings | Regulatory Filing Extractor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Institutional Fitch Ratings-inspired color tokens for Dark & Light modes
THEMES = {
    "dark": dict(
        bg="#0B0F17",
        surface="#111827",
        surface2="#1A2333",
        surface3="#232F46",
        border="#26334D",
        border_strong="#36496E",
        text="#F8FAFC",
        text_sec="#CBD5E1",
        muted="#8B9BB4",
        accent="#3B82F6",
        accent_soft="rgba(59, 130, 246, 0.14)",
        accent_border="rgba(59, 130, 246, 0.38)",
        on_accent="#FFFFFF",
        header="#070B12",
        table_head="#0F172A",
        table_sub="#162033",
        good="#10B981",
        good_bg="rgba(16, 185, 129, 0.12)",
        good_border="rgba(16, 185, 129, 0.35)",
        warn="#F59E0B",
        warn_bg="rgba(245, 158, 11, 0.14)",
        warn_border="rgba(245, 158, 11, 0.38)",
        hover="#1E293B",
        shadow="0 4px 20px rgba(0, 0, 0, 0.35)",
        chart_tot="#93C5FD",
    ),
    "light": dict(
        bg="#F4F6FA",
        surface="#FFFFFF",
        surface2="#F1F5F9",
        surface3="#E2E8F0",
        border="#E2E8F0",
        border_strong="#CBD5E1",
        text="#0F172A",
        text_sec="#334155",
        muted="#64748B",
        accent="#1D4ED8",
        accent_soft="rgba(29, 78, 216, 0.08)",
        accent_border="rgba(29, 78, 216, 0.28)",
        on_accent="#FFFFFF",
        header="#0F172A",
        table_head="#1E293B",
        table_sub="#F1F5F9",
        good="#059669",
        good_bg="rgba(5, 150, 105, 0.08)",
        good_border="rgba(5, 150, 105, 0.28)",
        warn="#D97706",
        warn_bg="rgba(217, 119, 6, 0.10)",
        warn_border="rgba(217, 119, 6, 0.32)",
        hover="#F8FAFC",
        shadow="0 2px 10px rgba(15, 23, 42, 0.05)",
        chart_tot="#1E3A8A",
    ),
}
SERIES = [
    "#2563EB",
    "#0EA5E9",
    "#0D9488",
    "#6366F1",
    "#F59E0B",
    "#10B981",
    "#8B5CF6",
    "#EC4899",
    "#64748B",
]

# ---------------------------------------------------------------- state / theme
st.session_state.setdefault("results", {})
st.session_state.setdefault("dark", True)
T = THEMES["dark" if st.session_state.dark else "light"]


def inject_css(t):
    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Libre+Baskerville:wght@700&display=swap');

    :root {{
        --bg: {t['bg']};
        --surface: {t['surface']};
        --surface2: {t['surface2']};
        --surface3: {t['surface3']};
        --border: {t['border']};
        --border-strong: {t['border_strong']};
        --text: {t['text']};
        --text-sec: {t['text_sec']};
        --muted: {t['muted']};
        --accent: {t['accent']};
        --accent-soft: {t['accent_soft']};
        --accent-border: {t['accent_border']};
        --on-accent: {t['on_accent']};
        --header: {t['header']};
        --table-head: {t['table_head']};
        --table-sub: {t['table_sub']};
        --good: {t['good']};
        --good-bg: {t['good_bg']};
        --good-border: {t['good_border']};
        --warn: {t['warn']};
        --warn-bg: {t['warn_bg']};
        --warn-border: {t['warn_border']};
        --hover: {t['hover']};
        --shadow: {t['shadow']};
    }}

    /* Core App & Typography */
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
        background: var(--bg) !important;
        color: var(--text) !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }}
    [data-testid="stHeader"] {{
        background: transparent !important;
    }}
    [data-testid="stSidebar"] {{
        background: var(--surface) !important;
        border-right: 1px solid var(--border) !important;
    }}
    [data-testid="stSidebar"] .block-container {{
        padding-top: 1.5rem !important;
    }}
    [data-testid="stMain"] .block-container {{
        padding-top: 3.75rem !important;
        padding-bottom: 3rem !important;
        max-width: 1480px !important;
    }}

    /* Text & Widget Label Harmonization */
    .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
    [data-testid="stWidgetLabel"] *, [data-testid="stMarkdownContainer"] {{
        color: var(--text);
    }}
    [data-testid="stCaptionContainer"] *, .stCaption {{
        color: var(--muted) !important;
        font-size: 0.8rem !important;
    }}

    /* File Uploader */
    [data-testid="stFileUploaderDropzone"] {{
        background: var(--surface2) !important;
        border: 1.5px dashed var(--border-strong) !important;
        border-radius: 8px !important;
        padding: 1rem !important;
        transition: all 0.15s ease;
    }}
    [data-testid="stFileUploaderDropzone"]:hover {{
        border-color: var(--accent) !important;
        background: var(--accent-soft) !important;
    }}
    [data-testid="stFileUploaderDropzone"] * {{
        color: var(--muted) !important;
    }}
    [data-testid="stFileUploaderFile"] * {{
        color: var(--text) !important;
    }}

    /* Buttons */
    .stButton > button, .stDownloadButton > button, [data-testid="stFileUploaderDropzone"] button {{
        background: var(--surface2) !important;
        color: var(--text) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 0.84rem !important;
        padding: 0.45rem 0.9rem !important;
        transition: all 0.15s ease !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
        width: 100%;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stFileUploaderDropzone"] button:hover {{
        border-color: var(--accent) !important;
        color: var(--accent) !important;
        background: var(--accent-soft) !important;
    }}
    .stButton > button p, .stDownloadButton > button p {{
        color: inherit !important;
        font-weight: 600 !important;
    }}
    .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, var(--accent), #1D4ED8) !important;
        color: var(--on-accent) !important;
        border: 1px solid transparent !important;
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.28) !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        color: var(--on-accent) !important;
        filter: brightness(1.08);
        transform: translateY(-1px);
    }}
    .stButton > button[kind="primary"]:disabled {{
        background: var(--surface3) !important;
        color: var(--muted) !important;
        box-shadow: none !important;
        border: 1px solid var(--border) !important;
        opacity: 0.65;
    }}
    .stButton > button[kind="primary"] p {{
        color: var(--on-accent) !important;
    }}

    /* Selectboxes, Multiselects, Inputs, Expanders */
    div[data-baseweb="select"] > div {{
        background: var(--surface2) !important;
        border-color: var(--border-strong) !important;
        border-radius: 6px !important;
    }}
    div[data-baseweb="select"] * {{
        color: var(--text) !important;
    }}
    [data-baseweb="popover"] ul, [data-baseweb="popover"] li {{
        background: var(--surface) !important;
        color: var(--text) !important;
    }}
    [data-baseweb="tag"] {{
        background: var(--accent-soft) !important;
        border: 1px solid var(--accent-border) !important;
        border-radius: 4px !important;
    }}

    /* Toggle Switch & Checkbox Controls (Streamlit 1.40+ react-aria & legacy BaseWeb) */
    /* 1. Toggle switch track (unchecked) */
    [data-testid="stCheckbox"] .react-aria-SwitchButton > div:first-of-type,
    [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > div:first-child {{
        background-color: var(--border-strong) !important;
        border: 1.5px solid var(--muted) !important;
        box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.18) !important;
        transition: all 0.18s ease !important;
    }}
    /* 2. Toggle switch track (checked) */
    [data-testid="stCheckbox"] .react-aria-SwitchButton[data-selected] > div:first-of-type,
    [data-testid="stCheckbox"] .react-aria-SwitchButton:has(input:checked) > div:first-of-type,
    [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > div:first-child {{
        background-color: var(--accent) !important;
        border-color: var(--accent) !important;
    }}
    /* 3. Toggle switch thumb (inner circle) */
    [data-testid="stCheckbox"] .react-aria-SwitchButton > div:first-of-type > div,
    [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > div:first-child > div {{
        background-color: #FFFFFF !important;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.45) !important;
    }}
    /* 4. Standard checkbox box (unchecked & checked) */
    [data-testid="stCheckbox"] .react-aria-CheckboxButton > div:first-of-type,
    [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > span:first-child {{
        background-color: var(--surface2) !important;
        border: 1.5px solid var(--muted) !important;
    }}
    [data-testid="stCheckbox"] .react-aria-CheckboxButton[data-selected] > div:first-of-type,
    [data-testid="stCheckbox"] .react-aria-CheckboxButton:has(input:checked) > div:first-of-type,
    [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > span:first-child {{
        background-color: var(--accent) !important;
        border-color: var(--accent) !important;
    }}
    [data-testid="stCheckbox"] .react-aria-CheckboxButton svg polyline {{
        stroke: #FFFFFF !important;
    }}

    /* Sidebar Collapse & Expand Toggle Buttons + Top Toolbar Buttons */
    [data-testid="stSidebarCollapseButton"] button,
    [data-testid="stExpandSidebarButton"],
    [data-testid="stMainMenuButton"],
    [data-testid="stAppDeployButton"] button {{
        background-color: var(--surface2) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 6px !important;
        color: var(--text) !important;
        opacity: 1 !important;
        visibility: visible !important;
        transition: all 0.15s ease !important;
    }}
    [data-testid="stSidebarCollapseButton"] button:hover,
    [data-testid="stExpandSidebarButton"]:hover,
    [data-testid="stMainMenuButton"]:hover,
    [data-testid="stAppDeployButton"] button:hover {{
        background-color: var(--accent-soft) !important;
        border-color: var(--accent) !important;
        color: var(--accent) !important;
    }}
    [data-testid="stSidebarCollapseButton"] button span,
    [data-testid="stExpandSidebarButton"] span,
    [data-testid="stAppDeployButton"] button span {{
        color: var(--text) !important;
    }}
    [data-testid="stSidebarCollapseButton"] button svg,
    [data-testid="stExpandSidebarButton"] svg,
    [data-testid="stMainMenuButton"] svg {{
        color: var(--text) !important;
        fill: currentColor !important;
    }}
    [data-testid="stSidebarCollapseButton"] {{
        opacity: 1 !important;
        visibility: visible !important;
    }}
    [data-testid="stExpander"] details {{
        background: var(--surface2) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
    }}
    [data-testid="stExpander"] summary * {{
        color: var(--text) !important;
        font-weight: 600 !important;
    }}

    /* Tabs */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {{
        gap: 6px !important;
        background: var(--surface) !important;
        padding: 6px 8px !important;
        border-radius: 8px !important;
        border: 1px solid var(--border) !important;
        margin-bottom: 14px !important;
    }}
    button[data-baseweb="tab"] {{
        border-radius: 6px !important;
        padding: 8px 16px !important;
        background: transparent !important;
        border: none !important;
        transition: all 0.15s ease !important;
    }}
    button[data-baseweb="tab"]:hover {{
        background: var(--surface2) !important;
    }}
    button[data-baseweb="tab"] p {{
        color: var(--muted) !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        background: var(--accent-soft) !important;
        border: 1px solid var(--accent-border) !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] p {{
        color: var(--accent) !important;
        font-weight: 700 !important;
    }}
    [data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {{
        display: none !important;
    }}

    /* Plotly Chart Wrapper */
    [data-testid="stPlotlyChart"] {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 10px 12px 4px 12px;
        box-shadow: var(--shadow);
    }}

    /* Top Brand Bar */
    .fx-header {{
        background: linear-gradient(90deg, #070B12 0%, #0F172A 65%, #172554 100%);
        border: 1px solid #1E293B;
        border-bottom: 3px solid var(--accent);
        border-radius: 10px;
        padding: 16px 24px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 20px;
        margin-bottom: 20px;
        box-shadow: var(--shadow);
    }}
    .fx-brand-group {{
        display: flex;
        align-items: center;
        gap: 20px;
    }}
    .fx-word {{
        font-family: 'Libre Baskerville', Georgia, 'Times New Roman', serif;
        font-weight: 700;
        font-size: 26px;
        line-height: 1;
        color: #FFFFFF;
        letter-spacing: -0.4px;
    }}
    .fx-sub {{
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        font-size: 10px;
        color: #60A5FA;
        letter-spacing: 2.4px;
        text-transform: uppercase;
        margin-left: 8px;
    }}
    .fx-title {{
        font-size: 15px;
        font-weight: 600;
        color: #E2E8F0;
        border-left: 1px solid #334155;
        padding-left: 20px;
        display: flex;
        flex-direction: column;
    }}
    .fx-title span {{
        font-size: 11px;
        font-weight: 400;
        color: #94A3B8;
        margin-top: 2px;
    }}
    .fx-badges {{
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .fx-pill-frame {{
        font-size: 11px;
        font-weight: 600;
        color: #93C5FD;
        background: rgba(59, 130, 246, 0.16);
        border: 1px solid rgba(96, 165, 250, 0.35);
        padding: 5px 12px;
        border-radius: 999px;
        letter-spacing: 0.4px;
    }}
    .fx-pill {{
        font-size: 11px;
        font-weight: 700;
        color: #FBBF24;
        background: rgba(245, 158, 11, 0.15);
        border: 1px solid rgba(245, 158, 11, 0.4);
        padding: 5px 12px;
        border-radius: 999px;
        letter-spacing: 0.5px;
    }}

    /* Sidebar Section Headers */
    .fx-side-hdr {{
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.1px;
        color: var(--muted);
        margin: 14px 0 8px 0;
        display: flex;
        align-items: center;
        gap: 6px;
    }}
    .fx-side-box {{
        background: var(--surface2);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 12px 14px;
        margin-top: 12px;
        font-size: 12px;
        color: var(--muted);
        line-height: 1.5;
    }}

    /* Entity Banner & Metadata Grid */
    .fx-entity-banner {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-left: 4px solid var(--accent);
        border-radius: 10px;
        padding: 18px 22px;
        margin-bottom: 18px;
        box-shadow: var(--shadow);
    }}
    .fx-entity-top {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 16px;
        flex-wrap: wrap;
        margin-bottom: 14px;
    }}
    .fx-entity-name {{
        font-size: 21px;
        font-weight: 700;
        color: var(--text);
        letter-spacing: -0.3px;
        margin: 0;
    }}
    .fx-entity-report {{
        font-size: 13px;
        color: var(--muted);
        margin-top: 3px;
    }}
    .fx-status-badge {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        font-weight: 600;
        color: var(--good);
        background: var(--good-bg);
        border: 1px solid var(--good-border);
        padding: 5px 12px;
        border-radius: 999px;
    }}
    .fx-meta-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 10px;
        padding-top: 14px;
        border-top: 1px solid var(--border);
    }}
    .fx-meta-item {{
        background: var(--surface2);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 8px 12px;
    }}
    .fx-meta-lbl {{
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.7px;
        color: var(--muted);
    }}
    .fx-meta-val {{
        font-size: 13px;
        font-weight: 600;
        color: var(--text);
        margin-top: 2px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}

    /* Executive KPI Cards */
    .fx-kpi {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-top: 3px solid var(--accent);
        border-radius: 8px;
        padding: 15px 18px;
        height: 100%;
        box-shadow: var(--shadow);
        transition: transform 0.15s ease, border-color 0.15s ease;
    }}
    .fx-kpi:hover {{
        transform: translateY(-2px);
        border-color: var(--accent-border);
        border-top-color: var(--accent);
    }}
    .fx-kpi.ratio {{
        border-top-color: var(--good);
    }}
    .fx-kpi .l {{
        color: var(--muted);
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }}
    .fx-kpi .v {{
        color: var(--text);
        font-size: 25px;
        font-weight: 700;
        margin-top: 6px;
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.4px;
    }}
    .fx-kpi.ratio .v {{
        color: var(--good);
    }}
    .fx-kpi .s {{
        color: var(--muted);
        font-size: 12px;
        margin-top: 4px;
    }}

    /* Validation Checks Strip */
    .fx-checks-bar {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 12px 16px;
        margin: 14px 0 18px 0;
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
    }}
    .fx-checks-label {{
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        color: var(--muted);
        margin-right: 6px;
    }}
    .fx-chip {{
        display: inline-flex;
        align-items: center;
        gap: 5px;
        font-size: 12px;
        font-weight: 500;
        padding: 4px 11px;
        border-radius: 999px;
        border: 1px solid var(--border-strong);
        background: var(--surface2);
        color: var(--text-sec);
    }}
    .fx-chip.ok {{
        background: var(--good-bg);
        border-color: var(--good-border);
        color: var(--text);
    }}
    .fx-chip.ok::before {{
        content: '✓';
        font-weight: 800;
        color: var(--good);
    }}

    /* Template Section Header */
    .fx-sec-hdr {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 10px;
        margin: 4px 0 12px 0;
        padding-bottom: 10px;
        border-bottom: 1px solid var(--border);
    }}
    .fx-sec-title {{
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .fx-code-badge {{
        font-family: 'JetBrains Mono', Consolas, monospace;
        font-size: 12px;
        font-weight: 600;
        color: var(--accent);
        background: var(--accent-soft);
        border: 1px solid var(--accent-border);
        padding: 3px 9px;
        border-radius: 5px;
    }}
    .fx-sec-name {{
        font-size: 17px;
        font-weight: 700;
        color: var(--text);
    }}
    .fx-sec-unit {{
        font-size: 12px;
        font-weight: 500;
        color: var(--muted);
        background: var(--surface2);
        border: 1px solid var(--border);
        padding: 3px 10px;
        border-radius: 6px;
    }}

    /* Financial Data Tables */
    .fx-table-wrap {{
        overflow: auto;
        max-height: 540px;
        border: 1px solid var(--border);
        border-radius: 8px;
        background: var(--surface);
        box-shadow: var(--shadow);
        margin-bottom: 16px;
    }}
    table.fx-table {{
        border-collapse: separate;
        border-spacing: 0;
        width: 100%;
        font-size: 13px;
    }}
    .fx-table th {{
        position: sticky;
        top: 0;
        background: var(--table-head);
        color: #F8FAFC;
        text-align: left;
        padding: 10px 14px;
        font-weight: 600;
        font-size: 11.5px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        white-space: nowrap;
        z-index: 2;
        border-bottom: 2px solid var(--accent);
    }}
    .fx-table td {{
        padding: 8px 14px;
        border-bottom: 1px solid var(--border);
        color: var(--text);
        white-space: nowrap;
    }}
    .fx-table th.num, .fx-table td.num {{
        text-align: right;
        font-family: 'JetBrains Mono', Consolas, monospace;
        font-size: 12.5px;
        font-variant-numeric: tabular-nums;
    }}
    .fx-table td.ref {{
        color: var(--muted);
        font-family: 'JetBrains Mono', Consolas, monospace;
        font-size: 11.5px;
    }}
    .fx-table tbody tr:hover td {{
        background: var(--hover);
    }}
    .fx-table tr.sec td {{
        font-weight: 700;
        font-size: 11.5px;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        color: var(--accent);
        background: var(--table-sub);
        padding-top: 10px;
        padding-bottom: 8px;
    }}
    .fx-table tr.b td {{
        font-weight: 700;
        background: var(--surface2);
        border-top: 1px solid var(--border-strong);
        border-bottom: 2px solid var(--border-strong);
    }}
    .fx-table tr.low td {{
        background: var(--warn-bg);
    }}
    .fx-conf-pill {{
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-family: 'JetBrains Mono', Consolas, monospace;
        font-size: 11.5px;
        font-weight: 600;
    }}
    .fx-conf-ok {{
        background: var(--good-bg);
        color: var(--good);
        border: 1px solid var(--good-border);
    }}
    .fx-conf-low {{
        background: var(--warn-bg);
        color: var(--warn);
        border: 1px solid var(--warn-border);
    }}

    /* Onboarding / Empty State Cards */
    .fx-hero {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 28px 30px;
        box-shadow: var(--shadow);
        margin-bottom: 20px;
    }}
    .fx-hero-title {{
        font-size: 22px;
        font-weight: 700;
        color: var(--text);
        margin: 0 0 8px 0;
        letter-spacing: -0.3px;
    }}
    .fx-hero-sub {{
        font-size: 14px;
        color: var(--muted);
        max-width: 820px;
        line-height: 1.6;
        margin-bottom: 18px;
    }}
    .fx-tpl-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 10px;
        margin-top: 12px;
    }}
    .fx-tpl-card {{
        background: var(--surface2);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 10px 14px;
    }}
    .fx-tpl-card .c {{
        font-family: 'JetBrains Mono', Consolas, monospace;
        font-size: 12px;
        font-weight: 600;
        color: var(--accent);
    }}
    .fx-tpl-card .n {{
        font-size: 12.5px;
        font-weight: 500;
        color: var(--text);
        margin-top: 3px;
    }}
    .fx-demo-card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-top: 3px solid var(--accent);
        border-radius: 8px;
        padding: 16px 18px;
        margin-bottom: 10px;
        box-shadow: var(--shadow);
    }}
    .fx-demo-tag {{
        font-size: 10.5px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.7px;
        color: var(--accent);
    }}
    .fx-demo-name {{
        font-size: 15px;
        font-weight: 700;
        color: var(--text);
        margin: 4px 0 6px 0;
    }}
    .fx-demo-meta {{
        font-size: 12px;
        color: var(--muted);
        line-height: 1.5;
    }}
    </style>"""
    st.markdown(css, unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers
def short_money(v, unit):
    m = {"m": v, "k": v / 1e3, "u": v / 1e6}[unit]
    return f"{m / 1000:,.1f}bn" if abs(m) >= 1000 else f"{m:,.0f}m"


def html_table(df, fmt=None, note_rows=500):
    fmt = fmt or {}
    cols = [c for c in df.columns if not c.startswith("_")]
    numeric = {c: pd.api.types.is_numeric_dtype(df[c]) and c not in fmt for c in cols}
    head = "".join(
        f"<th class='{'num' if numeric[c] or c in fmt else ''}'>{html.escape(str(c))}</th>"
        for c in cols
    )
    body = []
    for _, r in df.head(note_rows).iterrows():
        is_bold = bool(r.get("_bold", False))
        is_low = bool(r.get("_low", False))
        # Detect section divider rows (bold row where all numeric columns are NaN)
        num_cols = [c for c in cols if numeric[c]]
        is_section = is_bold and bool(num_cols) and all(pd.isna(r[c]) for c in num_cols)
        if is_section:
            cls = "sec"
        else:
            cls = " ".join(k for k, f in (("b", is_bold), ("low", is_low)) if f)
        tds = []
        for c in cols:
            v = r[c]
            if c in fmt:
                s, k = fmt[c](v, r), "num"
            elif numeric[c]:
                s, k = ("" if is_section else "—" if pd.isna(v) else f"{v:,.0f}"), "num"
            else:
                s = html.escape("" if pd.isna(v) else str(v))
                k = "ref" if c in ("Ref", "Row ref") else ""
            tds.append(f"<td class='{k}'>{s}</td>")
        body.append(f"<tr class='{cls}'>{''.join(tds)}</tr>")
    st.markdown(
        f"<div class='fx-table-wrap'><table class='fx-table'><thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    if len(df) > note_rows:
        st.caption(f"Showing first {note_rows:,} of {len(df):,} rows — use the downloads below for the full dataset.")


def style_fig(fig, height=370):
    fig.update_layout(
        height=height,
        margin=dict(l=16, r=16, t=46, b=16),
        colorway=SERIES,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=T["text"], family="Inter, Segoe UI, Arial, sans-serif", size=12),
        title=dict(font=dict(size=14, color=T["text"]), x=0.01),
        legend=dict(font=dict(size=11, color=T["text_sec"]), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=T["surface2"], font_size=12, font_family="Inter, sans-serif"),
    )
    fig.update_xaxes(gridcolor=T["border"], zerolinecolor=T["border"], tickfont=dict(color=T["muted"]))
    fig.update_yaxes(gridcolor=T["border"], zerolinecolor=T["border"], tickfont=dict(color=T["text_sec"]))
    return fig


def kpi(label, value, sub="", variant=""):
    cls = f"fx-kpi {variant}".strip()
    return f"<div class='{cls}'><div class='l'>{label}</div><div class='v'>{value}</div><div class='s'>{sub}</div></div>"


def page_count(uploaded):
    if PdfReader is None:
        return None
    try:
        return len(PdfReader(io.BytesIO(uploaded.getvalue())).pages)
    except Exception:
        return None


def run_extraction(items):
    steps = [
        "Parsing PDF structure and detecting tabular regions",
        "Locating Solvency II / PRA QRT templates (S.02.01, S.05.01, S.05.02, S.19.01, S.25)",
        "Extracting cell values & row/column coordinates (mock)",
        "Running cross-template reconciliation & accounting checks",
    ]
    with st.status("Running regulatory filing extraction…", expanded=True) as status:
        for name, pages in items:
            st.write(f"**{name}**")
            for s in steps:
                st.write(f"• {s}")
                time.sleep(0.3)
            res = extract(name, pages)
            res["meta"].update(file=name, extracted_at=datetime.now().strftime("%d %b %Y %H:%M"))
            st.session_state.results[name] = res
            st.session_state.active = name
        status.update(label="Extraction complete", state="complete", expanded=False)


# ---------------------------------------------------------------- charts
def donut(df, group, title):
    d = df[(df["_group"] == group) & df["_top"] & (df[df.columns[2]] > 0)]
    fig = go.Figure(
        go.Pie(
            labels=d["Item"].str.strip(),
            values=d.iloc[:, 2],
            hole=0.58,
            sort=True,
            textinfo="percent",
            marker=dict(line=dict(color=T["surface"], width=2)),
        )
    )
    fig.update_layout(title=title, showlegend=True)
    return style_fig(fig, 380)


def bar_h(labels, values, title, color=None):
    order = sorted(zip(values, labels))
    fig = go.Figure(
        go.Bar(
            x=[v for v, _ in order],
            y=[l for _, l in order],
            orientation="h",
            marker_color=color or T["accent"],
            marker_line_width=0,
        )
    )
    fig.update_layout(title=title)
    return style_fig(fig, 380)


def scr_waterfall(spec):
    spec = [s for s in spec if s[2] == "total" or s[1] != 0]
    fig = go.Figure(
        go.Waterfall(
            x=[s[0] for s in spec],
            y=[s[1] for s in spec],
            measure=[s[2] for s in spec],
            increasing=dict(marker_color=T["accent"]),
            decreasing=dict(marker_color=T["warn"]),
            totals=dict(marker_color=T["chart_tot"]),
            connector=dict(line=dict(color=T["border_strong"], width=1.2)),
        )
    )
    fig.update_layout(title="Solvency Capital Requirement (SCR) Component Build-up", showlegend=False)
    return style_fig(fig, 390)


# ---------------------------------------------------------------- layout
inject_css(T)

DEMOS = {
    "Generali Group – SFCR YE25": "SFCR YE25 ENG.pdf",
    "Allianz Group – SFCR 2025": "en-Allianz-Group-SFCR-2025.pdf",
    "AXA Insurance UK plc – Annual QRTs": "AXA Insurance UK plc Annual QRTs PUBLIC FY 2025.pdf",
}

DEMO_CARDS = [
    (
        "Generali Group – SFCR YE25",
        "EU Group SFCR · EIOPA S.xx",
        "Assicurazioni Generali S.p.A.",
        "EUR thousand · Partial internal model · Solvency ratio 218.9%",
    ),
    (
        "Allianz Group – SFCR 2025",
        "EU Group SFCR · EIOPA S.xx",
        "Allianz SE – Allianz Group",
        "EUR thousand · Group internal model · Solvency ratio 218.0%",
    ),
    (
        "AXA Insurance UK plc – Annual QRTs",
        "UK PRA Public QRTs · IR.xx",
        "AXA Insurance UK plc",
        "GBP whole pounds · Includes IR.19.01 claims triangle · Ratio 133.3%",
    ),
]

with st.sidebar:
    st.markdown("<div class='fx-side-hdr'>Workspace Theme</div>", unsafe_allow_html=True)
    st.toggle("Dark Mode (Executive Slate)", key="dark")

    st.markdown("<div class='fx-side-hdr'>Source Filings</div>", unsafe_allow_html=True)
    uploads = st.file_uploader(
        "Upload SFCR / QRT PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    go_run = st.button("Run Extraction", type="primary", disabled=not uploads)

    st.markdown("<div class='fx-side-hdr'>Sample Benchmark Filings</div>", unsafe_allow_html=True)
    demo = st.selectbox("Select sample filing", list(DEMOS), label_visibility="collapsed")
    demo_go = st.button("Load Sample Filing")

    if st.session_state.results:
        st.markdown("<div class='fx-side-hdr'>Loaded Documents</div>", unsafe_allow_html=True)
        st.selectbox(
            "Active filing",
            list(st.session_state.results),
            key="active",
            label_visibility="collapsed",
        )
        if st.button("Clear Loaded Filings"):
            st.session_state.results = {}
            st.session_state.pop("active", None)
            st.rerun()

    st.markdown(
        "<div class='fx-side-box'><b>Mock Analytics Mode</b><br>"
        "Values are deterministic sample data modeled after official EIOPA & UK PRA QRT filings. "
        "No external LLM calls are made.</div>",
        unsafe_allow_html=True,
    )

# Top Institutional Header
st.markdown(
    "<div class='fx-header'>"
    "<div class='fx-brand-group'>"
    "<div><span class='fx-word'>Fitch</span><span class='fx-sub'>Ratings</span></div>"
    "<div class='fx-title'>Regulatory Filing Extractor"
    "<span>Insurance Credit Analytics · Solvency II &amp; UK PRA QRT Intelligence</span></div>"
    "</div>"
    "<div class='fx-badges'>"
    "<span class='fx-pill-frame'>EIOPA S.xx / PRA IR.xx</span>"
    "<span class='fx-pill'>MOCK MODE</span>"
    "</div>"
    "</div>",
    unsafe_allow_html=True,
)

if go_run:
    run_extraction([(u.name, page_count(u)) for u in uploads])
elif demo_go:
    run_extraction([(DEMOS[demo], None)])

results = st.session_state.results
if not results:
    tpl_cards = "".join(
        f"<div class='fx-tpl-card'><div class='c'>{html.escape(c)}</div>"
        f"<div class='n'>{html.escape(n)}</div></div>"
        for c, n in TEMPLATES
    )
    st.markdown(
        "<div class='fx-hero'>"
        "<div class='fx-hero-title'>Automated Solvency II &amp; UK PRA QRT Extraction</div>"
        "<div class='fx-hero-sub'>Upload one or more insurer Solvency and Financial Condition Reports (SFCR) "
        "or Quantitative Reporting Templates (QRT) in the sidebar, or launch an instant benchmark profile below. "
        "The extractor normalizes both European Group SFCR annexes (<b>S.xx</b>) and UK PRA solo templates (<b>IR.xx</b>) "
        "with automated accounting cross-checks:</div>"
        f"<div class='fx-tpl-grid'>{tpl_cards}</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("#### Quick-Start Benchmark Filings")
    dcols = st.columns(3)
    for col, (d_key, tag, ent, desc) in zip(dcols, DEMO_CARDS):
        with col:
            st.markdown(
                f"<div class='fx-demo-card'>"
                f"<div class='fx-demo-tag'>{html.escape(tag)}</div>"
                f"<div class='fx-demo-name'>{html.escape(ent)}</div>"
                f"<div class='fx-demo-meta'>{html.escape(desc)}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if st.button(f"Load {ent.split()[0]} Filing", key=f"hero_{d_key}"):
                run_extraction([(DEMOS[d_key], None)])
                st.rerun()
    st.stop()

names = list(results)
if st.session_state.get("active") not in names:
    st.session_state.active = names[-1]

res = results[st.session_state.active]
m, tpl = res["meta"], res["templates"]
lay = {l["key"]: l for l in m["layout"]}

passed_checks = sum(1 for _, ok in m["checks"] if ok)
total_checks = len(m["checks"])

# Entity Header & Metadata Grid
st.markdown(
    f"<div class='fx-entity-banner'>"
    f"<div class='fx-entity-top'>"
    f"<div>"
    f"<div class='fx-entity-name'>{html.escape(m['entity'])}</div>"
    f"<div class='fx-entity-report'>{html.escape(m['report'])} · Source file: <b>{html.escape(m['file'])}</b></div>"
    f"</div>"
    f"<div class='fx-status-badge'>✓ {passed_checks}/{total_checks} Reconciliation Checks Passed</div>"
    f"</div>"
    f"<div class='fx-meta-grid'>"
    f"<div class='fx-meta-item'><div class='fx-meta-lbl'>Reporting Date</div><div class='fx-meta-val'>{html.escape(m['period'])}</div></div>"
    f"<div class='fx-meta-item'><div class='fx-meta-lbl'>Currency &amp; Unit</div><div class='fx-meta-val'>{html.escape(m['unit_label'])}</div></div>"
    f"<div class='fx-meta-item'><div class='fx-meta-lbl'>SCR Methodology</div><div class='fx-meta-val'>{html.escape(m['method'])}</div></div>"
    f"<div class='fx-meta-item'><div class='fx-meta-lbl'>Number Format</div><div class='fx-meta-val'>{html.escape(m['numfmt'])}</div></div>"
    f"<div class='fx-meta-item'><div class='fx-meta-lbl'>Document Pages</div><div class='fx-meta-val'>{m['pages'] or 'Annex extract'}</div></div>"
    f"<div class='fx-meta-item'><div class='fx-meta-lbl'>Extracted Timestamp</div><div class='fx-meta-val'>{html.escape(m['extracted_at'])}</div></div>"
    f"</div>"
    f"</div>",
    unsafe_allow_html=True,
)

# 5 Headline KPI Cards
cols = st.columns(5)
cards = [
    ("Total Assets", f"{m['ccy']} {short_money(m['total_assets'], m['unit'])}", "Solvency II balance sheet", ""),
    ("Excess of Assets", f"{m['ccy']} {short_money(m['excess'], m['unit'])}", "Assets minus total liabilities", ""),
    ("Gross Written Premium", f"{m['ccy']} {short_money(m['gwp'], m['unit'])}", "Non-life direct + prop. accepted", ""),
    ("Solvency Capital Req. (SCR)", f"{m['ccy']} {short_money(m['scr'], m['unit'])}", m["method"], ""),
    ("Solvency II Ratio", f"{m['ratio']:.1%}", f"Own funds {m['ccy']} {short_money(m['own_funds'], m['unit'])} ÷ SCR", "ratio"),
]
for c, (l, v, s, var) in zip(cols, cards):
    c.markdown(kpi(l, v, s, var), unsafe_allow_html=True)

# Validation Strip
chips_html = "".join(f"<span class='fx-chip ok'>{html.escape(l)}</span>" for l, ok in m["checks"] if ok)
st.markdown(
    f"<div class='fx-checks-bar'><span class='fx-checks-label'>Validation Suite</span>{chips_html}</div>",
    unsafe_allow_html=True,
)

keys = ["bs", "lob", "cty", "tri", "scr"]
tab_labels = [f"{lay[k]['code']} · {lay[k]['title'].split('–')[0].split('by')[0].strip()}" for k in keys] + [
    "All Fields & Export"
]
tabs = st.tabs(tab_labels)
tab_of = dict(zip(keys, tabs[:5]))
tab_all = tabs[5]


def heading(key):
    st.markdown(
        f"<div class='fx-sec-hdr'>"
        f"<div class='fx-sec-title'>"
        f"<span class='fx-code-badge'>{html.escape(lay[key]['code'])}</span>"
        f"<span class='fx-sec-name'>{html.escape(lay[key]['title'])}</span>"
        f"</div>"
        f"<span class='fx-sec-unit'>Reported in {html.escape(m['unit_label'])}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if not m["codes"] and key in ("bs", "lob", "scr"):
        st.caption("Row reference codes are omitted for this template because they were not reliably legible in the source layout.")


with tab_of["bs"]:
    heading("bs")
    bs = tpl["bs"]
    html_table(bs)
    a, b = st.columns(2)
    a.plotly_chart(donut(bs, "asset", "Asset Portfolio Composition"), width="stretch")
    b.plotly_chart(donut(bs, "liab", "Liability & Technical Provisions Composition"), width="stretch")

with tab_of["lob"]:
    heading("lob")
    lob = tpl["lob"]
    html_table(lob)
    lob_cols = list(lob.columns[2:-2])
    gross = lob.iloc[:3][lob_cols].fillna(0).sum()
    st.plotly_chart(
        bar_h(lob_cols, [gross[c] for c in lob_cols], f"Gross Written Premium by Line of Business ({m['unit_label']})"),
        width="stretch",
    )

with tab_of["cty"]:
    heading("cty")
    st.caption("Non-life underwriting obligations: domestic home market and top-5 countries by gross premiums written.")
    cty = tpl["cty"]
    html_table(cty)
    cty_cols = list(cty.columns[2:-2])
    if len(cty_cols) > 1:
        st.plotly_chart(
            bar_h(
                [c.replace("Home country – ", "") for c in cty_cols],
                [cty.iloc[0][c] for c in cty_cols],
                f"Gross Direct Premiums Written by Country ({m['unit_label']})",
            ),
            width="stretch",
        )

with tab_of["tri"]:
    heading("tri")
    tri = tpl["tri"]
    if tri is None:
        st.info(
            "Not included in this filing — European Group SFCR public QRT annexes do not include S.19.01 "
            "(non-life claims development triangles are reported in solo entity disclosures)."
        )
    else:
        st.caption("Gross non-life claims paid (non-cumulative) by accident year (N = 2025) and development year.")
        html_table(tri)
        dv = [c for c in tri.columns if c.startswith("Dev") and "+" not in c]
        body = tri.iloc[1:-1]
        fig = go.Figure(
            go.Heatmap(
                z=body[dv].values.astype(float),
                x=dv,
                y=list(body["Accident year"]),
                colorscale=[[0, T["surface2"]], [1, T["accent"]]],
                xgap=2,
                ygap=2,
                colorbar=dict(tickfont=dict(color=T["text"])),
            )
        )
        fig.update_layout(title="Gross Claims Paid Run-Off Heatmap", yaxis=dict(autorange="reversed"))
        st.plotly_chart(style_fig(fig, 380), width="stretch")

with tab_of["scr"]:
    heading("scr")
    html_table(tpl["scr"])
    c1, c2 = st.columns(2)
    c1.markdown(
        kpi("Eligible Own Funds to Meet SCR", f"{m['ccy']} {short_money(m['own_funds'], m['unit'])}", "Total eligible capital resources"),
        unsafe_allow_html=True,
    )
    c2.markdown(
        kpi("Solvency II Coverage Ratio", f"{m['ratio']:.1%}", "Eligible own funds ÷ SCR", "ratio"),
        unsafe_allow_html=True,
    )
    st.write("")
    st.plotly_chart(scr_waterfall(res["scr_chart"]), width="stretch")
    st.info(f"Standard formula template (S.25.01) is not populated — this filer reports under: {m['method']}.")

with tab_all:
    code_of = {k: lay[k]["code"] for k in keys}
    f = res["fields"].copy()
    f["Template"] = f["Template"].map(code_of)
    st.markdown(
        "<div class='fx-sec-hdr'>"
        "<div class='fx-sec-title'>"
        "<span class='fx-code-badge'>AUDIT LOG</span>"
        "<span class='fx-sec-name'>Extracted Data Cells, Confidence Audit &amp; Export</span>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Cell-level extraction audit log with OCR/LLM confidence score and PDF page provenance. Rows below threshold are highlighted.")
    c1, c2, c3 = st.columns([2.2, 1.3, 1])
    sel = c1.multiselect("Filter by Template", sorted(f["Template"].unique()), placeholder="All QRT templates")
    thr = c2.slider("Confidence Review Threshold", 0.50, 0.99, 0.85, 0.01)
    only_low = c3.checkbox("Show flagged rows only")
    if sel:
        f = f[f["Template"].isin(sel)]
    f["_low"] = f["Confidence"] < thr

    m1, m2, m3 = st.columns(3)
    m1.markdown(kpi("Extracted Cells", f"{len(f):,}", "Across selected templates"), unsafe_allow_html=True)
    m2.markdown(kpi("Flagged for Review", f"{int(f['_low'].sum()):,}", f"Confidence below {thr:.0%}"), unsafe_allow_html=True)
    m3.markdown(kpi("Mean Extraction Confidence", f"{f['Confidence'].mean():.1%}", "Cell-level model score", "ratio"), unsafe_allow_html=True)
    st.write("")

    view = f[f["_low"]] if only_low else f

    def _fmt_conf(v, row):
        cls = "fx-conf-low" if row.get("_low", False) else "fx-conf-ok"
        return f"<span class='fx-conf-pill {cls}'>{v:.1%}</span>"

    html_table(
        view,
        fmt={
            "Value": lambda v, _: f"{v:,.0f}",
            "Confidence": _fmt_conf,
            "Source page": lambda v, _: f"p. {v:.0f}",
        },
    )
    st.write("")
    out = f.drop(columns="_low")
    xbuf = io.BytesIO()
    with pd.ExcelWriter(xbuf, engine="openpyxl") as xw:
        for k in keys:
            df = tpl[k]
            if df is not None:
                df[[c for c in df.columns if not c.startswith("_")]].to_excel(
                    xw, sheet_name=code_of[k][:31], index=False
                )
        out.to_excel(xw, sheet_name="All fields", index=False)
    payload = json.dumps(
        {
            "meta": {k: v for k, v in m.items() if k not in ("checks", "layout")},
            "fields": out.to_dict("records"),
        },
        indent=2,
        default=str,
    )
    d1, d2, d3 = st.columns(3)
    stem = m["file"].rsplit(".", 1)[0]
    d1.download_button(
        "⬇ Download Excel Workbook (.xlsx)",
        xbuf.getvalue(),
        f"{stem}_extraction.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    d2.download_button(
        "⬇ Download Flat Audit Log (.csv)",
        out.to_csv(index=False),
        f"{stem}_fields.csv",
        "text/csv",
    )
    d3.download_button(
        "⬇ Download Structured Payload (.json)",
        payload,
        f"{stem}_extraction.json",
        "application/json",
    )

