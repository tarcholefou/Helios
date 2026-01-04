# app.py — Helios Reporting (TVA PDF + Inscriptions CSV)
# Dashboard Direction (pilotage box) :
# - MRR / membres actifs / ARPU / churn / net adds (CSV)
# - Drivers de CA (waterfall) (TVA)
# - Retail efficacité (TVA)
# - Forecast 3 mois basé sur MRR + hypothèses churn/acquisition
# - Alertes (règles direction)

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
HISTORY_TVA_FILE = os.path.join(DATA_DIR, "history_tva.csv")
HISTORY_ABOS_FILE = os.path.join(DATA_DIR, "history_abos.csv")
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
# PAGE / STYLE (moderne)
# =========================

st.set_page_config(page_title="Helios — Cockpit", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1450px; }
      h1,h2,h3,h4 { font-family: -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif !important; }

      /* Tabs pills */
      .stTabs [data-baseweb="tab-list"] { gap: .5rem; }
      .stTabs [data-baseweb="tab"] {
        padding: .42rem 1.05rem;
        border-radius: 999px;
        background: rgba(2,6,23,.55);
        border: 1px solid rgba(148,163,184,.18);
      }
      .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #7c3aed, #22c55e) !important;
        color: white !important;
      }

      /* KPI cards */
      .kpiGrid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
      @media (max-width: 1200px){ .kpiGrid{ grid-template-columns: repeat(2, 1fr);} }
      @media (max-width: 700px){ .kpiGrid{ grid-template-columns: repeat(1, 1fr);} }

      .kpiCard {
        background:
          radial-gradient(1000px 420px at 20% 0%, rgba(124,58,237,.18), transparent 55%),
          radial-gradient(900px 420px at 80% 10%, rgba(34,197,94,.14), transparent 55%),
          linear-gradient(180deg, rgba(2,6,23,.72), rgba(2,6,23,.92));
        border: 1px solid rgba(148,163,184,.18);
        box-shadow: 0 18px 40px rgba(0,0,0,.35);
        border-radius: 18px;
        padding: 16px 16px 14px 16px;
      }
      .kpiTitle { color: rgba(226,232,240,.86); font-size: .92rem; margin-bottom: 6px; }
      .kpiValue { font-size: 2.05rem; font-weight: 750; letter-spacing: -0.02em; }
      .kpiDelta { margin-top: 8px; display: inline-flex; gap: 8px; align-items: center; font-size: .95rem; }
      .badgeUp {
        background: rgba(34,197,94,.16);
        border: 1px solid rgba(34,197,94,.33);
        color: rgb(74,222,128);
        padding: 3px 10px;
        border-radius: 999px;
        font-weight: 650;
      }
      .badgeDown {
        background: rgba(239,68,68,.14);
        border: 1px solid rgba(239,68,68,.33);
        color: rgb(248,113,113);
        padding: 3px 10px;
        border-radius: 999px;
        font-weight: 650;
      }
      .muted { color: rgba(226,232,240,.72); font-size: .95rem; }
      .section { margin-top: 12px; }

      /* little cards */
      .miniCard {
        background: rgba(2,6,23,.55);
        border: 1px solid rgba(148,163,184,.18);
        border-radius: 16px;
        padding: 14px;
      }

      /* charts tighter */
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
# ALTAIR THEME
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
    return (arcs + txt).properties(height=260, title=title)

def line_chart(df, x, y, title="", height=260):
    if df.empty:
        return None
    return (
        alt.Chart(df)
        .mark_line(point=alt.OverlayMarkDef(size=65), strokeWidth=2.6)
        .encode(
            x=alt.X(f"{x}:N", title=None, sort=list(df[x])),
            y=alt.Y(f"{y}:Q", title="€"),
            tooltip=[x, alt.Tooltip(y, format=",.0f")]
        )
        .properties(height=height, title=title)
    )

def grouped_bars(df, x, series, y, title="", height=240):
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
        .properties(height=height, title=title)
    )

