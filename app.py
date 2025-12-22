# app.py — Helios Reporting (TVA PDF + Inscriptions CSV)
# Refonte "Synthèse globale" :
# - Vision globale sur tous les mois (CA total + catégories)
# - Prévisionnel théorique sur 3 mois (méthode simple : moyenne mobile / tendance linéaire)
# - État des lieux adhérents (à l’instant T) avec détail : abonnements actifs récurrents + carnets 10 actifs (option)

import os
import re
from io import BytesIO
from datetime import datetime, date, timedelta

import streamlit as st
import pandas as pd
import pdfplumber
import altair as alt


# =========================
# CONFIG & STORAGE
# =========================

DATA_DIR = "data"
HISTORY_TVA_FILE = os.path.join(DATA_DIR, "history_tva.csv")     # lignes de ventes (PDF TVA)
HISTORY_ABOS_FILE = os.path.join(DATA_DIR, "history_abos.csv")   # inscriptions (CSV)
os.makedirs(DATA_DIR, exist_ok=True)

CATEGORIES_TVA = [
    "Abonnements / cartes",
    "Boissons & compléments alimentaires",
    "Vestimentaire & accessoires sport",
    "AUTRE",
]

MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
}

# =========================
# PAGE / STYLE
# =========================

st.set_page_config(page_title="Helios — Dashboard", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1400px; }
      h1,h2,h3,h4 { font-family: -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif !important; }

      /* Tabs pill */
      .stTabs [data-baseweb="tab-list"] { gap: 0.5rem; }
      .stTabs [data-baseweb="tab"] {
        padding: 0.42rem 1.05rem;
        border-radius: 999px;
        background: rgba(2,6,23,.55);
        border: 1px solid rgba(148,163,184,.18);
      }
      .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #2563eb, #22c55e) !important;
        color: white !important;
      }

      /* KPI cards */
      .kpiGrid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
      @media (max-width: 1200px){ .kpiGrid{ grid-template-columns: repeat(2, 1fr);} }
      @media (max-width: 700px){ .kpiGrid{ grid-template-columns: repeat(1, 1fr);} }

      .kpiCard {
        background: radial-gradient(1200px 500px at 20% 10%, rgba(37,99,235,.22), transparent 55%),
                    radial-gradient(900px 400px at 80% 20%, rgba(34,197,94,.16), transparent 55%),
                    linear-gradient(180deg, rgba(2,6,23,.72), rgba(2,6,23,.92));
        border: 1px solid rgba(148,163,184,.18);
        box-shadow: 0 16px 32px rgba(0,0,0,.32);
        border-radius: 18px;
        padding: 16px 16px 14px 16px;
      }
      .kpiTitle { color: rgba(226,232,240,.85); font-size: .92rem; margin-bottom: 6px; }
      .kpiValue { font-size: 2.05rem; font-weight: 700; letter-spacing: -0.02em; }
      .kpiDelta { margin-top: 8px; display: inline-flex; gap: 8px; align-items: center; font-size: .95rem; }
      .badgeUp {
        background: rgba(34,197,94,.18);
        border: 1px solid rgba(34,197,94,.35);
        color: rgb(74,222,128);
        padding: 3px 10px;
        border-radius: 999px;
        font-weight: 600;
      }
      .badgeDown {
        background: rgba(239,68,68,.16);
        border: 1px solid rgba(239,68,68,.35);
        color: rgb(248,113,113);
        padding: 3px 10px;
        border-radius: 999px;
        font-weight: 600;
      }
      .muted { color: rgba(226,232,240,.72); font-size: .95rem; }
      .section { margin-top: 10px; }

      /* Make charts feel tighter */
      .stAltairChart { background: transparent !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# STREAMLIT COMPAT HELPERS
# =========================

def show_chart(chart):
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)

def show_df(df, height=None):
    try:
        st.dataframe(df, width="stretch", height=height)
    except TypeError:
        st.dataframe(df, use_container_width=True, height=height)

# =========================
# UTILS
# =========================

