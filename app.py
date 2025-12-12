import os
import re
from io import BytesIO
from datetime import datetime, date, timedelta

import streamlit as st
import pandas as pd
import pdfplumber
import altair as alt


# =========================
# CONFIG
# =========================

DATA_DIR = "data"
HISTORY_TVA_FILE = os.path.join(DATA_DIR, "history_tva.csv")   # ventes issues des PDF TVA
HISTORY_ABOS_FILE = os.path.join(DATA_DIR, "history_abos.csv") # abonnements / cartes issus du CSV
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
# PAGE / THEME
# =========================

st.set_page_config(page_title="Helios – Reporting CA", layout="wide")

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1320px;
        }
        h1, h2, h3, h4 {
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
                         system-ui, sans-serif !important;
        }
        .kpiCard .stMetric {
            background: linear-gradient(135deg, #0b1220, #020617);
            padding: 0.9rem 1.1rem;
            border-radius: 1rem;
            border: 1px solid rgba(148,163,184,.18);
            box-shadow: 0 12px 22px rgba(0,0,0,0.35);
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 0.45rem 1.1rem;
            border-radius: 999px;
            background-color: #0b1220;
            border: 1px solid rgba(148,163,184,.18);
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #2563eb, #22c55e) !important;
            color: white !important;
        }
        .muted {
            color: rgba(226,232,240,.75);
            font-size: 0.95rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================
# HELPERS STREAMLIT (width compat)
# =========================

def show_chart(chart):
    """
    Compat Streamlit: certains environnements déprécient use_container_width.
    """
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
# UTILS PARSE / FORMAT
# =========================

def to_float(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return 0.0
    s = str(x)
    s = s.replace("€", "").replace("\u00a0", "").replace(" ", "")
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
    return sorted(months, key=lambda x: datetime.strptime(x, "%Y-%m"))


def format_mois_label(mois: str) -> str:
    dt = datetime.strptime(mois, "%Y-%m")
    return f"{MOIS_FR[dt.month]} {dt.year}"


def extract_period_from_text(text: str):
    m = re.search(r"(\d{2}-\d{2}-\d{4})\s*-\s*(\d{2}-\d{2}-\d{4})", text)
    if not m:
        return None, None, None
    d1 = datetime.strptime(m.group(1), "%d-%m-%Y")
    d2 = datetime.strptime(m.group(2), "%d-%m-%Y")
    mois = f"{d1.year}-{d1.month:02d}"
    return mois, d1.date().isoformat(), d2.date().isoformat()


def parse_date_creation(raw):
    """
    CSV : "29/09/25 à 21:37" -> date
    """
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
    """
    Date début/fin : "01/10/25", "01/10/2025", "2025-10-01"
    """
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


# =========================
# VISUELS (ALTair)
# =========================

def donut_chart(df, label_col, value_col, title: str):
    if df.empty or df[value_col].sum() <= 0:
        return None

    base = alt.Chart(df)

    arcs = (
        base
        .mark_arc(innerRadius=62, outerRadius=118)
        .encode(
            theta=alt.Theta(f"{value_col}:Q", stack=True),
            color=alt.Color(
                f"{label_col}:N",
                legend=alt.Legend(title=""),
                scale=alt.Scale(scheme="tableau10")
            ),
            tooltip=[label_col, alt.Tooltip(value_col, format=".2f")]
        )
    )

    text = (
        base
        .transform_joinaggregate(total=f"sum({value_col})")
        .transform_calculate(pct=f"datum.{value_col} / datum.total * 100")
        .mark_text(radius=140, size=11)
        .encode(
            theta=alt.Theta(f"{value_col}:Q", stack=True),
            text=alt.Text("pct:Q", format=".1f"),
            color=alt.value("white")
        )
    )

    return (arcs + text).properties(height=290, title=title)


def bar_vertical(df, x_col, y_col, title, y_title, color_col=None):
    if df.empty:
        return None
    if color_col is None:
        color_col = x_col

    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8)
        .encode(
            x=alt.X(f"{x_col}:N", title=None, sort=list(df[x_col])),
            y=alt.Y(f"{y_col}:Q", title=y_title),
            color=alt.Color(f"{color_col}:N", legend=None, scale=alt.Scale(scheme="category10")),
            tooltip=[x_col, alt.Tooltip(y_col, format=".2f")]
        )
        .properties(height=240, title=title)
    )


def bar_horizontal(df, cat_col, value_col, title, v_title):
    if df.empty:
        return None
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopRight=8, cornerRadiusBottomRight=8)
        .encode(
            x=alt.X(f"{value_col}:Q", title=v_title),
            y=alt.Y(f"{cat_col}:N", title=None, sort="-x"),
            color=alt.Color(f"{cat_col}:N", legend=None, scale=alt.Scale(scheme="tableau10")),
            tooltip=[cat_col, alt.Tooltip(value_col, format=".2f")]
        )
        .properties(height=260, title=title)
    )