def waterfall_drivers(df, x="driver", y="delta", title="", height=230):
    if df.empty:
        return None
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8)
        .encode(
            x=alt.X(f"{x}:N", title=None, sort=None),
            y=alt.Y(f"{y}:Q", title="Δ €"),
            color=alt.condition(alt.datum.delta >= 0, alt.value("#22c55e"), alt.value("#ef4444")),
            tooltip=[x, alt.Tooltip(y, format=",.0f")]
        )
        .properties(height=height, title=title)
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
    out["mois_label"] = out["mois"].apply(format_mois_label)
    return out


# =========================
# CSV INSCRIPTIONS — CLASSIF
# =========================

def classify_contrat(offre: str):
    """
    Règles :
    - "Liberté" = Carnet 10 séances (pas abonnement)
    - "Drop in" exclu
    - Events exclus
    - Abonnements = offres normales
    """
    s = (offre or "").lower().strip()

    if any(k in s for k in ["soirée", "soiree", "inauguration", "raclette", "event", "offre de rentrée", "offre de rentree"]):
        return ("EVENT", offre)

    if "drop" in s:
        return ("EXCLU", "Drop in")

    if "liberté" in s or "liberte" in s:
        return ("CARTE_10", "Carnet 10 séances")

    abo_keywords = ["essentiel", "evolution", "premium", "hyrox", "1x semaine", "1 x semaine", "ascension"]
    if any(k in s for k in abo_keywords):
        return ("ABONNEMENT", offre)

    return ("EXCLU", offre)

def extract_abos_from_csv(file_obj: BytesIO) -> pd.DataFrame:
    df_raw = pd.read_csv(file_obj)
    df_raw.columns = [c.strip() for c in df_raw.columns]

    # Détection robuste "date création"
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

    # Identifiant (pour cohortes / churn) — email en priorité, sinon téléphone
    df["email_norm"] = df.get("email", "").astype(str).str.strip().str.lower()
    df["tel_norm"] = df.get("telephone", "").astype(str).str.replace(" ", "").str.strip()
    df["member_key"] = df.apply(
        lambda r: r["email_norm"] if r["email_norm"] not in ("", "nan", "none") else r["tel_norm"],
        axis=1
    )
    # clé contrat (même personne + même offre + date début)
    df["contract_key"] = df.apply(
        lambda r: f"{r.get('member_key','')}|{r.get('sous_type','')}|{r.get('date_debut_parsed', '')}",
        axis=1
    )
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
# ABOS ACTIFS + CHURN + FORECAST
# =========================

def month_end(ym: str) -> date:
    dt = datetime.strptime(ym, "%Y-%m")
    if dt.month == 12:
        nxt = date(dt.year + 1, 1, 1)
    else:
        nxt = date(dt.year, dt.month + 1, 1)
    return nxt - timedelta(days=1)

def compute_active_recurring_subs_at(df_abos: pd.DataFrame, ref_dt: date) -> pd.DataFrame:
    """
    Abonnements actifs récurrents uniquement (direction) :
    - type_contrat=ABONNEMENT
    - Reconduction ≠ Non (vide = récurrent)
    - statut VALIDATED (ou FUTURE si chevauche)
    - date_debut <= ref_dt <= date_fin (ou date_fin vide)
    """
    if df_abos is None or df_abos.empty:
        return pd.DataFrame()

    df = df_abos.copy()
    for col in ["type_contrat","reconduction","statut","date_debut_parsed","date_fin_parsed","prix_effectif","contract_key","sous_type","offre"]:
        if col not in df.columns:
            df[col] = None

    df["reconduction_norm"] = df["reconduction"].astype(str).str.strip().str.lower()
    recurring = df["reconduction_norm"] != "non"
    df["statut_norm"] = df["statut"].astype(str).str.upper()

    sub = df[(df["type_contrat"] == "ABONNEMENT") & recurring].copy()
    sub = sub[sub["date_debut_parsed"].notna()]
    sub_act = sub[
        (sub["date_debut_parsed"] <= ref_dt) &
        (sub["date_fin_parsed"].isna() | (sub["date_fin_parsed"] >= ref_dt)) &
        (sub["statut_norm"].isin(["VALIDATED", "FUTURE"]))
    ].copy()

    sub_act["prix_effectif"] = sub_act["prix_effectif"].apply(to_float)
    return sub_act