def to_float(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return 0.0
    s = str(x).replace("€", "").replace("\u00a0", "").replace(" ", "").strip()
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def to_int(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return 0
    try:
        return int(float(str(x).replace(",", ".").replace(" ", "")))
    except ValueError:
        return 0

def sort_months(months):
    return sorted(months, key=lambda m: datetime.strptime(m, "%Y-%m"))

def format_mois_label(mois: str) -> str:
    dt = datetime.strptime(mois, "%Y-%m")
    return f"{MOIS_FR[dt.month]} {dt.year}"

def month_add(ym: str, n: int) -> str:
    dt = datetime.strptime(ym, "%Y-%m")
    y = dt.year
    m = dt.month + n
    while m > 12:
        y += 1
        m -= 12
    while m < 1:
        y -= 1
        m += 12
    return f"{y}-{m:02d}"

def parse_date_creation(raw):
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    if "à" in s:
        s = s.split("à")[0].strip()
    elif " " in s:
        s = s.split(" ")[0].strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def parse_simple_date(raw):
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    if "à" in s:
        s = s.split("à")[0].strip()
    if " " in s:
        s = s.split(" ")[0].strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def extract_period_from_text(text: str):
    m = re.search(r"(\d{2}-\d{2}-\d{4})\s*-\s*(\d{2}-\d{2}-\d{4})", text or "")
    if not m:
        return None, None, None
    d1 = datetime.strptime(m.group(1), "%d-%m-%Y")
    d2 = datetime.strptime(m.group(2), "%d-%m-%Y")
    mois = f"{d1.year}-{d1.month:02d}"
    return mois, d1.date().isoformat(), d2.date().isoformat()

# =========================
# ALTair THEME-ish
# =========================

def alt_base():
    return alt.Chart().configure_view(strokeOpacity=0).configure_axis(
        labelColor="rgba(226,232,240,.78)",
        titleColor="rgba(226,232,240,.78)",
        gridColor="rgba(148,163,184,.16)",
        tickColor="rgba(148,163,184,.16)",
        domainColor="rgba(148,163,184,.18)",
    ).configure_legend(
        labelColor="rgba(226,232,240,.78)",
        titleColor="rgba(226,232,240,.78)",
    ).configure_title(
        color="rgba(226,232,240,.92)",
        fontSize=16,
        anchor="start",
        offset=10
    )

def line_with_forecast(df_hist, df_fc, x="mois_label", y="CA", title=""):
    # historical: solid
    ch1 = (
        alt.Chart(df_hist)
        .mark_line(point=alt.OverlayMarkDef(size=70), strokeWidth=2.6)
        .encode(
            x=alt.X(f"{x}:N", title=None, sort=list(df_hist[x])),
            y=alt.Y(f"{y}:Q", title="€"),
            tooltip=[x, alt.Tooltip(y, format=",.0f")]
        )
    )
    # forecast: dashed
    ch2 = (
        alt.Chart(df_fc)
        .mark_line(strokeDash=[6, 4], strokeWidth=2.6, opacity=0.9)
        .encode(
            x=alt.X(f"{x}:N", title=None, sort=list(pd.concat([df_hist[x], df_fc[x]]))),
            y=alt.Y(f"{y}:Q", title="€"),
            tooltip=[x, alt.Tooltip(y, format=",.0f")]
        )
    )
    return (ch1 + ch2).properties(height=280, title=title)

def donut(df, label_col, value_col, title=""):
    if df.empty or df[value_col].sum() <= 0:
        return None
    arcs = (
        alt.Chart(df)
        .mark_arc(innerRadius=65, outerRadius=118)
        .encode(
            theta=alt.Theta(f"{value_col}:Q", stack=True),
            color=alt.Color(f"{label_col}:N", legend=alt.Legend(title=""), scale=alt.Scale(scheme="tableau10")),
            tooltip=[label_col, alt.Tooltip(value_col, format=",.0f")]
        )
    )
    txt = (
        alt.Chart(df)
        .transform_joinaggregate(total=f"sum({value_col})")
        .transform_calculate(pct=f"datum.{value_col}/datum.total*100")
        .mark_text(radius=140, size=11, color="white")
        .encode(
            theta=alt.Theta(f"{value_col}:Q", stack=True),
            text=alt.Text("pct:Q", format=".1f")
        )
    )
    return (arcs + txt).properties(height=290, title=title)

def grouped_bars(df, x, series, y, title=""):
    # df must have columns x, series, y
    if df.empty:
        return None
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8)
        .encode(
            x=alt.X(f"{x}:N", title=None, sort=list(df[x].unique())),
            xOffset=alt.XOffset(f"{series}:N"),
            y=alt.Y(f"{y}:Q", title="€"),
            color=alt.Color(f"{series}:N", legend=alt.Legend(title=""), scale=alt.Scale(scheme="tableau10")),
            tooltip=[x, series, alt.Tooltip(y, format=",.0f")]
        )
        .properties(height=260, title=title)
    )

# =========================
# TVA — CATEGORISATION
# =========================

def categorize_product_tva(name: str):
    n = (name or "").lower()

    # Abonnements / cartes
    if "abonn" in n:
        return "Abonnements / cartes", "Abonnement"
    if "carte" in n or "prépayée" in n or "prepayee" in n:
        return "Abonnements / cartes", "Carte"
    if "drop in" in n or "drop-in" in n or "dropin" in n:
        return "Abonnements / cartes", "Drop-in"

    # Boissons / compléments
    patterns_boissons = [
        "nocco", "barebells", "fitaid", "vitamin well", "vitaminwell",
        "whey", "creatine", "créatine", "collagene", "collagène",
        "magnesium", "magnésium", "omega", "oméga"
    ]
    if any(p in n for p in patterns_boissons):
        return "Boissons & compléments alimentaires", "Boisson / complément"

    # Vestimentaire / accessoires
    patterns_vet = ["t-shirt", "t shirt", "tee shirt", "ceinture", "manique", "maniques", "genouill"]
    if any(p in n for p in patterns_vet):
        return "Vestimentaire & accessoires sport", "Textile / accessoires"

    return "AUTRE", "AUTRE"

# =========================
# PDF TVA — EXTRACTION
# =========================

def extract_sales_tables_from_pdf(file_obj: BytesIO, forced_month: str = None) -> pd.DataFrame:
    rows = []
    periode_debut = None
    periode_fin = None

    with pdfplumber.open(file_obj) as pdf:
        first_text = pdf.pages[0].extract_text() or ""
        mois_detecte, periode_debut, periode_fin = extract_period_from_text(first_text)
        periode_mois = forced_month or mois_detecte
        if periode_mois is None:
            t = datetime.today()
            periode_mois = f"{t.year}-{t.month:02d}"

        for page in pdf.pages:
            tables = page.extract_tables()
            for t in tables:
                if not t or len(t) < 2:
                    continue
                header = [c.strip() if c else "" for c in t[0]]
                hl = [h.lower() for h in header]
                if not any("désignation" in h or "designation" in h for h in hl):
                    continue
                if not any("quantité" in h or "quantite" in h for h in hl):
                    continue

                df = pd.DataFrame(t[1:], columns=header)

                colmap = {}
                for col in df.columns:
                    lc = col.lower().strip()
                    if "désignation" in lc or "designation" in lc:
                        colmap[col] = "designation"
                    elif "quantité" in lc or "quantite" in lc:
                        colmap[col] = "quantite"
                    elif "total ttc" in lc:
                        colmap[col] = "total_ttc"
                    elif "tva (%)" in lc or "tva%" in lc:
                        colmap[col] = "tva_pct"
                    elif "total tva" in lc:
                        colmap[col] = "total_tva"
                    elif "total ht" in lc:
                        colmap[col] = "total_ht"
                    else:
                        colmap[col] = lc
                df = df.rename(columns=colmap)

                df["quantite"] = df.get("quantite", 0).apply(to_int)
                df["total_ttc"] = df.get("total_ttc", 0).apply(to_float)
                df["total_tva"] = df.get("total_tva", 0).apply(to_float)
                df["total_ht"] = df.get("total_ht", 0).apply(to_float)
                df["tva_pct"] = df.get("tva_pct", 0).apply(to_float)

                df["mois"] = periode_mois
                df["periode_debut"] = periode_debut
                df["periode_fin"] = periode_fin
                rows.append(df)

    if not rows:
        return pd.DataFrame()

    full_df = pd.concat(rows, ignore_index=True)
    full_df = full_df[full_df["designation"].notna()]
    full_df = full_df[full_df["designation"].astype(str).str.strip() != ""]

    cats = full_df["designation"].astype(str).apply(categorize_product_tva)
    full_df["categorie"] = cats.apply(lambda x: x[0])
    full_df["sous_categorie"] = cats.apply(lambda x: x[1])
    return full_df