def line_chart(df, x_col, y_col, title, y_title):
    if df.empty:
        return None
    return (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X(f"{x_col}:N", title=None, sort=list(df[x_col])),
            y=alt.Y(f"{y_col}:Q", title=y_title),
            tooltip=[x_col, alt.Tooltip(y_col, format=".2f")]
        )
        .properties(height=240, title=title)
    )


# =========================
# CATEGORISATION TVA (PDF)
# =========================

def categorize_product_tva(name: str):
    if not isinstance(name, str):
        name = str(name)
    n = name.lower()

    # Abonnements / cartes
    if "abonn" in n:
        return "Abonnements / cartes", "Abonnement"
    if "carte" in n or "prépayée" in n or "prepayee" in n:
        return "Abonnements / cartes", "Carte"
    if "drop in" in n or "drop-in" in n or "dropin" in n:
        return "Abonnements / cartes", "Drop-in"

    # Boissons & compléments
    patterns_boissons = [
        "nocco", "barebells", "fitaid", "vitamin well", "vitaminwell",
        "whey", "creatine", "créatine", "collagene", "collagène",
        "magnesium", "magnésium", "omega", "oméga"
    ]
    if any(p in n for p in patterns_boissons):
        return "Boissons & compléments alimentaires", "Boisson / complément"

    # Vestimentaire & accessoires
    patterns_vetements = ["t-shirt", "t shirt", "tee shirt", "ceinture", "manique", "maniques", "genouill"]
    if any(p in n for p in patterns_vetements):
        return "Vestimentaire & accessoires sport", "Textile / accessoires"

    return "AUTRE", "AUTRE"


# =========================
# EXTRACTION PDF TVA
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
            today = datetime.today()
            periode_mois = f"{today.year}-{today.month:02d}"

        for page in pdf.pages:
            tables = page.extract_tables()
            for t in tables:
                if not t or len(t) < 2:
                    continue

                header = [c.strip() if c else "" for c in t[0]]
                header_lower = [h.lower() for h in header]

                if not any("désignation" in h or "designation" in h for h in header_lower):
                    continue
                if not any("quantité" in h or "quantite" in h for h in header_lower):
                    continue

                df = pd.DataFrame(t[1:], columns=header)

                # mapping colonnes tolérant
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

    cats = full_df["designation"].apply(lambda x: categorize_product_tva(str(x)))
    full_df["categorie"] = cats.apply(lambda x: x[0])
    full_df["sous_categorie"] = cats.apply(lambda x: x[1])

    return full_df


# =========================
# HISTORIQUE TVA
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
    res = df.groupby("mois").agg(
        CA_total=("total_ttc", "sum"),
        Qt_total=("quantite", "sum"),
    ).reset_index()

    for cat in CATEGORIES_TVA:
        col_name = f"CA_{cat}"
        tmp = (
            df[df["categorie"] == cat]
            .groupby("mois")["total_ttc"]
            .sum()
            .rename(col_name)
        )
        res = res.merge(tmp, on="mois", how="left")

    res = res.sort_values("mois", key=lambda s: s.map(lambda x: datetime.strptime(x, "%Y-%m")))
    return res.fillna(0.0)


# =========================
# CSV INSCRIPTIONS : CLASSIFICATION
# =========================

