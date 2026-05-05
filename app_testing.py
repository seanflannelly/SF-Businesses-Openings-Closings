import json
import pandas as pd
import geopandas as gpd
from dash import Dash, dcc, html, Input, Output, State, callback, ctx
from plotly.subplots import make_subplots
import dash_leaflet as dl
from dash_extensions.javascript import assign
import plotly.graph_objects as go

app = Dash(__name__)
server = app.server

sf_map = gpd.read_file('data/processed/open_close_neighs.geojson')
sf_map = sf_map.to_crs(epsg=4326)
sf_map = sf_map[sf_map['biz_stock'] >= 50]

naics_df   = pd.read_parquet('data/processed/naics_year_charts.parquet')
yearly_df  = pd.read_parquet('data/processed/sf_businesses_nhood_naics.parquet')
combined_df = pd.read_parquet('data/processed/sf_business_demographics_nhood_naics.parquet')
demo_df    = combined_df[['neighborhood', 'median_income', 'pct_white', 'pct_black',
                           'pct_asian', 'pct_latina_o', 'pct_other']].drop_duplicates('neighborhood')

yearly_totals = (
    yearly_df
    .groupby(['nhood', 'year'])[['opened', 'closed']]
    .sum()
    .reset_index()
)
yearly_totals['open_close_ratio'] = yearly_totals['opened'] / yearly_totals['closed'].replace(0, float('nan'))

years   = sorted(yearly_totals['year'].unique().tolist())
sectors = sorted(naics_df['naics_group'].unique().tolist())

LOW  = 0.0
HIGH = 2.0
MID  = 1.0

def make_geojson(year):
    year_data = yearly_totals[yearly_totals['year'] == year].set_index('nhood')
    gdf = sf_map.copy()
    gdf['opened']           = gdf['neighborhood'].map(year_data['opened']).fillna(0)
    gdf['closed']           = gdf['neighborhood'].map(year_data['closed']).fillna(0)
    gdf['open_close_ratio'] = gdf['neighborhood'].map(year_data['open_close_ratio'])

    for idx, row in gdf.iterrows():
        ratio = row['open_close_ratio']
        ratio_str = f"{ratio:.2f}" if pd.notna(ratio) else "N/A"
        gdf.at[idx, 'tooltip'] = (
            f"<b>{row['neighborhood']}</b><br>"
            f"Opened: {int(row['opened'])}<br>"
            f"Closed: {int(row['closed'])}<br>"
            f"Ratio: {ratio_str}"
        )

    return json.loads(gdf.to_json())

geojson_by_year = {year: make_geojson(year) for year in years}

DEFAULT_SELECTION = ['Sunset/Parkside', 'Bayview Hunters Point']
DEFAULT_YEAR = 2024
NEIGHBORHOOD_COLORS = ['#378ADD', '#E87040', '#4CAF50', '#9C27B0']

style_handle = assign("""
function(feature, context) {
    const { selected, low, high, mid } = context.hideout;
    const isSelected = selected.includes(feature.properties.neighborhood);
    const ratio = Math.min(Math.max(feature.properties.open_close_ratio || 1, low), high);

    let r, g, b;
    if (ratio < mid) {
        const t = (ratio - low) / (mid - low);
        r = 220;
        g = Math.round(220 * t);
        b = Math.round(220 * t);
    } else {
        const t = (ratio - mid) / (high - mid);
        r = Math.round(220 * (1 - t));
        g = Math.round(220 * (1 - t));
        b = 220;
    }

    return {
        fillColor: isSelected ? '#27ae60' : `rgb(${r},${g},${b})`,
        fillOpacity: isSelected ? 0.9 : 0.85,
        color: 'white',
        weight: 1
    };
}
""")