def compute_churn_metrics(df_abos: pd.DataFrame, months: list[str]) -> pd.DataFrame:
    """
    Churn approximé par "cohorte active fin de mois" :
    - Active fin mois M-1
    - Active fin mois M
    Churn M = (perdus) / (actifs M-1)
    New adds M = (nouveaux dans M) = actifs M - intersection
    Net adds = new - lost
    """
    if df_abos is None or df_abos.empty or len(months) < 2:
        return pd.DataFrame()

    rows = []
    prev_set = None
    prev_count = None

    for ym in months:
        ref = month_end(ym)
        act = compute_active_recurring_subs_at(df_abos, ref_dt=ref)
        keys = set(act["contract_key"].astype(str).tolist())
        count = len(keys)
        mrr = act["prix_effectif"].sum()

        if prev_set is None:
            rows.append({"mois": ym, "actifs": count, "mrr": mrr, "new": None, "lost": None, "net_adds": None, "churn_pct": None, "arpu": (mrr / count) if count else 0.0})
        else:
            retained = len(keys & prev_set)
            lost = len(prev_set - keys)
            new = len(keys - prev_set)
            churn = (lost / prev_count * 100) if prev_count else None
            net = new - lost
            rows.append({"mois": ym, "actifs": count, "mrr": mrr, "new": new, "lost": lost, "net_adds": net, "churn_pct": churn, "arpu": (mrr / count) if count else 0.0})

        prev_set = keys
        prev_count = count

    df = pd.DataFrame(rows)
    df["mois_label"] = df["mois"].apply(format_mois_label)
    return df

def forecast_mrr_3_months(current_actifs: int, current_mrr: float, arpu: float, churn_pct: float, new_adds: int, start_month: str):
    """
    Forecast simple direction :
    MRR(t+1) = MRR(t) * (1 - churn) + new_adds * ARPU
    Actifs(t+1) = Actifs(t) * (1 - churn) + new_adds
    sur 3 mois
    """
    churn = max(0.0, churn_pct) / 100.0
    rows = []
    actifs = float(current_actifs)
    mrr = float(current_mrr)

    for i in [1, 2, 3]:
        m = month_add(start_month, i)
        # pertes
        lost = actifs * churn
        actifs = max(0.0, actifs - lost + new_adds)
        mrr = max(0.0, mrr * (1 - churn) + new_adds * arpu)
        rows.append({"mois": m, "actifs": round(actifs), "mrr": mrr})

    df = pd.DataFrame(rows)
    df["mois_label"] = df["mois"].apply(format_mois_label)
    return df


# =========================
# APP HEADER
# =========================

st.title("Helios — Cockpit de pilotage")

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
        <b>TVA PDF</b> : tu choisis année + mois, puis tu importes → l’app remplace uniquement ce mois (pas d’écrasement global).<br>
        <b>CSV inscriptions</b> : tu importes le CSV → l’app remplace l’historique inscriptions (logique “plus à jour”).
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
else:
    mois_dispo = []
    summary_tva = pd.DataFrame()

if has_abos:
    # Parse si import plus ancien
    if "date_debut_parsed" not in df_abos.columns and "date_debut" in df_abos.columns:
        df_abos["date_debut_parsed"] = df_abos["date_debut"].apply(parse_simple_date)
    if "date_fin_parsed" not in df_abos.columns and "date_fin" in df_abos.columns:
        df_abos["date_fin_parsed"] = df_abos["date_fin"].apply(parse_simple_date)
    for col in ["prix_effectif", "prix_offre", "prix_perso"]:
        if col in df_abos.columns:
            df_abos[col] = df_abos[col].apply(to_float)
    # fallback si l’identifiant n’existe pas (ancien fichier)
    if "email_norm" not in df_abos.columns:
        df_abos["email_norm"] = df_abos.get("email", "").astype(str).str.strip().str.lower()
    if "tel_norm" not in df_abos.columns:
        df_abos["tel_norm"] = df_abos.get("telephone", "").astype(str).str.replace(" ", "").str.strip()
    if "member_key" not in df_abos.columns:
        df_abos["member_key"] = df_abos.apply(
            lambda r: r["email_norm"] if r["email_norm"] not in ("", "nan", "none") else r["tel_norm"],
            axis=1
        )
    if "contract_key" not in df_abos.columns:
        df_abos["contract_key"] = df_abos.apply(
            lambda r: f"{r.get('member_key','')}|{r.get('sous_type','')}|{r.get('date_debut_parsed', '')}",
            axis=1
        )


