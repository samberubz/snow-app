"""
PLAN THE POW — Quebec Ski Resort Snowfall Comparator
"""
import streamlit as st
import requests
import pandas as pd
import numpy as np
import pydeck as pdk
import plotly.graph_objects as go
from datetime import datetime

# -------------------- CONFIG --------------------
# Fixed display order (keeps left-to-right consistent regardless of forecast)
MOUNTAINS = {
    "Stoneham":    (47.0094, -71.3767),
    "Sutton":      (45.1017, -72.5606),
    "Tremblant":   (46.2094, -74.5850),
    "Orford":      (45.3167, -72.2333),
    "Sainte-Anne": (47.0756, -70.9069),
    "Bromont":     (45.3167, -72.6500),
}

# Regional groupings for the snow recap
REGIONS = {
    "Estrie":      ["Sutton", "Orford", "Bromont"],
    "Laurentides": ["Tremblant"],
    "East":        ["Stoneham", "Sainte-Anne"],
}
RECAP_HOURS = 48  # window for the recap line
WINDOWS = {"6 h": 6, "12 h": 12, "18 h": 18, "24 h": 24, "48 h": 48, "72 h": 72}
FREEZING_RAIN_CODES = {66, 67}

VAR_MAP = {
    "Snowfall":      ("snowfall",       "cm", "#4FC3F7", "Blues",   20.0, [79, 195, 247]),
    "Rain":          ("rain",           "mm", "#66BB6A", "Greens",  20.0, [102, 187, 106]),
    "Freezing rain": ("freezing_rain",  "mm", "#AB47BC", "Purples", 10.0, [171, 71, 188]),
    "Temperature":   ("temperature_2m", "°C", "#FF6B6B", "RdBu_r",  15.0, [255, 107, 107]),
}

MAX_HEIGHT_M = 80000
COLUMN_RADIUS_M = 12000

# -------------------- PAGE SETUP --------------------
st.set_page_config(page_title="Where's the Pow?", page_icon="❄️", layout="wide")

st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@300;400;500;600;700&family=Ubuntu:wght@300;400;500;700&display=swap" rel="stylesheet">