def classify_contrat(offre: str):
    """
    Retourne (type_contrat, sous_type)
    type_contrat ∈ {ABONNEMENT, CARTE_10, EVENT, EXCLU}
    Règles demandées :
      - "Liberté" = Carnet 10 séances (pas un abo)
      - "Drop in" exclu (séance unique)
      - Events exclu
      - Abonnements = les offres normales (Essentiel/Evolution/Premium/Hyrox/1x semaine/Ascension…)
    """
    if not isinstance(offre, str):
        offre = str(offre)
    s = offre.lower().strip()

    # Events à exclure
    if any(k in s for k in ["soirée", "soiree", "inauguration", "raclette", "event", "offre de rentrée", "offre de rentree"]):
        return ("EVENT", offre)

    # Drop-in exclu
    if "drop" in s:
        return ("EXCLU", "Drop in")

    # Liberté = carnet 10
    if "liberté" in s or "liberte" in s:
        return ("CARTE_10", "Carnet 10 séances")

    # Abonnements
    abo_keywords = [
        "essentiel", "evolution", "premium", "hyrox", "1x semaine", "1 x semaine", "ascension"
    ]
    if any(k in s for k in abo_keywords):
        # On garde le libellé d'offre comme sous_type (plus parlant)
        return ("ABONNEMENT", offre)

    return ("EXCLU", offre)


def extract_abos_from_csv(file_obj: BytesIO) -> pd.DataFrame:
    df_raw = pd.read_csv(file_obj)
    df_raw.columns = [c.strip() for c in df_raw.columns]

    # Détection colonne date création (tolérante)
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

    # Date création -> mois
    df["date_creation"] = df_raw[date_col].apply(parse_date_creation)
    df = df[~df["date_creation"].isna()]
    if df.empty:
        return df

    df["mois_creation"] = df["date_creation"].apply(lambda d: f"{d.year}-{d.month:02d}")

    # Classification
    df["offre"] = df["offre"].astype(str)
    types = df["offre"].apply(classify_contrat)
    df["type_contrat"] = types.apply(lambda x: x[0])
    df["sous_type"] = types.apply(lambda x: x[1])

    # Prix effectif
    df["prix_offre"] = df.get("prix_offre", 0).apply(to_float)
    df["prix_perso"] = df.get("prix_perso", 0).apply(to_float)
    df["prix_effectif"] = df.apply(
        lambda r: r["prix_perso"] if r["prix_perso"] > 0 else r["prix_offre"],
        axis=1,
    )

    # Parsing dates début/fin (utile pour abos actifs + projection)
    df["date_debut_parsed"] = df.get("date_debut").apply(parse_simple_date)
    df["date_fin_parsed"] = df.get("date_fin").apply(parse_simple_date)

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
# ABOS ACTIFS + PROJECTION
# =========================

def month_bounds(d: date):
    start = date(d.year, d.month, 1)
    if d.month == 12:
        start_next = date(d.year + 1, 1, 1)
    else:
        start_next = date(d.year, d.month + 1, 1)
    end = start_next - timedelta(days=1)
    return start, end