app.layout = html.Div([
    html.H1('SF Business Openings and Closings'),
    html.P('Selected neighborhoods:'),
    html.Div(
        id='selected-display',
        style={'display': 'flex', 'gap': '8px', 'padding': '10px 0', 'flexWrap': 'wrap'}
    ),
    dcc.Store(id='selected-neighborhoods', data=DEFAULT_SELECTION),
    html.Div('Opening to Closing Ratio by Year', style={
        'fontSize': '25px', 'color': '#666', 'textAlign': 'right', 'marginBottom': '4px'
    }),
    html.Div('Select up to four neighborhoods to compare', style={
        'fontSize': '15px', 'color': '#666', 'textAlign': 'right', 'marginBottom': '4px'
    }),
    html.Div(
        [
            dl.Map(
                center=[37.7749, -122.4194],
                zoom=12,
                children=[
                    dl.TileLayer(url='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'),
                    dl.GeoJSON(
                        id='sf-geojson',
                        data=geojson_by_year[DEFAULT_YEAR],
                        options=dict(style=style_handle),
                        hideout=dict(selected=DEFAULT_SELECTION, low=LOW, high=HIGH, mid=MID),
                        zoomToBounds=True,
                    ),
                    dl.Colorbar(
                        id='colorbar',
                        colorscale=['#dc0000', '#ffffff', '#0000dc'],
                        width=200,
                        height=12,
                        min=LOW,
                        max=HIGH,
                        tickValues=[0.0, 1.0, 2.0],
                        tickText=['0', '1 (equal)', '2+'],
                        position='bottomright',
                    )
                ],
                style={'height': '600px'}
            ),
        ],
        className='map-container'
    ),
    html.Div([
        html.Button('▶ Play', id='play-button', n_clicks=0),
        dcc.Slider(
            id='year-slider',
            min=min(years),
            max=max(years),
            step=1,
            value=DEFAULT_YEAR,
            marks={y: str(y) for y in years},
        ),
    ], style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'marginTop': '8px'}),
    dcc.Interval(id='animation-interval', interval=1000, disabled=True),

    html.Div([
        html.Div([
            html.Div([
                dcc.Graph(id='demographics-chart', config={'displayModeBar': False}),
                html.Div(id='income-display', style={
                    'display': 'flex',
                    'gap': '24px',
                    'justifyContent': 'center',
                    'flexWrap': 'wrap',
                    'padding': '8px 0'
                })
            ], style={
                'background': '#f5f5f5',
                'border': '2px dashed #ddd',
                'borderRadius': '12px',
                'padding': '16px',
                'flex': 1,
                'overflow': 'hidden'
            }),
            html.Div([
                dcc.Dropdown(
                    id='sector-dropdown',
                    options=[{'label': 'All Sectors', 'value': 'All'}] + [{'label': s, 'value': s} for s in sectors],
                    value='All',
                    clearable=False,
                    style={'marginBottom': '8px', 'fontSize': '13px'}
                ),
                dcc.Graph(id='sector-chart', config={'displayModeBar': False})
            ], style={
                'background': '#f5f5f5',
                'border': '2px dashed #ddd',
                'borderRadius': '12px',
                'padding': '16px',
                'flex': 1,
                'overflow': 'hidden'
            }),
        ], style={'display': 'flex', 'gap': '16px'}),
        html.Div([
            html.Div('Chart 3', className='chart-placeholder'),
            html.Div('Chart 4', className='chart-placeholder'),
        ], style={'display': 'flex', 'gap': '16px'}),
    ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '16px', 'marginTop': '24px'})

], className='app-wrapper')


@callback(
    Output('year-slider', 'value'),
    Output('animation-interval', 'disabled'),
    Output('play-button', 'children'),
    Input('animation-interval', 'n_intervals'),
    Input('play-button', 'n_clicks'),
    State('year-slider', 'value'),
    State('animation-interval', 'disabled')
)
def animate(n_intervals, n_clicks, current_year, is_disabled):
    if not n_clicks:
        return current_year, True, '▶ Play'
    if ctx.triggered_id == 'play-button':
        playing = is_disabled
        return current_year, not is_disabled, '⏸ Pause' if playing else '▶ Play'
    if current_year >= max(years):
        return current_year, True, '▶ Play'
    return current_year + 1, False, '⏸ Pause'