# =========================
# DASHBOARD DIRECTION
# =========================

with tab_dash:
    st.subheader("Dashboard Direction — cockpit")

    if not has_tva:
        st.warning("Aucune donnée TVA importée. Va dans l’onglet Import.")
        st.stop()

    # ====== Paramètres direction (sliders)
    with st.expander("Paramètres direction (seuils & hypothèses)", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            churn_alert = st.slider("Alerte churn (%)", 1.0, 25.0, 7.0, 0.5)
        with c2:
            arpu_drop_alert = st.slider("Alerte baisse ARPU (%)", 1.0, 40.0, 10.0, 1.0)
        with c3:
            abos_share_alert = st.slider("Alerte % CA Abos/Cartes min", 10.0, 95.0, 75.0, 1.0)
        with c4:
            top1_retail_alert = st.slider("Alerte dépendance Top1 retail (%)", 10.0, 80.0, 35.0, 1.0)

    # ====== Focus mois (mais synthèse globale visible)
    mois_focus = st.selectbox(
        "Mois analysé (pour les KPI du mois)",
        mois_dispo,
        index=len(mois_dispo)-1,
        format_func=format_mois_label,
        key="dir_mois"
    )
    idx = mois_dispo.index(mois_focus)
    mois_prev = mois_dispo[idx-1] if idx >= 1 else None

    row_m = summary_tva[summary_tva["mois"] == mois_focus].iloc[0]
    ca_m = float(row_m["CA_total"])
    abos_ca_m = float(row_m.get("CA_Abonnements / cartes", 0.0))
    retail_ca_m = ca_m - abos_ca_m
    share_abos = (abos_ca_m / ca_m * 100) if ca_m else 0.0

    if mois_prev:
        row_p = summary_tva[summary_tva["mois"] == mois_prev].iloc[0]
        ca_p = float(row_p["CA_total"])
        delta_ca = ca_m - ca_p
        delta_pct = (delta_ca / ca_p * 100) if ca_p else None
    else:
        ca_p, delta_ca, delta_pct = None, None, None

    # ====== CSV (MRR / actifs / churn / net adds)
    today = datetime.today().date()
    sub_active_now = compute_active_recurring_subs_at(df_abos, today) if has_abos else pd.DataFrame()
    actifs_now = int(len(sub_active_now))
    mrr_now = float(sub_active_now["prix_effectif"].sum()) if not sub_active_now.empty else 0.0
    arpu_now = (mrr_now / actifs_now) if actifs_now else 0.0

    # Churn historique (sur les mois TVA disponibles, pour coller au pilotage mensuel)
    churn_df = pd.DataFrame()
    if has_abos and len(mois_dispo) >= 2:
        churn_df = compute_churn_metrics(df_abos, mois_dispo)
    churn_last = None
    arpu_prev = None
    net_adds_last = None
    if not churn_df.empty:
        # prendre la dernière ligne qui a churn calculé
        last_churn_row = churn_df.dropna(subset=["churn_pct"]).tail(1)
        if not last_churn_row.empty:
            churn_last = float(last_churn_row["churn_pct"].iloc[0])
            net_adds_last = int(last_churn_row["net_adds"].iloc[0])

        # arpu vs mois-1 (dans churn_df)
        last2 = churn_df.tail(2)
        if len(last2) == 2:
            arpu_prev = float(last2["arpu"].iloc[0])

    # ====== KPI Cards direction (4)
    def badge_delta(val_abs, val_pct):
        if val_abs is None or val_pct is None:
            return "<div class='kpiDelta'><span class='muted'>Δ non dispo</span></div>"
        cls = "badgeUp" if val_abs >= 0 else "badgeDown"
        sign = "+" if val_abs >= 0 else ""
        return f"<div class='kpiDelta'><span class='{cls}'>{sign}{val_abs:,.0f} € ({sign}{val_pct:.1f}%)</span><span class='muted'>vs mois-1</span></div>"

    st.markdown(
        f"""
        <div class="kpiGrid">
          <div class="kpiCard">
            <div class="kpiTitle">CA total (TVA) — {format_mois_label(mois_focus)}</div>
            <div class="kpiValue">{ca_m:,.0f} €</div>
            {badge_delta(delta_ca, delta_pct) if mois_prev else "<div class='kpiDelta'><span class='muted'>Δ non dispo</span></div>"}
          </div>
          <div class="kpiCard">
            <div class="kpiTitle">MRR (abos récurrents actifs) — instant T</div>
            <div class="kpiValue">{mrr_now:,.0f} €</div>
            <div class="kpiDelta"><span class="muted">Actifs :</span><span class="muted">{actifs_now}</span></div>
          </div>
          <div class="kpiCard">
            <div class="kpiTitle">ARPU (MRR / abonnés) — instant T</div>
            <div class="kpiValue">{arpu_now:,.0f} €</div>
            {"<div class='kpiDelta'><span class='muted'>Δ ARPU non dispo</span></div>" if arpu_prev is None else (
                f"<div class='kpiDelta'><span class='{('badgeDown' if (arpu_now < arpu_prev) else 'badgeUp')}'>{(arpu_now-arpu_prev):+.0f} €</span><span class='muted'>vs mois-1</span></div>"
            )}
          </div>
          <div class="kpiCard">
            <div class="kpiTitle">Churn (approx fin de mois)</div>
            <div class="kpiValue">{('N/A' if churn_last is None else f'{churn_last:.1f}%')}</div>
            <div class="kpiDelta"><span class="muted">Net adds :</span><span class="muted">{('N/A' if net_adds_last is None else net_adds_last)}</span></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)

    # ====== Ligne CA global (tous mois) + focus
    df_line = summary_tva[["mois_label", "CA_total"]].rename(columns={"CA_total": "CA"})
    ch = line_chart(df_line, "mois_label", "CA", "CA total — historique (TVA)", height=240)
    if ch is not None:
        show_chart(alt_base() + ch)

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)

    # ====== Drivers de CA (waterfall) : delta par catégorie entre mois_focus et mois_prev
    st.markdown("### Drivers du CA (Δ mois vs mois-1)")
    if not mois_prev:
        st.info("Il faut au moins 2 mois importés pour calculer les drivers.")
    else:
        drivers = []
        for cat in CATEGORIES_TVA:
            d = float(row_m.get(f"CA_{cat}", 0.0)) - float(row_p.get(f"CA_{cat}", 0.0))
            drivers.append({"driver": cat, "delta": d})
        df_drv = pd.DataFrame(drivers)

        col1, col2 = st.columns([1.0, 1.0])
        with col1:
            ch_drv = waterfall_drivers(df_drv, title=f"Δ CA par catégorie — {format_mois_label(mois_prev)} → {format_mois_label(mois_focus)}", height=230)
            if ch_drv is not None:
                show_chart(alt_base() + ch_drv)
        with col2:
            df_drv2 = df_drv.copy()
            df_drv2["delta"] = df_drv2["delta"].round(0)
            show_df(df_drv2.sort_values("delta", ascending=False), height=240)

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)

    # ====== Mix du CA (donut) + alertes structure
    st.markdown("### Structure du CA (TVA)")
    df_cat = pd.DataFrame([{
        "Catégorie": cat,
        "CA": float(row_m.get(f"CA_{cat}", 0.0))
    } for cat in CATEGORIES_TVA]).sort_values("CA", ascending=False)

    col1, col2 = st.columns([1.0, 1.0])
    with col1:
        ch_mix = donut(df_cat, "Catégorie", "CA", title=f"Mix CA — {format_mois_label(mois_focus)}")
        if ch_mix is not None:
            show_chart(alt_base() + ch_mix)
    with col2:
        df_cat["%"] = (df_cat["CA"] / df_cat["CA"].sum() * 100).round(1) if df_cat["CA"].sum() else 0
        show_df(df_cat, height=260)

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)

    # ====== Retail efficacité (TVA) : tout sauf Abonnements/cartes
    st.markdown("### Retail — efficacité (TVA)")
    df_m_lines = df_hist_tva[df_hist_tva["mois"] == mois_focus].copy()
    df_retail = df_m_lines[df_m_lines["categorie"] != "Abonnements / cartes"].copy()

    retail_share = (retail_ca_m / ca_m * 100) if ca_m else 0.0
    top1_share = 0.0
    top1_name = None

    if not df_retail.empty:
        top_prod = (
            df_retail.groupby("designation", as_index=False)
            .agg(CA=("total_ttc", "sum"), Qt=("quantite", "sum"))
            .sort_values("CA", ascending=False)
        )
        if not top_prod.empty and float(top_prod["CA"].sum()) > 0:
            top1_name = str(top_prod.iloc[0]["designation"])
            top1_share = float(top_prod.iloc[0]["CA"]) / float(top_prod["CA"].sum()) * 100

    colA, colB, colC, colD = st.columns(4)
    colA.metric("CA retail", f"{retail_ca_m:,.0f} €".replace(",", " "))
    colB.metric("% retail du CA", f"{retail_share:.1f}%")
    colC.metric("Produit #1 retail", (top1_name[:24] + "…") if top1_name and len(top1_name) > 25 else (top1_name or "N/A"))
    colD.metric("Dépendance Top1 (retail)", f"{top1_share:.1f}%")

    col1, col2 = st.columns([1.2, 1.0])
    with col1:
        if df_retail.empty:
            st.info("Aucune vente retail sur ce mois.")
        else:
            top5 = (
                df_retail.groupby("designation", as_index=False)
                .agg(CA=("total_ttc", "sum"))
                .sort_values("CA", ascending=False)
                .head(8)
            )
            top5["mois"] = format_mois_label(mois_focus)
            ch_top = (
                alt.Chart(top5)
                .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8)
                .encode(
                    y=alt.Y("designation:N", title=None, sort="-x"),
                    x=alt.X("CA:Q", title="€"),
                    color=alt.value("#7c3aed"),
                    tooltip=["designation:N", alt.Tooltip("CA:Q", format=",.0f")]
                )
                .properties(height=260, title="Top produits retail (CA)")
            )
            show_chart(alt_base() + ch_top)

    with col2:
        # AUTRE à corriger
        df_autre = df_m_lines[df_m_lines["categorie"] == "AUTRE"].copy()
        if df_autre.empty:
            st.markdown("<div class='miniCard'><b>AUTRE</b><br><span class='muted'>Rien à corriger ce mois.</span></div>", unsafe_allow_html=True)
        else:
            autre = (
                df_autre.groupby("designation", as_index=False)
                .agg(CA=("total_ttc", "sum"), Qt=("quantite", "sum"))
                .sort_values("CA", ascending=False)
            )
            st.markdown("<div class='miniCard'><b>Produits classés AUTRE (à recatégoriser)</b></div>", unsafe_allow_html=True)
            show_df(autre.head(12), height=245)

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)

    # ====== Forecast 3 mois basé MRR + hypothèses
    st.markdown("### Prévisionnel (3 mois) — basé sur MRR (abos récurrents)")
    if not has_abos:
        st.info("Pas de CSV importé : prévision MRR indisponible.")
    else:
        # churn moyen sur 3 derniers mois si possible
        churn_default = 6.0
        new_default = 8
        if not churn_df.empty:
            tmp = churn_df.dropna(subset=["churn_pct"]).tail(3)
            if not tmp.empty:
                churn_default = float(tmp["churn_pct"].mean())
            tmp2 = churn_df.dropna(subset=["new"]).tail(3)
            if not tmp2.empty:
                new_default = int(round(tmp2["new"].mean()))

        c1, c2, c3 = st.columns(3)
        with c1:
            churn_ass = st.slider("Hypothèse churn mensuel (%)", 0.0, 25.0, float(round(churn_default, 1)), 0.5)
        with c2:
            new_ass = st.slider("Hypothèse nouveaux abos / mois", 0, 60, int(new_default), 1)
        with c3:
            arpu_ass = st.slider("ARPU utilisé (€/mois)", 10.0, 200.0, float(round(arpu_now if arpu_now else 75.0, 0)), 1.0)

        start_month = mois_dispo[-1]
        fc = forecast_mrr_3_months(actifs_now, mrr_now, arpu_ass, churn_ass, new_ass, start_month)

        df_hist_mrr = None
        if not churn_df.empty:
            df_hist_mrr = churn_df[["mois_label", "mrr"]].rename(columns={"mrr": "MRR"}).copy()
        else:
            df_hist_mrr = pd.DataFrame(columns=["mois_label", "MRR"])

        df_fc_mrr = fc[["mois_label", "mrr"]].rename(columns={"mrr": "MRR"}).copy()

        # chart: historique (si dispo) + forecast
        if not df_hist_mrr.empty:
            hist = df_hist_mrr.copy()
            hist["Type"] = "Historique"
        else:
            hist = pd.DataFrame(columns=["mois_label", "MRR", "Type"])

        fut = df_fc_mrr.copy()
        fut["Type"] = "Prévision"

        df_plot = pd.concat([hist, fut], ignore_index=True)
        order = list(hist["mois_label"]) + list(fut["mois_label"])
        ch = (
            alt.Chart(df_plot)
            .mark_line(point=alt.OverlayMarkDef(size=65), strokeWidth=2.6)
            .encode(
                x=alt.X("mois_label:N", title=None, sort=order),
                y=alt.Y("MRR:Q", title="€"),
                color=alt.Color("Type:N", legend=alt.Legend(title=""), scale=alt.Scale(range=["#60a5fa", "#f59e0b"])),
                strokeDash=alt.condition(alt.datum.Type == "Prévision", alt.value([6,4]), alt.value([1,0])),
                tooltip=["mois_label:N", "Type:N", alt.Tooltip("MRR:Q", format=",.0f")]
            )
            .properties(height=250, title="MRR — historique + prévision (3 mois)")
        )
        show_chart(alt_base() + ch)

        colL, colR = st.columns([1.0, 1.0])
        with colL:
            show_df(fc.rename(columns={"mrr": "MRR"}), height=240)
        with colR:
            st.markdown("<div class='miniCard'><b>Lecture direction</b><br>"
                        "<span class='muted'>Prévision = modèle simple. Si tu veux un prévisionnel solide : "
                        "il faudra intégrer les résiliations réelles + leads + conversion.</span></div>",
                        unsafe_allow_html=True)

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)

    # ====== Alertes direction (règles)
    st.markdown("### Alertes direction (à traiter)")
    alerts = []

    # 1) churn
    if churn_last is not None and churn_last >= churn_alert:
        alerts.append(("Rouge", f"Churn élevé ({churn_last:.1f}%) ≥ seuil {churn_alert:.1f}% : risque rétention / expérience / pricing."))

    # 2) ARPU baisse
    if arpu_prev is not None and arpu_prev > 0:
        drop_pct = (arpu_prev - arpu_now) / arpu_prev * 100
        if drop_pct >= arpu_drop_alert:
            alerts.append(("Orange", f"ARPU en baisse (-{drop_pct:.1f}%) : attention mix d'offres / remises / downgrade."))

    # 3) structure CA abos/cartes
    if share_abos < abos_share_alert:
        alerts.append(("Orange", f"% CA Abos/Cartes trop faible ({share_abos:.1f}%) < {abos_share_alert:.1f}% : dépendance retail/one-shot, MRR fragile."))

    # 4) dépendance retail top1
    if top1_share >= top1_retail_alert:
        alerts.append(("Orange", f"Retail dépendant d’un produit (Top1={top1_share:.1f}%) ≥ {top1_retail_alert:.1f}% : risque rupture / effet mode."))

    # 5) AUTRE trop haut
    autre_ca = float(row_m.get("CA_AUTRE", 0.0))
    autre_pct = (autre_ca / ca_m * 100) if ca_m else 0
    if autre_pct >= 5.0:
        alerts.append(("Info", f"Part 'AUTRE' élevée ({autre_pct:.1f}%) : recatégoriser pour mieux piloter."))

    if not alerts:
        st.success("✅ Aucune alerte majeure détectée selon les seuils actuels.")
    else:
        for lvl, msg in alerts:
            if lvl == "Rouge":
                st.error(msg)
            elif lvl == "Orange":
                st.warning(msg)
            else:
                st.info(msg)


# =========================
# VUE MENSUELLE (TVA)
# =========================

with tab_mensuel:
    st.subheader("Vue mensuelle (TVA)")
    if not has_tva:
        st.warning("Aucune donnée TVA importée.")
    else:
        mois_focus = st.selectbox("Mois", mois_dispo, index=len(mois_dispo)-1, format_func=format_mois_label, key="mens_mois")
        df_m = df_hist_tva[df_hist_tva["mois"] == mois_focus].copy()
        ca = df_m["total_ttc"].sum()

        df_cat = (
            df_m.groupby("categorie", as_index=False)
            .agg(CA=("total_ttc", "sum"), Quantites=("quantite", "sum"))
            .sort_values("CA", ascending=False)
        )
        df_cat["%"] = (df_cat["CA"] / df_cat["CA"].sum() * 100).round(1) if df_cat["CA"].sum() > 0 else 0.0

        st.markdown(
            f"""
            <div class="kpiGrid">
              <div class="kpiCard"><div class="kpiTitle">CA total — {format_mois_label(mois_focus)}</div><div class="kpiValue">{ca:,.0f} €</div></div>
              <div class="kpiCard"><div class="kpiTitle">% Abos/Cartes</div><div class="kpiValue">{(df_cat[df_cat["categorie"]=="Abonnements / cartes"]["%"].sum() if not df_cat.empty else 0):.1f}%</div></div>
              <div class="kpiCard"><div class="kpiTitle">CA retail</div><div class="kpiValue">{(ca - df_cat[df_cat["categorie"]=="Abonnements / cartes"]["CA"].sum()):,.0f} €</div></div>
              <div class="kpiCard"><div class="kpiTitle">Nb lignes</div><div class="kpiValue">{len(df_m)}</div></div>
            </div>
            """,
            unsafe_allow_html=True
        )

        col1, col2 = st.columns([1.0, 1.0])
        with col1:
            ch = donut(df_cat.rename(columns={"categorie": "Catégorie"}), "Catégorie", "CA", "Structure CA (mois)")
            if ch is not None:
                show_chart(alt_base() + ch)
        with col2:
            show_df(df_cat, height=260)


# =========================
# COMPARAISON MENSUELLE (TVA)
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

            df_line = df_range[["mois_label", "CA_total"]].rename(columns={"CA_total": "CA"})
            ch = line_chart(df_line, "mois_label", "CA", "CA total — période sélectionnée", height=240)
            if ch is not None:
                show_chart(alt_base() + ch)

            cat_long = []
            for _, r in df_range.iterrows():
                for cat in CATEGORIES_TVA:
                    cat_long.append({"mois_label": r["mois_label"], "Catégorie": cat, "CA": float(r.get(f"CA_{cat}", 0.0))})
            df_cat_long = pd.DataFrame(cat_long)

            ch2 = grouped_bars(df_cat_long, "mois_label", "Catégorie", "CA", "CA par catégorie — comparaison", height=240)
            if ch2 is not None:
                show_chart(alt_base() + ch2)


# =========================
# DETAIL (produits + adhérents)
# =========================

with tab_detail:
    st.subheader("Détails")

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
            show_df(top, height=420)

    st.markdown("---")
    st.markdown("### Abonnements récurrents actifs (CSV) — instant T")
    if not has_abos:
        st.info("Pas de CSV importé.")
    else:
        today = datetime.today().date()
        sub_act = compute_active_recurring_subs_at(df_abos, today)
        st.metric("Abonnements récurrents actifs", int(len(sub_act)))
        if sub_act.empty:
            st.info("Aucun.")
        else:
            cols = [c for c in ["prenom","nom","email","telephone","offre","sous_type","prix_effectif","date_debut","date_fin","reconduction","statut"] if c in sub_act.columns]
            show_df(sub_act[cols].sort_values(["sous_type","nom","prenom"], na_position="last"), height=520)