# =========================
# HISTO TVA
# =========================

def load_history_tva() -> pd.DataFrame:
    cols = [
        "mois", "periode_debut", "periode_fin",
        "designation", "quantite",
        "total_ttc", "total_tva", "total_ht", "tva_pct",
        "categorie", "sous_categorie",
    ]
    if os.path.exists(HISTORY_TVA_FILE):
        try:
            df = pd.read_csv(HISTORY_TVA_FILE)
            if df.empty:
                return pd.DataFrame(columns=cols)
            return df
        except pd.errors.EmptyDataError:
            return pd.DataFrame(columns=cols)
    return pd.DataFrame(columns=cols)

def save_history_tva(df: pd.DataFrame):
    df.to_csv(HISTORY_TVA_FILE, index=False)

def build_month_summary_tva(df_hist: pd.DataFrame) -> pd.DataFrame:
    df = df_hist.copy()
    df["total_ttc"] = df["total_ttc"].apply(to_float)
    df["quantite"] = df["quantite"].apply(to_int)
    out = df.groupby("mois").agg(
        CA_total=("total_ttc", "sum"),
        Qt_total=("quantite", "sum"),
    ).reset_index()

    for cat in CATEGORIES_TVA:
        col_name = f"CA_{cat}"
        tmp = df[df["categorie"] == cat].groupby("mois")["total_ttc"].sum().rename(col_name)
        out = out.merge(tmp, on="mois", how="left")

    out = out.fillna(0.0)
    out = out.sort_values("mois", key=lambda s: s.map(lambda x: datetime.strptime(x, "%Y-%m")))
    return out

# =========================
# CSV INSCRIPTIONS — CLASSIF
# =========================

def classify_contrat(offre: str):
    """
    Demandes :
      - "Liberté" = Carnet 10 séances (pas abonnement)
      - "Drop in" exclu
      - Events exclus
      - Abonnements = offres normales (Essentiel/Evolution/Premium/Hyrox/1x semaine/Ascension...)
    """
    s = (offre or "").lower().strip()

    # Events (exclu)
    if any(k in s for k in ["soirée", "soiree", "inauguration", "raclette", "event", "offre de rentrée", "offre de rentree"]):
        return ("EVENT", offre)

    # Drop-in (exclu)
    if "drop" in s:
        return ("EXCLU", "Drop in")

    # Liberté = carnet 10
    if "liberté" in s or "liberte" in s:
        return ("CARTE_10", "Carnet 10 séances")

    # Abonnements
    abo_keywords = ["essentiel", "evolution", "premium", "hyrox", "1x semaine", "1 x semaine", "ascension"]
    if any(k in s for k in abo_keywords):
        return ("ABONNEMENT", offre)

    # par défaut : exclu
    return ("EXCLU", offre)

def extract_abos_from_csv(file_obj: BytesIO) -> pd.DataFrame:
    df_raw = pd.read_csv(file_obj)
    df_raw.columns = [c.strip() for c in df_raw.columns]

    # Détection "date de création"
    date_col = None
    for c in df_raw.columns:
        lc = c.lower()
        if "date" in lc and ("cré" in lc or "crea" in lc or "crÃ©" in lc):
            date_col = c
            break
    if date_col is None:
        for c in df_raw.columns:
            if "date" in c.lower():
                date_col = c
                break
    if date_col is None:
        date_col = df_raw.columns[0]

    colmap = {
        "Prénom": "prenom",
        "Nom": "nom",
        "Email": "email",
        "Téléphone": "telephone",
        "Offre": "offre",
        "Date de début": "date_debut",
        "Date de fin": "date_fin",
        "Statut": "statut",
        "Méthode de paiement": "methode_paiement",
        "Prix de l'offre": "prix_offre",
        "Prix personnalisé": "prix_perso",
        "Reconduction": "reconduction",
        "Paiement comptant": "paiement_comptant",
        "Entrées restantes": "entrees_restantes",
        "Entrées max": "entrees_max",
    }
    df = df_raw.rename(columns={k: v for k, v in colmap.items() if k in df_raw.columns})

    df["date_creation"] = df_raw[date_col].apply(parse_date_creation)
    df = df[~df["date_creation"].isna()]
    if df.empty:
        return df

    df["mois_creation"] = df["date_creation"].apply(lambda d: f"{d.year}-{d.month:02d}")

    df["offre"] = df.get("offre", "").astype(str)
    types = df["offre"].apply(classify_contrat)
    df["type_contrat"] = types.apply(lambda x: x[0])
    df["sous_type"] = types.apply(lambda x: x[1])

    df["prix_offre"] = df.get("prix_offre", 0).apply(to_float)
    df["prix_perso"] = df.get("prix_perso", 0).apply(to_float)
    df["prix_effectif"] = df.apply(lambda r: r["prix_perso"] if r["prix_perso"] > 0 else r["prix_offre"], axis=1)

    df["date_debut_parsed"] = df.get("date_debut").apply(parse_simple_date)
    df["date_fin_parsed"] = df.get("date_fin").apply(parse_simple_date)

    df["entrees_restantes"] = df.get("entrees_restantes", 0).apply(to_int)
    df["entrees_max"] = df.get("entrees_max", 0).apply(to_int)

    return df