def compute_active_abos_and_projection(df_abos: pd.DataFrame, ref_dt: date):
    """
    - Ne prend que les ABONNEMENTS
    - Ne prend que les "récurrents" : reconduction != 'Non'
      (vide = considéré comme reconduit)
    - Exclut carnets / events / dropin via type_contrat
    - Actifs à la date ref_dt :
        VALIDATED, date_debut <= ref_dt <= date_fin (ou date_fin vide)
    - Projection mois suivant :
        abos récurrents qui couvrent au moins une partie du mois suivant
    """
    if df_abos is None or df_abos.empty:
        return pd.DataFrame(), 0.0, pd.DataFrame(), 0.0, None

    df = df_abos.copy()

    # Sécurité colonnes
    for col in ["type_contrat", "statut", "reconduction", "prix_effectif", "date_debut_parsed", "date_fin_parsed", "sous_type"]:
        if col not in df.columns:
            df[col] = None

    df["statut_norm"] = df["statut"].astype(str).str.upper()
    df["reconduction_norm"] = df["reconduction"].astype(str).str.strip().str.lower()

    # Récurrents : reconduction != non (vide = ok)
    recurring_mask = (df["reconduction_norm"] != "non")

    # Abonnements uniquement
    df = df[(df["type_contrat"] == "ABONNEMENT") & recurring_mask].copy()
    if df.empty:
        return pd.DataFrame(), 0.0, pd.DataFrame(), 0.0, None

    # Actifs aujourd'hui
    active_mask = (
        (df["statut_norm"] == "VALIDATED")
        & df["date_debut_parsed"].notna()
        & (df["date_debut_parsed"] <= ref_dt)
        & (df["date_fin_parsed"].isna() | (df["date_fin_parsed"] >= ref_dt))
    )
    df_active = df[active_mask].copy()
    ca_mensuel_estime = df_active["prix_effectif"].apply(to_float).sum()

    # Projection mois suivant
    if ref_dt.month == 12:
        next_month_start = date(ref_dt.year + 1, 1, 1)
    else:
        next_month_start = date(ref_dt.year, ref_dt.month + 1, 1)
    _, next_month_end = month_bounds(next_month_start)

    proj_mask = (
        df["date_debut_parsed"].notna()
        & (df["date_debut_parsed"] <= next_month_end)
        & (df["date_fin_parsed"].isna() | (df["date_fin_parsed"] >= next_month_start))
        & df["statut_norm"].isin(["VALIDATED", "FUTURE"])
    )
    df_proj = df[proj_mask].copy()
    ca_proj = df_proj["prix_effectif"].apply(to_float).sum()
    next_label = f"{MOIS_FR[next_month_start.month]} {next_month_start.year}"

    return df_active, ca_mensuel_estime, df_proj, ca_proj, next_label


# =========================
# APP
# =========================

st.title("Helios CrossFit – Outil de reporting CA")

tabs = st.tabs(["📊 Dashboard Direction", "📅 Vue mensuelle", "📈 Comparaison", "🔍 Détail produits/abos", "⬆️ Import"])
tab_dash, tab_mensuel, tab_comp, tab_detail, tab_import = tabs

# =========================
# IMPORT TAB
# =========================
with tab_import:
    st.subheader("Import de données")

    st.markdown(
        """
        <div class="muted">
        ✅ PDF TVA : choisir l’année + le mois, puis importer le PDF → remplace uniquement ce mois.<br>
        ✅ CSV Inscriptions : importer le CSV → remplace l’historique inscriptions (plus à jour).
        </div>
        """,
        unsafe_allow_html=True
    )

    col_a, col_m = st.columns(2)
    annee_courante = datetime.today().year
    annees = list(range(2022, annee_courante + 1))

    with col_a:
        annee_select = st.selectbox("Année (PDF TVA)", annees, index=len(annees) - 1)
    with col_m:
        mois_num = st.selectbox("Mois (PDF TVA)", list(MOIS_FR.keys()), format_func=lambda x: MOIS_FR[x])

    mois_import_tva = f"{annee_select}-{mois_num:02d}"

    uploaded_pdf = st.file_uploader("Rapport TVA (PDF)", type=["pdf"])
    if st.button("Importer / remplacer ce mois (TVA)"):
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

                st.success(f"✅ Import OK — {len(df_new)} lignes — CA: {df_new['total_ttc'].sum():.2f} € — {format_mois_label(mois_import_tva)}.")
                show_df(df_new.head(30), height=340)

    st.divider()

    csv_file = st.file_uploader("Inscriptions (CSV)", type=["csv"])
    if st.button("Importer / remplacer l’historique inscriptions"):
        if csv_file is None:
            st.error("Choisis un CSV.")
        else:
            with st.spinner("Traitement du CSV..."):
                df_abos_new = extract_abos_from_csv(BytesIO(csv_file.read()))

            if df_abos_new.empty:
                st.error("Aucune inscription exploitable trouvée.")
            else:
                save_history_abos(df_abos_new)
                mois_couverts = sort_months(df_abos_new["mois_creation"].unique())
                st.success(f"✅ CSV importé — {len(df_abos_new)} lignes — {format_mois_label(mois_couverts[0])} → {format_mois_label(mois_couverts[-1])}")
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
    # sécurité parse dates si le fichier a été importé avant ajout des colonnes
    if "date_debut_parsed" not in df_abos.columns and "date_debut" in df_abos.columns:
        df_abos["date_debut_parsed"] = df_abos["date_debut"].apply(parse_simple_date)
    if "date_fin_parsed" not in df_abos.columns and "date_fin" in df_abos.columns:
        df_abos["date_fin_parsed"] = df_abos["date_fin"].apply(parse_simple_date)


