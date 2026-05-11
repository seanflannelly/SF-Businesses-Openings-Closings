import json
from pathlib import Path
import geopandas as gpd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

root = Path(__file__).parents[2]

def load_hex(path):
    gdf = gpd.read_parquet(path).to_crs(epsg=4326)
    gdf = gdf[gdf["event_year"].between(2019, 2025)].copy()
    gdf["net_change"] = gdf["Opening"] - gdf["Closing"]
    return gdf

fidi = load_hex(root / "data/processed/fidi_hex_open_close.parquet")
bhp  = load_hex(root / "data/processed/bhp_hex_open_close.parquet")

geojson_fidi = json.loads(fidi.to_json())
geojson_bhp  = json.loads(bhp.to_json())

years = sorted(fidi["event_year"].dropna().astype(int).unique())

fidi_scale = float(fidi["net_change"].abs().quantile(0.99))
bhp_scale  = float(bhp["net_change"].abs().quantile(0.99))

neighs_year = gpd.read_parquet(root / "data/processed/ALL_openings_closings_by_neighs_year.parquet")
neighs_year = neighs_year[neighs_year["year"].between(2019, 2025)]

def neigh_totals(name):
    df = neighs_year[neighs_year["neighborhood"] == name].copy()
    df["net_change"] = df["opened"] - df["closed"]
    return df.set_index("year")["net_change"].astype(int).to_dict()

fidi_totals = neigh_totals("Financial District/South Beach")
bhp_totals  = neigh_totals("Bayview Hunters Point")

def net_annotations(yr):
    return [
        dict(text=f"Total net: {fidi_totals[yr]:+d}", x=0.23, y=0.97,
             xref="paper", yref="paper", showarrow=False, font=dict(size=13)),
        dict(text=f"Total net: {bhp_totals[yr]:+d}", x=0.77, y=0.97,
             xref="paper", yref="paper", showarrow=False, font=dict(size=13)),
    ]

fidi_center = fidi.dissolve().to_crs(epsg=7131).centroid.to_crs(epsg=4326)
bhp_center  = bhp.dissolve().to_crs(epsg=7131).centroid.to_crs(epsg=4326)
fidi_lat, fidi_lon = fidi_center.y.iloc[0], fidi_center.x.iloc[0]
bhp_lat, bhp_lon   = bhp_center.y.iloc[0], bhp_center.x.iloc[0]

start = years[0]
df_fidi = fidi[fidi["event_year"] == start]
df_bhp  = bhp[bhp["event_year"] == start]

fig = make_subplots(
    rows=1, cols=2,
    specs=[[{"type": "mapbox"}, {"type": "mapbox"}]],
    subplot_titles=("Financial District", "Bayview Hunters Point"),
    horizontal_spacing=0.03
)

fig.add_trace(go.Choroplethmapbox(
    geojson=geojson_fidi, featureidkey="properties.hex_id",
    locations=df_fidi["hex_id"], z=df_fidi["net_change"],
    customdata=df_fidi[["Opening", "Closing"]],
    colorscale="RdBu", zmid=0, zmin=-fidi_scale, zmax=fidi_scale,
    marker_opacity=0.78, marker_line_width=0,
    colorbar=dict(title="Net Change", x=0.46),
    hovertemplate="Openings: %{customdata[0]:.0f}<br>Closings: %{customdata[1]:.0f}<br>Net: %{z:.0f}<extra></extra>"
), row=1, col=1)

fig.add_trace(go.Choroplethmapbox(
    geojson=geojson_bhp, featureidkey="properties.hex_id",
    locations=df_bhp["hex_id"], z=df_bhp["net_change"],
    customdata=df_bhp[["Opening", "Closing"]],
    colorscale="RdBu", zmid=0, zmin=-bhp_scale, zmax=bhp_scale,
    marker_opacity=0.78, marker_line_width=0,
    colorbar=dict(title="Net Change", x=1.02),
    hovertemplate="Openings: %{customdata[0]:.0f}<br>Closings: %{customdata[1]:.0f}<br>Net: %{z:.0f}<extra></extra>"
), row=1, col=2)

fig.frames = [
    go.Frame(
        name=str(yr),
        data=[
            go.Choroplethmapbox(
                geojson=geojson_fidi, featureidkey="properties.hex_id",
                locations=fidi[fidi["event_year"] == yr]["hex_id"],
                z=fidi[fidi["event_year"] == yr]["net_change"],
                customdata=fidi[fidi["event_year"] == yr][["Opening", "Closing"]],
                colorscale="RdBu", zmid=0, zmin=-fidi_scale, zmax=fidi_scale,
                marker_opacity=0.78, marker_line_width=0, showscale=False,
                hovertemplate="Openings: %{customdata[0]:.0f}<br>Closings: %{customdata[1]:.0f}<br>Net: %{z:.0f}<extra></extra>"
            ),
            go.Choroplethmapbox(
                geojson=geojson_bhp, featureidkey="properties.hex_id",
                locations=bhp[bhp["event_year"] == yr]["hex_id"],
                z=bhp[bhp["event_year"] == yr]["net_change"],
                customdata=bhp[bhp["event_year"] == yr][["Opening", "Closing"]],
                colorscale="RdBu", zmid=0, zmin=-bhp_scale, zmax=bhp_scale,
                marker_opacity=0.78, marker_line_width=0, showscale=False,
                hovertemplate="Openings: %{customdata[0]:.0f}<br>Closings: %{customdata[1]:.0f}<br>Net: %{z:.0f}<extra></extra>"
            )
        ],
        traces=[0, 1],
        layout=go.Layout(title_text=f"Business Net Change by Neighborhood, {yr}",
                         annotations=net_annotations(yr))
    )
    for yr in years
]

fig.update_layout(
    title=f"Business Net Change by Neighborhood, {start}",
    annotations=net_annotations(start),
    height=700,
    margin=dict(l=10, r=10, t=80, b=40),
    mapbox=dict(style="carto-positron", center=dict(lat=fidi_lat, lon=fidi_lon), zoom=12),
    mapbox2=dict(style="carto-positron", center=dict(lat=bhp_lat, lon=bhp_lon), zoom=12),
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

fig.write_html(root / "outputs/net_change_comparison.html")
fig.show()