<style>
    /* Default everything to Josefin Sans */
    html, body, [class*="css"], .stApp, .stMarkdown,
    .stSelectbox, .stButton, .stCaption, .stMetric,
    h1, h2, h3, h4, h5, h6, p, span, div, label {
        font-family: "Josefin Sans", sans-serif !important;
    }
    /* Numbers helper class — applied wherever we render numbers */
    .num, .num * {
        font-family: "Ubuntu", sans-serif !important;
        font-feature-settings: "tnum" 1;
    }
    /* Streamlit metric values are always numeric -> Ubuntu */
    div[data-testid="stMetricValue"],
    div[data-testid="stMetricValue"] * {
        font-family: "Ubuntu", sans-serif !important;
    }
    /* Force Ubuntu on the selectbox display text & options (they contain numbers like '24 h') */
    div[data-baseweb="select"] *,
    div[role="listbox"] *,
    li[role="option"] * {
        font-family: "Ubuntu", sans-serif !important;
    }

    .block-container { padding: 1rem 0.5rem 2rem 0.5rem; max-width: 100%; }
    h1 { font-size: 1.9rem !important; text-align: center;
         color: #FFFFFF !important; margin-bottom: 0.3rem;
         font-weight: 700 !important; letter-spacing: 0.08em; }
    h3 { color: #FFFFFF !important; font-weight: 500 !important; }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg,#1a237e 0%,#0d47a1 100%);
        padding: 10px; border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    div[data-testid="stMetric"] label {
        color: #FFFFFF !important; font-size: 0.8rem !important;
        font-weight: 400 !important;
    }
    div[data-testid="stMetricValue"] {
        color: #FFFFFF !important; font-size: 1.4rem !important;
        font-weight: 500 !important;
    }
    .map-legend {
        background: rgba(10, 14, 39, 0.85);
        border: 1px solid rgba(255,255,255,0.15);
        border-radius: 10px;
        padding: 10px 14px;
        color: #FFFFFF;
        font-size: 0.9rem;
        font-family: "Josefin Sans", sans-serif !important;
    }
    .map-legend .row { display: flex; justify-content: space-between;
                       padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }
    .map-legend .row:last-child { border-bottom: none; }
    .map-legend .dot { display: inline-block; width: 10px; height: 10px;
                       border-radius: 50%; margin-right: 8px; vertical-align: middle; }

    .recap-box {
        background: rgba(10,14,39,0.6);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 10px;
        padding: 10px 14px;
        margin: 14px 0 6px 0;
        color: #FFFFFF;
        font-size: 0.9rem;
        font-family: "Josefin Sans", sans-serif !important;
    }
    .recap-title {
        font-weight: 600; margin-bottom: 6px; color: #4FC3F7;
    }
    .recap-row {
        padding: 4px 0;
        border-bottom: 1px solid rgba(255,255,255,0.07);
    }
    .recap-row:last-child { border-bottom: none; }
    .recap-row .msg { color: rgba(255,255,255,0.85); }
</style>
""", unsafe_allow_html=True)

st.markdown("#")
st.markdown("# ❄️ WHERE'S THE POW?")
st.markdown(
    f'<div style="text-align:center;color:rgba(255,255,255,0.6);font-size:0.85rem;">'
    f'Live · <span class="num">{datetime.now().strftime("%b %d, %Y %H:%M")}</span></div>',
    unsafe_allow_html=True,
)

# -------------------- FETCH (early, so recap can render under title) --------------------
@st.cache_data(ttl=1800)
def fetch(lat, lon):
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}"
           "&hourly=snowfall,rain,precipitation,temperature_2m,weather_code"
           "&timezone=America/Montreal&forecast_days=4")
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()

with st.spinner("Fetching weather..."):
    try:
        data = {m: fetch(lat, lon) for m, (lat, lon) in MOUNTAINS.items()}
    except Exception as e:
        st.error(f"Fetch failed: {e}")
        st.stop()

for m, d in data.items():
    codes = d["hourly"]["weather_code"]
    precip = d["hourly"]["precipitation"]
    d["hourly"]["freezing_rain"] = [
        p if c in FREEZING_RAIN_CODES else 0.0
        for c, p in zip(codes, precip)
    ]

# -------------------- SNOW RECAP --------------------
def region_snow_summary(region_name, mountain_list):
    """Average snowfall over RECAP_HOURS for a region."""
    per_mtn = {}
    for m in mountain_list:
        per_mtn[m] = sum(data[m]["hourly"]["snowfall"][:RECAP_HOURS])
    avg = sum(per_mtn.values()) / len(per_mtn)
    max_mtn = max(per_mtn, key=per_mtn.get)
    max_val = per_mtn[max_mtn]
    return avg, max_mtn, max_val

recap_lines = []
for region, mtn_list in REGIONS.items():
    avg, top_mtn, top_val = region_snow_summary(region, mtn_list)
    if avg < 0.5:
        msg = "No snowfall on the forecast"
    else:
        msg = (f'<span class="num">{avg:.1f}</span> cm avg · '
               f'top: {top_mtn} <span class="num">{top_val:.1f}</span> cm')
    recap_lines.append(
        f'<div class="recap-row"><b>{region}</b> · <span class="msg">{msg}</span></div>'
    )

st.markdown(
    f'<div class="recap-box">'
    f'<div class="recap-title">❄️ Snow recap · next <span class="num">{RECAP_HOURS}</span> h</div>'
    f'{"".join(recap_lines)}'
    f'</div>',
    unsafe_allow_html=True,
)

# -------------------- CONTROLS --------------------
c1, c2 = st.columns(2)
with c1:
    window_label = st.selectbox("Forecast window", list(WINDOWS.keys()), index=3)
with c2:
    variable = st.selectbox("Variable", list(VAR_MAP.keys()))
HOURS = WINDOWS[window_label]
api_var, unit, base_color, colorscale, ref_max, rgb = VAR_MAP[variable]

# -------------------- AGGREGATE --------------------
totals = {}
for m, d in data.items():
    vals = d["hourly"][api_var][:HOURS]
    totals[m] = sum(vals) if api_var != "temperature_2m" else sum(vals) / len(vals)

# Snowflake ranking by absolute snow amount (cm)
def snowflakes(value):
    """Return snowflakes based on absolute snowfall in cm."""
    if value >= 5:
        return "❄️❄️❄️"
    elif value >= 3:
        return "❄️❄️"
    elif value >= 1:
        return "❄️"
    else:
        return ""

all_vals = list(totals.values())
is_temp = (api_var == "temperature_2m")
show_flakes = (api_var == "snowfall")

# -------------------- TOP CARDS (FIXED ORDER) --------------------
st.markdown(
    f'### {variable} · next <span class="num">{window_label}</span>',
    unsafe_allow_html=True,
)
cols = st.columns(3)
for i, (m, v) in enumerate(totals.items()):
    if show_flakes:
        flakes = snowflakes(v)
        prefix = f"{flakes} " if flakes else ""
    else:
        prefix = ""
    with cols[i % 3]:
        st.metric(f"{prefix}{m}", f"{v:.1f} {unit}")

st.divider()

# -------------------- 3D MAP --------------------
st.markdown(
    f'### Map <span style="font-weight:300;color:rgba(255,255,255,0.6);font-size:0.9rem;">'
    f'[height scaled to <span class="num">{ref_max}</span> {unit}]</span>',
    unsafe_allow_html=True,
)

rows = []
for name, (lat, lon) in MOUNTAINS.items():
    v = totals[name]
    if is_temp:
        h_ratio = np.clip((ref_max - v) / (2 * ref_max), 0, 1)
    else:
        h_ratio = np.clip(v / ref_max, 0, 1)
    rows.append({
        "name": name,
        "lat": lat,
        "lon": lon,
        "value": round(v, 2),
        "height": h_ratio * MAX_HEIGHT_M,
        "color": rgb + [int(160 + 95 * h_ratio)],
    })
df = pd.DataFrame(rows)

column_layer = pdk.Layer(
    "ColumnLayer",
    data=df,
    get_position=["lon", "lat"],
    get_elevation="height",
    elevation_scale=1,
    radius=COLUMN_RADIUS_M,
    get_fill_color="color",
    pickable=True,
    auto_highlight=True,
    extruded=True,
)

view_state = pdk.ViewState(
    latitude=46.4,
    longitude=-72.5,
    zoom=6.5,
    pitch=55,
    bearing=-15,
)

deck = pdk.Deck(
    layers=[column_layer],
    initial_view_state=view_state,
    map_style="dark_no_labels",
    tooltip={"text": "{name}\n{value} " + unit},
)

# Legend on top (compact), map below — stacks naturally on phone & desktop
rgb_css = f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
rows_html = "".join(
    f'<div class="row"><span><span class="dot" style="background:{rgb_css}"></span>{m}</span>'
    f'<span class="num"><b>{v:.1f}</b> {unit}</span></div>'
    for m, v in totals.items()
)
st.markdown(
    f'<div class="map-legend"><div style="font-weight:600;margin-bottom:6px;">'
    f'{variable}</div>{rows_html}</div>',
    unsafe_allow_html=True,
)

st.pydeck_chart(deck, use_container_width=True, height=460)

st.markdown(
    f'<div style="color:rgba(255,255,255,0.55);font-size:0.8rem;margin-top:6px;">'
    f'🔄 Drag to pan · two-finger drag to tilt · full column = '
    f'<span class="num">{ref_max}</span> {unit} · tap a column for details</div>',
    unsafe_allow_html=True,
)
st.divider()

# -------------------- HOURLY CHARTS (FIXED ORDER, ONE PER ROW) --------------------
st.markdown("### Hourly Breakdown")

for m in MOUNTAINS.keys():
    d = data[m]
    times = pd.to_datetime(d["hourly"]["time"][:HOURS])
    v = d["hourly"][api_var][:HOURS]

    fig = go.Figure()
    if is_temp:
        fig.add_trace(go.Scatter(
            x=times, y=v, mode="lines+markers",
            line=dict(color=base_color, width=2.5),
            marker=dict(size=5), fill="tozeroy",
            fillcolor="rgba(255,107,107,0.15)",
            hovertemplate="%{x|%a %Hh}<br>%{y:.1f} °C<extra></extra>",
        ))
    else:
        fig.add_trace(go.Bar(
            x=times, y=v,
            marker=dict(color=v, colorscale=colorscale, line=dict(width=0)),
            hovertemplate="%{x|%a %Hh}<br>%{y:.2f} " + unit + "<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text=f"<b>{m}</b>", x=0.02, y=0.95,
                   font=dict(size=14, color="#FFFFFF",
                             family="Josefin Sans, sans-serif")),
        height=220, showlegend=False,
        paper_bgcolor="#0a0e27", plot_bgcolor="#0a0e27",
        font=dict(color="#FFFFFF", family="Josefin Sans, sans-serif", size=12),
        margin=dict(l=10, r=10, t=35, b=20),
    )
    fig.update_xaxes(
        gridcolor="rgba(255,255,255,0.08)", tickformat="%a %Hh",
        tickfont=dict(size=10, color="#FFFFFF", family="Ubuntu, sans-serif"),
    )
    fig.update_yaxes(
        gridcolor="rgba(255,255,255,0.08)", title_text=unit,
        title_font=dict(size=11, color="#FFFFFF", family="Josefin Sans, sans-serif"),
        tickfont=dict(size=10, color="#FFFFFF", family="Ubuntu, sans-serif"),
        rangemode="tozero" if not is_temp else "normal",
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

st.caption("Source: Open-Meteo · GFS/ICON/ECMWF blend · freezing rain from WMO codes 66/67")
