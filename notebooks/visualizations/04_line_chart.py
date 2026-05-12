import pandas as pd
import plotly.express as px
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
df = pd.read_parquet(ROOT / "data/processed/ALL_openings_closings.parquet")

yearly = df.groupby(["year", "status"]).size().reset_index(name="count")

# Plotting
fig = px.line(
    yearly,
    x="year",
    y="count",
    color="status",
    markers=True
)

# Adding labels
fig.update_layout(
    title="San Francisco Business Openings vs Closings (2016–2025)",
    xaxis_title="Year",
    yaxis_title="Number of Businesses",
    legend_title=None,
    autosize=False,
    width=900,
    height=450,
    margin=dict(l=60, r=20, t=60, b=80),
    legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5)
)

fig.update_xaxes(dtick=1)
fig.update_layout(
    plot_bgcolor="white",
    paper_bgcolor="white"
)

fig.update_layout(
    plot_bgcolor="white",
    paper_bgcolor="white"
)

fig.update_xaxes(
    showgrid=False,
    
)

fig.update_yaxes(
    showgrid=True,
    gridcolor="lightgray",
    range=(6000, 20000)
)

fig.write_html(ROOT / 'outputs/line_chart_all.html')