def load_history_abos() -> pd.DataFrame:
    if os.path.exists(HISTORY_ABOS_FILE):
        try:
            return pd.read_csv(HISTORY_ABOS_FILE)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    return pd.DataFrame()

def save_history_abos(df: pd.DataFrame):
    df.to_csv(HISTORY_ABOS_FILE, index=False)

# =========================
# ABOS ACTIFS + FORECAST
# =========================

def compute_active_members(df_abos: pd.DataFrame, ref_dt: date):
    """
    Retourne :
      - df_sub_active : abonnements actifs récurrents (Reconduction != Non), VALIDATED, dates OK
      - df_carnet_active : carnets 10 "actifs" (VALIDATED et entrées_restantes > 0), dates si dispo
    """
    if df_abos is None or df_abos.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = df_abos.copy()
    for col in ["statut", "reconduction", "type_contrat", "prix_effectif", "date_debut_parsed", "date_fin_parsed", "entrees_restantes", "sous_type"]:
        if col not in df.columns:
            df[col] = None

    df["statut_norm"] = df["statut"].astype(str).str.upper()
    df["reconduction_norm"] = df["reconduction"].astype(str).str.strip().str.lower()

    # ABONNEMENTS récurrents actifs
    recurring = df["reconduction_norm"] != "non"  # vide = récurrent
    sub = df[(df["type_contrat"] == "ABONNEMENT") & recurring].copy()

    sub_active = sub[
        (sub["statut_norm"] == "VALIDATED") &
        sub["date_debut_parsed"].notna() &
        (sub["date_debut_parsed"] <= ref_dt) &
        (sub["date_fin_parsed"].isna() | (sub["date_fin_parsed"] >= ref_dt))
    ].copy()

    # Carnets 10 actifs (si tu veux les compter comme "adhérents actifs")
    carnet = df[df["type_contrat"] == "CARTE_10"].copy()
    carnet_active = carnet[
        (carnet["statut_norm"] == "VALIDATED") &
        (carnet["entrees_restantes"].fillna(0).astype(int) > 0)
    ].copy()

    return sub_active, carnet_active

def compute_subscription_projection_next_month(df_abos: pd.DataFrame, ref_dt: date):
    """
    Projection CA mois suivant basé uniquement sur les abonnements récurrents (pas carnets, pas events).
    """
    if df_abos is None or df_abos.empty:
        return 0.0, None

    df = df_abos.copy()
    for col in ["statut", "reconduction", "type_contrat", "prix_effectif", "date_debut_parsed", "date_fin_parsed"]:
        if col not in df.columns:
            df[col] = None

    df["statut_norm"] = df["statut"].astype(str).str.upper()
    df["reconduction_norm"] = df["reconduction"].astype(str).str.strip().str.lower()

    recurring = df["reconduction_norm"] != "non"
    df = df[(df["type_contrat"] == "ABONNEMENT") & recurring].copy()
    if df.empty:
        return 0.0, None

    # bornes mois suivant
    if ref_dt.month == 12:
        nm_start = date(ref_dt.year + 1, 1, 1)
    else:
        nm_start = date(ref_dt.year, ref_dt.month + 1, 1)
    if nm_start.month == 12:
        after = date(nm_start.year + 1, 1, 1)
    else:
        after = date(nm_start.year, nm_start.month + 1, 1)
    nm_end = after - timedelta(days=1)

    proj = df[
        df["date_debut_parsed"].notna() &
        (df["date_debut_parsed"] <= nm_end) &
        (df["date_fin_parsed"].isna() | (df["date_fin_parsed"] >= nm_start)) &
        df["statut_norm"].isin(["VALIDATED", "FUTURE"])
    ].copy()

    ca = proj["prix_effectif"].apply(to_float).sum()
    label = f"{MOIS_FR[nm_start.month]} {nm_start.year}"
    return ca, label

def forecast_next_3_months(summary_tva: pd.DataFrame, method: str = "Moyenne mobile (3 mois)"):
    """
    Forecast CA_total (et catégories par ratio moyen) sur 3 mois.
    Méthodes:
      - Moyenne mobile (3 mois) : moyenne des 3 derniers points
      - Tendance linéaire : régression simple sur l'index temps
    """
    if summary_tva is None or summary_tva.empty:
        return pd.DataFrame()

    s = summary_tva.sort_values("mois").copy()
    last_mois = s["mois"].iloc[-1]
    horizon = [month_add(last_mois, i) for i in [1, 2, 3]]

    # ratios catégorie moyens (sur 3 derniers mois)
    tail = s.tail(3).copy()
    total_tail = tail["CA_total"].sum() if tail["CA_total"].sum() > 0 else 1.0
    ratios = {}
    for cat in CATEGORIES_TVA:
        col = f"CA_{cat}"
        if col in tail.columns:
            ratios[cat] = tail[col].sum() / total_tail
        else:
            ratios[cat] = 0.0

    if method.startswith("Moyenne mobile"):
        base = s.tail(3)["CA_total"].mean()
        preds = [base, base, base]
    else:
        # Tendance linéaire y = a*x + b
        y = s["CA_total"].astype(float).values
        x = list(range(len(y)))
        if len(y) < 2:
            preds = [float(y[-1]), float(y[-1]), float(y[-1])]
        else:
            # calc a,b
            x_mean = sum(x) / len(x)
            y_mean = float(sum(y) / len(y))
            num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
            den = sum((xi - x_mean) ** 2 for xi in x) or 1.0
            a = num / den
            b = y_mean - a * x_mean
            x_future = [len(y) + i for i in [0, 1, 2]]
            preds = [max(0.0, a * xf + b) for xf in x_future]

    fc = pd.DataFrame({"mois": horizon, "CA_total": preds})
    # ventiler par catégories via ratio
    for cat in CATEGORIES_TVA:
        fc[f"CA_{cat}"] = fc["CA_total"] * ratios.get(cat, 0.0)
    return fc