@callback(
    Output('sf-geojson', 'data'),
    Output('sf-geojson', 'hideout'),
    Output('selected-neighborhoods', 'data'),
    Output('selected-display', 'children'),
    Input('year-slider', 'value'),
    Input('sf-geojson', 'n_clicks'),
    State('sf-geojson', 'clickData'),
    State('selected-neighborhoods', 'data')
)
def update_map(year, n_clicks, clickData, current_selection):
    if ctx.triggered_id == 'sf-geojson' and n_clicks and clickData:
        clicked = clickData['properties']['neighborhood']
        if clicked in current_selection:
            current_selection.remove(clicked)
        elif len(current_selection) < 4:
            current_selection.append(clicked)

    pills = [html.Span(n, className='pill') for n in current_selection]
    label = pills if current_selection else 'No neighborhoods selected'

    return (
        geojson_by_year[year],
        dict(selected=current_selection, low=LOW, high=HIGH, mid=MID),
        current_selection,
        label
    )


@callback(
    Output('demographics-chart', 'figure'),
    Output('income-display', 'children'),
    Input('selected-neighborhoods', 'data')
)
def update_demographics(selected):
    race_cols   = ['pct_white', 'pct_black', 'pct_asian', 'pct_latina_o', 'pct_other']
    race_labels = ['White', 'Black', 'Asian/PI', 'Latino', 'Other']

    fig = go.Figure()
    for i, neighborhood in enumerate(selected):
        row = demo_df[demo_df['neighborhood'] == neighborhood].iloc[0]
        values = [row[c] * 100 for c in race_cols]
        fig.add_trace(go.Bar(
            name=neighborhood,
            x=race_labels,
            y=values,
            marker_color=NEIGHBORHOOD_COLORS[i]
        ))

    fig.update_layout(
        barmode='group',
        height=220,
        margin=dict(l=20, r=20, t=10, b=20),
        legend=dict(font=dict(size=8)),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(range=[0, 100], title='% of population'),
    )

    income_pills = []
    for i, neighborhood in enumerate(selected):
        row = demo_df[demo_df['neighborhood'] == neighborhood].iloc[0]
        income = row['median_income']
        income_str = f"${income:,.0f}" if pd.notna(income) else 'No data'
        income_pills.append(html.Div([
            html.Div(income_str, style={'fontSize': '18px', 'fontWeight': '600', 'color': NEIGHBORHOOD_COLORS[i]}),
            html.Div(neighborhood, style={'fontSize': '11px', 'color': '#888'})
        ], style={'textAlign': 'center'}))

    return fig, income_pills


@callback(
    Output('sector-chart', 'figure'),
    Input('selected-neighborhoods', 'data'),
    Input('sector-dropdown', 'value')
)
def update_sector_chart(selected, sector):
    fig = go.Figure()

    for i, neighborhood in enumerate(selected):
        if sector == 'All':
            df = yearly_totals[yearly_totals['nhood'] == neighborhood].sort_values('year')
        else:
            df = naics_df[
                (naics_df['neighborhood'] == neighborhood) &
                (naics_df['naics_group'] == sector)
            ].copy().sort_values('year')
            df['open_close_ratio'] = df['opened'] / df['closed'].replace(0, float('nan'))

        fig.add_trace(go.Scatter(
            x=df['year'],
            y=df['open_close_ratio'],
            mode='lines+markers',
            name=neighborhood,
            line=dict(color=NEIGHBORHOOD_COLORS[i], width=2),
            marker=dict(size=5)
        ))

    fig.add_hline(y=1, line_dash='dash', line_color='gray', line_width=1)

    fig.update_layout(
        height=260,
        margin=dict(l=20, r=10, t=10, b=20),
        legend=dict(font=dict(size=9)),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(range=[0, None], title='Open/Close Ratio'),
        xaxis=dict(title='Year')
    )

    return fig


if __name__ == '__main__':
    app.run(debug=True)