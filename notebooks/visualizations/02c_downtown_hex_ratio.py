import json
import requests
from io import BytesIO
from pathlib import Path
import geopandas as gpd
import plotly.graph_objects as go

root = Path(__file__).parents[2]

url = "https://raw.githubusercontent.com/seanflannelly/SF-Businesses-Openings-Closings/main/data/processed/fidi_hex_open_close.parquet"
hex_plot = gpd.read_parquet(BytesIO(requests.get(url).content)).to_crs(epsg=4326)
hex_plot = hex_plot[hex_plot["event_year"].between(2019, 2025)].copy()

hex_plot["net_change"] = hex_plot["Opening"] - hex_plot["Closing"]

geojson_hex = json.loads(hex_plot.to_json())
years = sorted(hex_plot["event_year"].dropna().astype(int).unique())

centroid = hex_plot.dissolve().to_crs(epsg=7131).centroid.to_crs(epsg=4326)
center_lat, center_lon = centroid.y.iloc[0], centroid.x.iloc[0]

scale_bound = hex_plot["net_change"].abs().quantile(0.95)

neighborhood = "Financial District"
start = years[0]
df = hex_plot[hex_plot["event_year"] == start]

base = dict(
    geojson=geojson_hex,
    featureidkey="properties.hex_id",
    colorscale="RdBu",
    zmid=0,
    zmin=-scale_bound,
    zmax=scale_bound,
    marker_opacity=0.78,
    marker_line_width=0,
)

fig = go.Figure(go.Choroplethmapbox(
    **base,
    locations=df["hex_id"],
    z=df["net_change"],
    customdata=df[["Opening", "Closing"]],
    colorbar=dict(title="Net Change"),
    hovertemplate="Openings: %{customdata[0]:.0f}<br>Closings: %{customdata[1]:.0f}<br>Net: %{z:.0f}<extra></extra>"
))

fig.frames = [
    go.Frame(
        name=str(yr),
        data=[go.Choroplethmapbox(
            **base,
            locations=hex_plot[hex_plot["event_year"] == yr]["hex_id"],
            z=hex_plot[hex_plot["event_year"] == yr]["net_change"],
            customdata=hex_plot[hex_plot["event_year"] == yr][["Opening", "Closing"]],
            showscale=False,
            hovertemplate="Openings: %{customdata[0]:.0f}<br>Closings: %{customdata[1]:.0f}<br>Net: %{z:.0f}<extra></extra>"
        )],
        layout=go.Layout(title_text=f"Business Net Change in {neighborhood}, {yr}")
    )
    for yr in years
]

fig.update_layout(
    title=f"Business Net Change in {neighborhood}, {start}",
    height=650,
    margin=dict(l=10, r=10, t=80, b=40),
    mapbox=dict(style="carto-positron", center=dict(lat=center_lat, lon=center_lon), zoom=13),
    updatemenus=[dict(
        type="buttons", showactive=False, x=0.05, y=0,
        xanchor="left", yanchor="top",
        buttons=[
            dict(label="Play", method="animate", args=[None, {
                "frame": {"duration": 900, "redraw": True},
                "transition": {"duration": 300},
                "fromcurrent": True, "mode": "immediate"
            }]),
            dict(label="Pause", method="animate", args=[[None], {
                "frame": {"duration": 0, "redraw": False}, "mode": "immediate"
            }])
        ]
    )],
    sliders=[dict(
        active=0, x=0.15, y=0, len=0.75,
        currentvalue=dict(prefix="Year: ", visible=True),
        steps=[
            dict(label=str(yr), method="animate", args=[[str(yr)], {
                "frame": {"duration": 0, "redraw": True}, "mode": "immediate"
            }])
            for yr in years
        ]
    )]
)

fig.update_traces(showscale=True)
for frame in fig.frames:
    for trace in frame.data:
        trace.showscale = True

fig.write_html(root / "outputs/downtown_hex_ratio.html")
fig.show()
