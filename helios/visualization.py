import plotly.express as px
import pandas as pd

COLOR_SEQUENCE = ["#E84855", "#3185FC", "#F9DC5C", "#6E44FF", "#33CA7F"]

def month_over_month_chart(df: pd.DataFrame):
    fig = px.bar(
        df,
        x="month",
        y="amount",
        title="Variation du chiffre d'affaires par mois",
        color="amount",
        color_continuous_scale="Blues"
    )
    fig.update_layout(showlegend=False)
    return fig

def category_distribution(df: pd.DataFrame):
    fig = px.pie(
        df,
        names="category",
        values="amount",
        title="Répartition par catégorie de vente",
        color_discrete_sequence=COLOR_SEQUENCE
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return fig