# =========================
# APP HEADER
# =========================

st.title("Synthèse & pilotage — Helios CrossFit")

tabs = st.tabs([
    "📊 Dashboard Direction",
    "📅 Vue mensuelle",
    "📈 Comparaison mensuelle",
    "🔎 Détail produits / adhérents",
    "⬆️ Import",
])

tab_dash, tab_mensuel, tab_comp, tab_detail, tab_import = tabs

# =========================
# IMPORT TAB
# =========================

with tab_import:
    st.subheader("Import de données")
    st.markdown(
        """
        <div class="muted">
        • PDF TVA : sélectionne l’année + le mois, puis importe le PDF → remplace uniquement ce mois dans l’historique TVA.<br>
        • CSV Inscriptions : importe le CSV → remplace entièrement l’historique inscriptions (plus à jour).
        </div>
        """,
        unsafe_allow_html=True
    )

    colA, colB = st.columns(2)
    annee_courante = datetime.today().year
    annees = list(range(2022, annee_courante + 1))

    with colA:
        annee_select = st.selectbox("Année (PDF TVA)", annees, index=len(annees)-1, key="imp_annee")
    with colB:
        mois_num = st.selectbox("Mois (PDF TVA)", list(MOIS_FR.keys()), format_func=lambda x: MOIS_FR[x], key="imp_mois")

    mois_import_tva = f"{annee_select}-{mois_num:02d}"
    uploaded_pdf = st.file_uploader("Rapport TVA (PDF)", type=["pdf"], key="imp_pdf")

    if st.button("Importer / remplacer ce mois (TVA)", key="btn_imp_pdf"):
        if uploaded_pdf is None:
            st.error("Choisis un PDF.")
        else:
            with st.spinner("Extraction du PDF TVA..."):
                df_new = extract_sales_tables_from_pdf(BytesIO(uploaded_pdf.read()), forced_month=mois_import_tva)

            if df_new.empty:
                st.error("Impossible d'extraire des données depuis ce PDF.")
            else:
                df_hist = load_history_tva()
                df_autres = df_hist[df_hist["mois"] != mois_import_tva]
                df_hist_new = pd.concat([df_autres, df_new], ignore_index=True)
                save_history_tva(df_hist_new)

                st.success(
                    f"✅ Import TVA OK — {len(df_new)} lignes — CA: {df_new['total_ttc'].sum():,.2f} € — {format_mois_label(mois_import_tva)}"
                )
                show_df(df_new.head(30), height=340)

    st.divider()

    csv_file = st.file_uploader("Inscriptions (CSV)", type=["csv"], key="imp_csv")
    if st.button("Importer / remplacer l’historique inscriptions", key="btn_imp_csv"):
        if csv_file is None:
            st.error("Choisis un CSV.")
        else:
            with st.spinner("Traitement du CSV..."):
                df_abos_new = extract_abos_from_csv(BytesIO(csv_file.read()))

            if df_abos_new.empty:
                st.error("Aucune inscription exploitable trouvée dans ce fichier.")
            else:
                save_history_abos(df_abos_new)
                months = sort_months(df_abos_new["mois_creation"].astype(str).unique())
                st.success(f"✅ CSV importé — {len(df_abos_new)} lignes — {format_mois_label(months[0])} → {format_mois_label(months[-1])}")
                show_df(df_abos_new.head(30), height=340)

# =========================
# LOAD DATA
# =========================

df_hist_tva = load_history_tva()
df_abos = load_history_abos()

has_tva = not df_hist_tva.empty
has_abos = df_abos is not None and not df_abos.empty

if has_tva:
    df_hist_tva["mois"] = df_hist_tva["mois"].astype(str)
    df_hist_tva["total_ttc"] = df_hist_tva["total_ttc"].apply(to_float)
    df_hist_tva["quantite"] = df_hist_tva["quantite"].apply(to_int)
    mois_dispo = sort_months(df_hist_tva["mois"].unique())
    summary_tva = build_month_summary_tva(df_hist_tva)
    summary_tva["mois_label"] = summary_tva["mois"].apply(format_mois_label)
else:
    mois_dispo = []
    summary_tva = pd.DataFrame()

if has_abos:
    # sécurité colonnes/parse si ancien import
    if "date_debut_parsed" not in df_abos.columns and "date_debut" in df_abos.columns:
        df_abos["date_debut_parsed"] = df_abos["date_debut"].apply(parse_simple_date)
    if "date_fin_parsed" not in df_abos.columns and "date_fin" in df_abos.columns:
        df_abos["date_fin_parsed"] = df_abos["date_fin"].apply(parse_simple_date)
    for col in ["entrees_restantes", "entrees_max"]:
        if col in df_abos.columns:
            df_abos[col] = df_abos[col].apply(to_int)

# =========================
# DASHBOARD DIRECTION (global + forecast + adhérents)
# =========================