# =========================
# DASHBOARD DIRECTION
# =========================
with tab_dash:
    st.subheader("Dashboard Direction")

    if not has_tva:
        st.warning("Aucune donnée TVA importée. Va dans l’onglet Import.")
    else:
        mois_ref = st.selectbox("Mois analysé (TVA)", mois_dispo, index=len(mois_dispo) - 1, format_func=format_mois_label)
        idx = mois_dispo.index(mois_ref)
        mois_prev = mois_dispo[idx - 1] if idx > 0 else None

        row_ref = summary_tva[summary_tva["mois"] == mois_ref].iloc[0]
        ca_ref = float(row_ref["CA_total"])
        qt_ref = int(row_ref["Qt_total"])

        ca_prev = None
        if mois_prev:
            ca_prev = float(summary_tva[summary_tva["mois"] == mois_prev]["CA_total"].iloc[0])

        delta_abs = None
        delta_pct = None
        if ca_prev is not None and ca_prev != 0:
            delta_abs = ca_ref - ca_prev
            delta_pct = (delta_abs / ca_prev) * 100

        st.markdown('<div class="kpiCard">', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("CA total (TVA)", f"{ca_ref:,.0f} €".replace(",", " "),
                  None if delta_abs is None else f"{delta_abs:+.0f} € ({delta_pct:+.1f}%)")
        c2.metric("Quantités vendues (TVA)", qt_ref)
        c3.metric("Mois TVA", format_mois_label(mois_ref))
        c4.metric("Nb lignes TVA", int(len(df_hist_tva[df_hist_tva["mois"] == mois_ref])))
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("---")

        # CA total vs mois précédent
        if mois_prev:
            df_cmp = pd.DataFrame({
                "Mois": [format_mois_label(mois_prev), format_mois_label(mois_ref)],
                "CA": [ca_prev, ca_ref],
            })
            ch = bar_vertical(df_cmp, "Mois", "CA", "CA total – comparaison", "CA (€)")
            if ch is not None:
                show_chart(ch)
        else:
            st.info("Un seul mois TVA disponible : impossible de comparer.")

        st.markdown("---")

        # Structure du CA (donut)
        df_mois_tva = df_hist_tva[df_hist_tva["mois"] == mois_ref]
        df_cat = (
            df_mois_tva.groupby("categorie", as_index=False)
            .agg(CA=("total_ttc", "sum"))
            .sort_values("CA", ascending=False)
        )

        col1, col2 = st.columns((1, 1))
        with col1:
            ch_donut = donut_chart(df_cat.rename(columns={"categorie": "Catégorie"}), "Catégorie", "CA", "Structure du CA (TVA)")
            if ch_donut is not None:
                show_chart(ch_donut)
            else:
                st.info("Pas de CA.")
        with col2:
            if df_cat["CA"].sum() > 0:
                df_cat["%"] = (df_cat["CA"] / df_cat["CA"].sum() * 100).round(1)
            show_df(df_cat, height=320)

        st.markdown("---")

        # ========= AJOUT : ABOS ACTIFS + CA PROJETE =========
        st.subheader("Abonnements actifs (récurrents) & CA projeté")

        if not has_abos:
            st.info("Pas de CSV inscriptions importé.")
        else:
            today = datetime.today().date()
            df_active, ca_mensuel_estime, df_proj, ca_proj, next_label = compute_active_abos_and_projection(df_abos, today)

            st.markdown('<div class="kpiCard">', unsafe_allow_html=True)
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Abonnements actifs (aujourd’hui)", int(len(df_active)))
            a2.metric("CA mensuel estimé (actifs)", f"{ca_mensuel_estime:,.0f} €".replace(",", " "))
            a3.metric(f"CA projeté – {next_label}", f"{ca_proj:,.0f} €".replace(",", " "))
            a4.metric("Date de référence", today.strftime("%d/%m/%Y"))
            st.markdown("</div>", unsafe_allow_html=True)

            if df_active.empty:
                st.warning("Aucun abonnement actif récurrent détecté (hors carnets / drop-in / events).")
            else:
                # Détail par type (sous_type)
                df_mix = (
                    df_active.groupby("sous_type", as_index=False)
                    .agg(Nb=("offre", "count"), CA=("prix_effectif", "sum"))
                    .sort_values("CA", ascending=False)
                )
                df_mix["% actifs"] = (df_mix["Nb"] / df_mix["Nb"].sum() * 100).round(1)

                colA, colB = st.columns((1, 1))
                with colA:
                    ch_mix = donut_chart(
                        df_mix.rename(columns={"sous_type": "Type"}),
                        "Type",
                        "CA",
                        "Répartition des abonnements actifs (CA)"
                    )
                    if ch_mix is not None:
                        show_chart(ch_mix)
                with colB:
                    show_df(df_mix, height=320)

                st.markdown("#### Liste des abonnements actifs (détail)")
                cols_to_show = []
                for c in ["prenom", "nom", "email", "telephone", "offre", "sous_type", "prix_effectif", "date_debut", "date_fin", "reconduction", "statut"]:
                    if c in df_active.columns:
                        cols_to_show.append(c)
                show_df(df_active[cols_to_show].sort_values(["sous_type", "prix_effectif"], ascending=[True, False]), height=360)

                st.caption("⚠️ La projection du mois suivant se base sur les abonnements récurrents (Reconduction ≠ Non) actifs sur tout ou partie du mois suivant.")


# =========================
# VUE MENSUELLE
# =========================
with tab_mensuel:
    st.subheader("Vue mensuelle (TVA)")

    if not has_tva:
        st.warning("Aucune donnée TVA importée.")
    else:
        mois_focus = st.selectbox("Mois TVA", mois_dispo, index=len(mois_dispo) - 1, format_func=format_mois_label)

        df_m = df_hist_tva[df_hist_tva["mois"] == mois_focus]
        ca = df_m["total_ttc"].sum()
        qt = df_m["quantite"].sum()

        st.markdown('<div class="kpiCard">', unsafe_allow_html=True)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("CA total", f"{ca:,.0f} €".replace(",", " "))
        k2.metric("Quantités", int(qt))
        k3.metric("Nb lignes", int(len(df_m)))
        k4.metric("Mois", format_mois_label(mois_focus))
        st.markdown("</div>", unsafe_allow_html=True)

        df_cat = (
            df_m.groupby("categorie", as_index=False)
            .agg(CA=("total_ttc", "sum"), Quantites=("quantite", "sum"))
            .sort_values("CA", ascending=False)
        )

        col1, col2 = st.columns((1, 1))
        with col1:
            ch = donut_chart(df_cat.rename(columns={"categorie": "Catégorie"}), "Catégorie", "CA", "Répartition du CA (TVA)")
            if ch is not None:
                show_chart(ch)
        with col2:
            if df_cat["CA"].sum() > 0:
                df_cat["%"] = (df_cat["CA"] / df_cat["CA"].sum() * 100).round(1)
            show_df(df_cat, height=320)

        st.markdown("---")
        st.markdown("### Top produits (TVA)")

        cat_focus = st.selectbox("Catégorie TVA", CATEGORIES_TVA)
        df_c = df_m[df_m["categorie"] == cat_focus]
        if df_c.empty:
            st.info("Aucune ligne.")
        else:
            top = (
                df_c.groupby("designation", as_index=False)
                .agg(CA=("total_ttc", "sum"), Quantites=("quantite", "sum"))
                .sort_values("CA", ascending=False)
            )
            show_df(top, height=360)
            ch_top = bar_horizontal(top.head(10), "designation", "CA", "Top 10 produits (CA)", "CA (€)")
            if ch_top is not None:
                show_chart(ch_top)


# =========================
# COMPARAISON
# =========================
with tab_comp:
    st.subheader("Comparaison mois par mois")

    if not has_tva or len(mois_dispo) < 2:
        st.warning("Il faut au moins 2 mois TVA importés.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            m_start = st.selectbox("Mois début", mois_dispo, index=0, format_func=format_mois_label)
        with col2:
            m_end = st.selectbox("Mois fin", mois_dispo, index=len(mois_dispo) - 1, format_func=format_mois_label)

        i1 = mois_dispo.index(m_start)
        i2 = mois_dispo.index(m_end)
        if i1 > i2:
            st.error("Le mois de début doit être avant le mois de fin.")
        else:
            months = mois_dispo[i1:i2+1]
            df_range = df_hist_tva[df_hist_tva["mois"].isin(months)]
            sum_range = build_month_summary_tva(df_range)
            sum_range["Mois"] = sum_range["mois"].apply(format_mois_label)

            st.markdown("### CA total – évolution")
            ch = line_chart(sum_range, "Mois", "CA_total", "", "CA (€)")
            if ch is not None:
                show_chart(ch)

            show_df(sum_range[["Mois", "CA_total", "Qt_total"]], height=260)

            st.markdown("---")
            st.markdown("### Comparaison par catégorie (CA mensuel)")

            cat_choice = st.selectbox("Catégorie TVA", CATEGORIES_TVA, key="comp_cat")
            colname = f"CA_{cat_choice}"
            tmp = sum_range[["Mois", colname]].rename(columns={colname: "CA"})
            ch2 = bar_vertical(tmp, "Mois", "CA", f"CA – {cat_choice}", "CA (€)")
            if ch2 is not None:
                show_chart(ch2)
            show_df(tmp, height=260)


# =========================
# DETAIL
# =========================
with tab_detail:
    st.subheader("Détail produits (TVA) et abonnements (CSV)")

    if has_tva:
        col1, col2 = st.columns(2)
        with col1:
            cat_det = st.selectbox("Catégorie TVA", CATEGORIES_TVA, key="det_cat")
        with col2:
            mois_det = st.selectbox("Mois TVA", mois_dispo, index=len(mois_dispo) - 1, format_func=format_mois_label, key="det_mois")

        df_det = df_hist_tva[(df_hist_tva["categorie"] == cat_det) & (df_hist_tva["mois"] == mois_det)]
        if df_det.empty:
            st.info("Aucune donnée.")
        else:
            top = (
                df_det.groupby("designation", as_index=False)
                .agg(CA=("total_ttc", "sum"), Quantites=("quantite", "sum"))
                .sort_values("CA", ascending=False)
            )
            show_df(top, height=360)
            ch = bar_horizontal(top.head(10), "designation", "CA", "Top 10 (CA)", "CA (€)")
            if ch is not None:
                show_chart(ch)

        st.markdown("---")
        st.markdown("### Produits classés en AUTRE (à recatégoriser)")
        df_autre = (
            df_hist_tva[df_hist_tva["categorie"] == "AUTRE"]
            .groupby("designation", as_index=False)
            .agg(CA=("total_ttc", "sum"), Quantites=("quantite", "sum"))
            .sort_values("CA", ascending=False)
        )
        if df_autre.empty:
            st.info("Aucun.")
        else:
            show_df(df_autre, height=360)

    else:
        st.info("Pas de TVA importé.")

    st.markdown("---")
    st.markdown("## Abonnements / carnets (CSV)")

    if not has_abos:
        st.info("Pas de CSV inscriptions importé.")
    else:
        mois_abos = sort_months(df_abos["mois_creation"].astype(str).unique())
        col1, col2 = st.columns(2)
        with col1:
            type_filter = st.selectbox("Type contrat", ["ABONNEMENT", "CARTE_10", "EVENT", "EXCLU", "TOUS"])
        with col2:
            mois_sel = st.selectbox("Mois (CSV)", mois_abos, index=len(mois_abos)-1, format_func=format_mois_label)

        d = df_abos[df_abos["mois_creation"].astype(str) == mois_sel].copy()
        if type_filter != "TOUS":
            d = d[d["type_contrat"] == type_filter]

        if d.empty:
            st.info("Aucune ligne.")
        else:
            agg = (
                d.groupby(["type_contrat", "sous_type"], as_index=False)
                .agg(Nb=("offre", "count"), CA=("prix_effectif", "sum"))
                .sort_values("CA", ascending=False)
            )
            show_df(agg, height=320)
            ch = bar_vertical(agg, "sous_type", "Nb", "Répartition (Nb)", "Nb")
            if ch is not None:
                show_chart(ch)
