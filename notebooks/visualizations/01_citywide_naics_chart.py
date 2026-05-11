"""
02 - Citywide NAICS Chart

Rolls up neighborhood-level NAICS data to the city and plots open/close ratio by
sector 2019-2024
"""

from pathlib import Path
import pandas as pd
import geopandas as gpd
import plotly.graph_objects as go

root = Path(__file__).parents[2]
naics_gdf = gpd.read_parquet(root / 'data/processed/ALL_openings_closings_by_naics_neighs_year.parquet')

df = (
    pd.DataFrame(naics_gdf.drop(columns='geometry'))
    .query('2019 <= year <= 2024')
    .groupby(['naics_group', 'year'])[['opened', 'closed']]
    .sum()
    .reset_index()
)
df['ratio'] = df['opened'] / df['closed'].replace(0, float('nan'))

sectors = sorted(df['naics_group'].unique())

colors = [
    '#378ADD', '#E87040', '#4CAF50', '#9C27B0',
    '#FF9800', '#00BCD4', '#F44336', '#795548'
]
sector_colors = {s: colors[i] for i, s in enumerate(sectors)}

fig = go.Figure()

for sector in sectors:
    d = df[df['naics_group'] == sector].sort_values('year')
    fig.add_trace(go.Scatter(
        x=d['year'], y=d['ratio'],
        mode='lines+markers', name=sector,
        line=dict(color=sector_colors[sector], width=2), marker=dict(size=5),
        customdata=d[['opened', 'closed']].values,
        hovertemplate='<b>' + sector + '</b><br>Opened: %{customdata[0]:,}<br>Closed: %{customdata[1]:,}<br>Ratio: %{y:.2f}<extra></extra>',
    ))

fig.add_hrect(y0=0, y1=1, fillcolor='#fee', opacity=0.3, line_width=0)
fig.add_hline(y=1, line_dash='dash', line_color='gainsboro', line_width=1)
fig.add_vrect(x0=2019.5, x1=2021.5, fillcolor='gainsboro', opacity=0.3, line_width=0,
              annotation_text='COVID-19', annotation_position='top left',
              annotation_font=dict(size=10, color='darkgray'))

fig.update_layout(
    title='SF Citywide Open/Close Ratio by Sector (2019-2024)',
    height=500,
    legend=dict(x=1.02, y=1, xanchor='left', yanchor='top', font=dict(size=11)),
    margin=dict(l=20, r=160, t=60, b=20),
    plot_bgcolor='white',
    paper_bgcolor='white',
    yaxis=dict(title='Openings / Closings Ratio', showgrid=True, gridcolor='whitesmoke', zeroline=False),
    xaxis=dict(title='Year', dtick=1),
)

fig.write_html(root / 'outputs/citywide_naics_chart.html')
fig.show()