with tab_dash:
    st.subheader("Synthèse globale — Dashboard Direction")

    if not has_tva:
        st.warning("Aucune donnée TVA importée. Va dans l’onglet Import.")
    else:
        # --- Controls
        left, right = st.columns([1.4, 1.0])
        with left:
            st.markdown("<div class='muted'>Vision globale : tous les mois + prévisionnel sur 3 mois.</div>", unsafe_allow_html=True)
        with right:
            method = st.selectbox(
                "Méthode prévisionnelle",
                ["Moyenne mobile (3 mois)", "Tendance linéaire"],
                index=0,
                key="fc_method"
            )

        # --- Build forecast
        fc = forecast_next_3_months(summary_tva, method=method)
        if not fc.empty:
            fc["mois_label"] = fc["mois"].apply(format_mois_label)

        # --- KPIs (dernier mois + delta + cumuls)
        last = summary_tva.sort_values("mois").iloc[-1]
        last_mois = last["mois"]
        last_label = last["mois_label"]
        ca_last = float(last["CA_total"])
        qt_last = int(last["Qt_total"])

        prev = summary_tva.sort_values("mois").iloc[-2] if len(summary_tva) >= 2 else None
        ca_prev = float(prev["CA_total"]) if prev is not None else None
        delta_abs = (ca_last - ca_prev) if (ca_prev is not None) else None
        delta_pct = ((delta_abs / ca_prev) * 100) if (ca_prev not in (None, 0)) else None

        ca_total_all = float(summary_tva["CA_total"].sum())
        ca_avg = float(summary_tva["CA_total"].mean())

        # Abos (projection / actifs)
        today = datetime.today().date()
        sub_active, carnet_active = compute_active_members(df_abos, today) if has_abos else (pd.DataFrame(), pd.DataFrame())
        ca_proj_next, next_label = compute_subscription_projection_next_month(df_abos, today) if has_abos else (0.0, None)

        nb_sub_active = int(len(sub_active))
        nb_carnet_active = int(len(carnet_active))
        nb_members_total = nb_sub_active + nb_carnet_active  # état des lieux "adhérents" élargi (abos + carnets actifs)

        # --- KPI Cards
        # Card 1 (CA dernier mois + delta)
        delta_html = ""
        if delta_abs is not None and delta_pct is not None:
            badge = "badgeUp" if delta_abs >= 0 else "badgeDown"
            sign = "+" if delta_abs >= 0 else ""
            delta_html = f"<div class='kpiDelta'><span class='{badge}'>{sign}{delta_abs:,.0f} € ({sign}{delta_pct:.1f}%)</span><span class='muted'>vs mois-1</span></div>"
        else:
            delta_html = "<div class='kpiDelta'><span class='muted'>Δ non disponible</span></div>"

        st.markdown(
            f"""
            <div class="kpiGrid">
              <div class="kpiCard">
                <div class="kpiTitle">CA total (TVA) — {last_label}</div>
                <div class="kpiValue">{ca_last:,.0f} €</div>
                {delta_html}
              </div>
              <div class="kpiCard">
                <div class="kpiTitle">Quantités vendues (TVA) — {last_label}</div>
                <div class="kpiValue">{qt_last}</div>
                <div class="kpiDelta"><span class="muted">Moyenne CA mensuelle :</span><span class="muted">{ca_avg:,.0f} €</span></div>
              </div>
              <div class="kpiCard">
                <div class="kpiTitle">CA cumulé (tous mois TVA)</div>
                <div class="kpiValue">{ca_total_all:,.0f} €</div>
                <div class="kpiDelta"><span class="muted">Nb mois :</span><span class="muted">{len(summary_tva)}</span></div>
              </div>
              <div class="kpiCard">
                <div class="kpiTitle">Adhérents actifs (instant T)</div>
                <div class="kpiValue">{nb_members_total}</div>
                <div class="kpiDelta"><span class="muted">{nb_sub_active} abos récurrents</span><span class="muted">•</span><span class="muted">{nb_carnet_active} carnets actifs</span></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown("<div class='section'></div>", unsafe_allow_html=True)

        # --- Global timeline (CA total + forecast)
        hist_line = summary_tva[["mois_label", "CA_total"]].rename(columns={"CA_total": "CA"})
        fc_line = fc[["mois_label", "CA_total"]].rename(columns={"CA_total": "CA"}) if not fc.empty else pd.DataFrame(columns=["mois_label", "CA"])

        chart = line_with_forecast(hist_line, fc_line, x="mois_label", y="CA", title="CA total (historique) + prévisionnel (3 mois)")
        show_chart(alt_base() + chart)

        # --- Catégories : comparaison mensuelle claire (grouped bars) + forecast
        # Build long format for historical categories
        long_hist = []
        for _, r in summary_tva.iterrows():
            for cat in CATEGORIES_TVA:
                long_hist.append({
                    "mois_label": r["mois_label"],
                    "Période": "Historique",
                    "Catégorie": cat,
                    "CA": float(r.get(f"CA_{cat}", 0.0))
                })
        df_long_hist = pd.DataFrame(long_hist)

        # Forecast in long format
        df_long_fc = pd.DataFrame()
        if not fc.empty:
            long_fc = []
            for _, r in fc.iterrows():
                for cat in CATEGORIES_TVA:
                    long_fc.append({
                        "mois_label": r["mois_label"],
                        "Période": "Prévision",
                        "Catégorie": cat,
                        "CA": float(r.get(f"CA_{cat}", 0.0))
                    })
            df_long_fc = pd.DataFrame(long_fc)

        # For readability, show last N months + forecast
        n_show = min(6, len(mois_dispo))
        months_show = [format_mois_label(m) for m in mois_dispo[-n_show:]]
        if not fc.empty:
            months_show += list(fc["mois_label"].values)

        df_cat_plot = pd.concat([df_long_hist, df_long_fc], ignore_index=True)
        df_cat_plot = df_cat_plot[df_cat_plot["mois_label"].isin(months_show)]

        # We want grouped-by-category per month, but also differentiate historique vs prévision.
        # We'll encode "Série" = Catégorie, and opacity based on "Période"
        if not df_cat_plot.empty:
            ch_cat = (
                alt.Chart(df_cat_plot)
                .mark_bar(cornerRadiusTopLeft=7, cornerRadiusTopRight=7)
                .encode(
                    x=alt.X("mois_label:N", title=None, sort=months_show),
                    xOffset=alt.XOffset("Catégorie:N"),
                    y=alt.Y("CA:Q", title="€"),
                    color=alt.Color("Catégorie:N", legend=alt.Legend(title=""), scale=alt.Scale(scheme="tableau10")),
                    opacity=alt.condition(alt.datum.Période == "Historique", alt.value(1.0), alt.value(0.45)),
                    tooltip=["mois_label:N", "Période:N", "Catégorie:N", alt.Tooltip("CA:Q", format=",.0f")]
                )
                .properties(height=300, title="CA par catégorie — vue globale (derniers mois + prévision)")
            )
            show_chart(alt_base() + ch_cat)

        # --- Projection CA abonnements (mois suivant) — KPI direction
        st.markdown("<div class='section'></div>", unsafe_allow_html=True)
        st.subheader("Récurrence — Abonnements récurrents (instant T)")

        if not has_abos:
            st.info("Pas de CSV inscriptions importé : impossible de calculer abonnements actifs / projection.")
        else:
            st.markdown(
                f"<div class='muted'>Exclus : carnets 10 (Liberté), drop-in, événements. Uniquement abonnements récurrents (Reconduction ≠ Non).</div>",
                unsafe_allow_html=True
            )

            col1, col2, col3 = st.columns(3)
            col1.metric("Abonnements récurrents actifs", nb_sub_active)
            col2.metric("CA mensuel estimé (actifs)", f"{sub_active['prix_effectif'].apply(to_float).sum():,.0f} €".replace(",", " "))
            if next_label:
                col3.metric(f"CA projeté — {next_label}", f"{ca_proj_next:,.0f} €".replace(",", " "))
            else:
                col3.metric("CA projeté (mois suivant)", f"{ca_proj_next:,.0f} €".replace(",", " "))

            # Distribution by offer
            if not sub_active.empty:
                dist = (
                    sub_active.groupby("sous_type", as_index=False)
                    .agg(Nb=("offre", "count"), CA=("prix_effectif", "sum"))
                    .sort_values("CA", ascending=False)
                )
                dist["%"] = (dist["Nb"] / dist["Nb"].sum() * 100).round(1)

                colA, colB = st.columns([1.0, 1.0])
                with colA:
                    ch = donut(dist.rename(columns={"sous_type": "Type", "CA": "CA"}), "Type", "CA", "Répartition des abonnements actifs (CA)")
                    if ch is not None:
                        show_chart(alt_base() + ch)
                with colB:
                    show_df(dist, height=320)

        # --- Adhérents (détail)
        st.markdown("<div class='section'></div>", unsafe_allow_html=True)
        st.subheader("Adhérents — détail (instant T)")

        if not has_abos:
            st.info("Pas de CSV inscriptions importé.")
        else:
            with st.expander("Définition & règles (clique pour lire)"):
                st.markdown(
                    """
                    - **Abonnements actifs** : type_contrat=ABONNEMENT, statut VALIDATED, date_debut ≤ aujourd’hui, date_fin vide ou ≥ aujourd’hui.  
                      + **Récurrents** : Reconduction ≠ Non (vide = considéré récurrent).  
                    - **Carnets 10 actifs** : type_contrat=CARTE_10 (Liberté), statut VALIDATED, entrées_restantes > 0.  
                    - **Exclus** : drop-in, events.
                    """
                )

            # Toggle: include carnets in "adhérents"
            incl_carnets = st.checkbox("Inclure les carnets 10 dans le total adhérents", value=True, key="incl_carnets_dash")
            total_now = nb_sub_active + (nb_carnet_active if incl_carnets else 0)
            st.metric("Adhérents actifs (selon sélection)", total_now)

            colX, colY = st.columns(2)
            with colX:
                st.markdown("#### Abonnements actifs (récurrents)")
                if sub_active.empty:
                    st.info("Aucun abonnement actif récurrent.")
                else:
                    cols = [c for c in ["prenom","nom","email","telephone","offre","sous_type","prix_effectif","date_debut","date_fin","reconduction","statut"] if c in sub_active.columns]
                    show_df(sub_active[cols].sort_values(["sous_type","nom","prenom"], na_position="last"), height=360)

            with colY:
                st.markdown("#### Carnets 10 actifs (entrées restantes > 0)")
                if not incl_carnets:
                    st.info("Carnets exclus de la vue.")
                else:
                    if carnet_active.empty:
                        st.info("Aucun carnet actif détecté.")
                    else:
                        cols = [c for c in ["prenom","nom","email","telephone","offre","sous_type","entrees_restantes","entrees_max","prix_effectif","date_debut","date_fin","statut"] if c in carnet_active.columns]
                        show_df(carnet_active[cols].sort_values(["entrees_restantes","nom"], ascending=[False, True], na_position="last"), height=360)

# =========================
# VUE MENSUELLE (focus)
# =========================

with tab_mensuel:
    st.subheader("Vue mensuelle (TVA)")

    if not has_tva:
        st.warning("Aucune donnée TVA importée.")
    else:
        mois_focus = st.selectbox("Mois", mois_dispo, index=len(mois_dispo)-1, format_func=format_mois_label, key="mens_mois")
        df_m = df_hist_tva[df_hist_tva["mois"] == mois_focus].copy()
        ca = df_m["total_ttc"].sum()
        qt = df_m["quantite"].sum()

        st.markdown(
            f"""
            <div class="kpiGrid">
              <div class="kpiCard">
                <div class="kpiTitle">CA total — {format_mois_label(mois_focus)}</div>
                <div class="kpiValue">{ca:,.0f} €</div>
                <div class="kpiDelta"><span class="muted">Nb lignes :</span><span class="muted">{len(df_m)}</span></div>
              </div>
              <div class="kpiCard">
                <div class="kpiTitle">Quantités vendues — {format_mois_label(mois_focus)}</div>
                <div class="kpiValue">{int(qt)}</div>
                <div class="kpiDelta"><span class="muted">—</span></div>
              </div>
              <div class="kpiCard">
                <div class="kpiTitle">Top catégorie (CA)</div>
                <div class="kpiValue">
                  {df_m.groupby("categorie")["total_ttc"].sum().sort_values(ascending=False).index[0] if not df_m.empty else "N/A"}
                </div>
                <div class="kpiDelta"><span class="muted">—</span></div>
              </div>
              <div class="kpiCard">
                <div class="kpiTitle">Mois</div>
                <div class="kpiValue">{format_mois_label(mois_focus)}</div>
                <div class="kpiDelta"><span class="muted">{mois_focus}</span></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        df_cat = (
            df_m.groupby("categorie", as_index=False)
            .agg(CA=("total_ttc", "sum"), Quantites=("quantite", "sum"))
            .sort_values("CA", ascending=False)
        )
        df_cat["%"] = (df_cat["CA"] / df_cat["CA"].sum() * 100).round(1) if df_cat["CA"].sum() > 0 else 0.0

        col1, col2 = st.columns([1.0, 1.0])
        with col1:
            ch = donut(df_cat.rename(columns={"categorie": "Catégorie"}), "Catégorie", "CA", "Structure du CA (mois)")
            if ch is not None:
                show_chart(alt_base() + ch)
        with col2:
            show_df(df_cat, height=320)

# =========================
# COMPARAISON MENSUELLE
# =========================

with tab_comp:
    st.subheader("Comparaison mensuelle (TVA)")

    if not has_tva or len(mois_dispo) < 2:
        st.warning("Il faut au moins 2 mois TVA importés.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            m_start = st.selectbox("Mois début", mois_dispo, index=max(0, len(mois_dispo)-6), format_func=format_mois_label, key="cmp_start")
        with col2:
            m_end = st.selectbox("Mois fin", mois_dispo, index=len(mois_dispo)-1, format_func=format_mois_label, key="cmp_end")

        i1 = mois_dispo.index(m_start)
        i2 = mois_dispo.index(m_end)
        if i1 > i2:
            st.error("Le mois de début doit être avant le mois de fin.")
        else:
            months = mois_dispo[i1:i2+1]
            df_range = summary_tva[summary_tva["mois"].isin(months)].copy()

            # CA total
            df_line = df_range[["mois_label", "CA_total"]].rename(columns={"CA_total": "CA"})
            ch = (
                alt.Chart(df_line)
                .mark_line(point=alt.OverlayMarkDef(size=70), strokeWidth=2.6)
                .encode(
                    x=alt.X("mois_label:N", title=None, sort=list(df_line["mois_label"])),
                    y=alt.Y("CA:Q", title="€"),
                    tooltip=["mois_label:N", alt.Tooltip("CA:Q", format=",.0f")]
                )
                .properties(height=280, title="CA total — période sélectionnée")
            )
            show_chart(alt_base() + ch)

            # comparaison catégories (grouped bars)
            cat_long = []
            for _, r in df_range.iterrows():
                for cat in CATEGORIES_TVA:
                    cat_long.append({"mois_label": r["mois_label"], "Catégorie": cat, "CA": float(r.get(f"CA_{cat}", 0.0))})
            df_cat_long = pd.DataFrame(cat_long)

            ch2 = grouped_bars(df_cat_long, "mois_label", "Catégorie", "CA", "CA par catégorie — comparaison")
            if ch2 is not None:
                show_chart(alt_base() + ch2)

# =========================
# DETAIL (produits + adhérents)
# =========================

with tab_detail:
    st.subheader("Détails")

    # --- Produits
    st.markdown("### Produits (TVA)")
    if not has_tva:
        st.info("Pas de TVA importé.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            cat_det = st.selectbox("Catégorie", CATEGORIES_TVA, key="det_cat")
        with col2:
            mois_det = st.selectbox("Mois", mois_dispo, index=len(mois_dispo)-1, format_func=format_mois_label, key="det_mois")

        df_det = df_hist_tva[(df_hist_tva["categorie"] == cat_det) & (df_hist_tva["mois"] == mois_det)].copy()
        if df_det.empty:
            st.info("Aucune donnée.")
        else:
            top = (
                df_det.groupby("designation", as_index=False)
                .agg(CA=("total_ttc", "sum"), Quantites=("quantite", "sum"))
                .sort_values("CA", ascending=False)
            )
            show_df(top, height=360)

    st.markdown("---")
    st.markdown("### Adhérents (CSV)")
    if not has_abos:
        st.info("Pas de CSV inscriptions importé.")
    else:
        today = datetime.today().date()
        sub_active, carnet_active = compute_active_members(df_abos, today)

        st.markdown("<div class='muted'>Vue détaillée à l’instant T.</div>", unsafe_allow_html=True)

        colA, colB, colC = st.columns(3)
        colA.metric("Abonnements actifs récurrents", int(len(sub_active)))
        colB.metric("Carnets 10 actifs", int(len(carnet_active)))
        colC.metric("Total (abos + carnets)", int(len(sub_active) + len(carnet_active)))

        st.markdown("#### Abonnements actifs récurrents — détail")
        if sub_active.empty:
            st.info("Aucun.")
        else:
            cols = [c for c in ["prenom","nom","email","telephone","offre","sous_type","prix_effectif","date_debut","date_fin","reconduction","statut"] if c in sub_active.columns]
            show_df(sub_active[cols].sort_values(["sous_type","nom","prenom"], na_position="last"), height=420)

        st.markdown("#### Carnets 10 actifs — détail")
        if carnet_active.empty:
            st.info("Aucun.")
        else:
            cols = [c for c in ["prenom","nom","email","telephone","offre","sous_type","entrees_restantes","entrees_max","prix_effectif","statut"] if c in carnet_active.columns]
            show_df(carnet_active[cols].sort_values(["entrees_restantes","nom"], ascending=[False, True], na_position="last"), height=420)
