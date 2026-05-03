import json
import pandas as pd
import geopandas as gpd
from dash import Dash, dcc, html, Input, Output, State, callback, ctx
import dash_leaflet as dl
from dash_extensions.javascript import assign
import plotly.graph_objects as go

app = Dash(__name__)
server = app.server

sf_map = gpd.read_file('data/processed/open_close_neighs.geojson')
sf_map = sf_map.to_crs(epsg=4326)
sf_map = sf_map[sf_map['biz_stock'] >= 50]

naics_df = pd.read_parquet('data/processed/naics_year_charts.parquet')
yearly_df = pd.read_parquet('data/processed/sf_businesses_nhood_naics.parquet')

yearly_totals = (
    yearly_df
    .groupby(['nhood', 'year'])[['opened', 'closed']]
    .sum()
    .reset_index()
)
yearly_totals['open_close_ratio'] = yearly_totals['opened'] / yearly_totals['closed'].replace(0, float('nan'))

years = sorted(yearly_totals['year'].unique().tolist())

def make_geojson(year):
    year_data = yearly_totals[yearly_totals['year'] == year].set_index('nhood')
    gdf = sf_map.copy()
    gdf['opened']           = gdf['neighborhood'].map(year_data['opened']).fillna(0)
    gdf['closed']           = gdf['neighborhood'].map(year_data['closed']).fillna(0)
    gdf['open_close_ratio'] = gdf['neighborhood'].map(year_data['open_close_ratio'])

    ratios = gdf['open_close_ratio'].dropna()
    raw_low  = float(ratios.quantile(0.05))
    raw_high = float(ratios.quantile(0.95))
    max_dev  = max(abs(raw_high - 1.0), abs(1.0 - raw_low))
    year_low  = round(1.0 - max_dev, 3)
    year_high = round(1.0 + max_dev, 3)

    return json.loads(gdf.to_json()), year_low, year_high

geojson_by_year = {}
bounds_by_year  = {}
for year in years:
    geojson, year_low, year_high = make_geojson(year)
    geojson_by_year[year] = geojson
    bounds_by_year[year]  = (year_low, year_high)

DEFAULT_SELECTION = ['Sunset/Parkside', 'Bayview Hunters Point']
DEFAULT_YEAR = years[-1]
default_low, default_high = bounds_by_year[DEFAULT_YEAR]

style_handle = assign("""
function(feature, context) {
    const { selected, low, high } = context.hideout;
    const isSelected = selected.includes(feature.properties.neighborhood);
    const ratio = feature.properties.open_close_ratio || 1;

    const norm = Math.min(Math.max((ratio - low) / (high - low), 0), 1);

    let r, g, b;
    if (norm < 0.5) {
        const t = norm / 0.5;
        r = Math.round(180 + (240 - 180) * t);
        g = Math.round(30  + (240 - 30)  * t);
        b = Math.round(30  + (240 - 30)  * t);
    } else {
        const t = (norm - 0.5) / 0.5;
        r = Math.round(240 + (30  - 240) * t);
        g = Math.round(240 + (100 - 240) * t);
        b = Math.round(240 + (180 - 240) * t);
    }

    return {
        fillColor: isSelected ? '#58d68d' : `rgb(${r},${g},${b})`,
        fillOpacity: isSelected ? 0.9 : 0.85,
        color: 'white',
        weight: 1
    };
}
""")

color_dict = {
    'Retail':                     'brown',
    'Service':                    'teal',
    'Food & Entertainment':       'orange',
    'Personal Services':          'lightblue',
    'Education & Health':         'purple',
    'Manufacturing & Industrial': 'red',
    'Utilities & Construction':   'blue'
}

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
                        hideout=dict(selected=DEFAULT_SELECTION, low=default_low, high=default_high),
                        zoomToBounds=True,
                    ),
                    dl.Colorbar(
                        id='colorbar',
                        colorscale=['#b41e1e', '#f0f0f0', '#1e64b4'],
                        width=200,
                        height=12,
                        min=default_low,
                        max=default_high,
                        position='bottomright',
                    )
                ],
                style={'height': '600px'}
            ),
        ],
        className='map-container'
    ),
    dcc.Slider(
        id='year-slider',
        min=min(years),
        max=max(years),
        step=1,
        value=DEFAULT_YEAR,
        marks={y: str(y) for y in years},
    ),

    html.Div([
        html.Div([
            html.Div('Chart 1', className='chart-placeholder'),
            html.Div([
                dcc.RadioItems(
                    id='metric-toggle',
                    options=[
                        {'label': 'Openings', 'value': 'opened'},
                        {'label': 'Closings', 'value': 'closed'},
                    ],
                    value='opened',
                    inline=True,
                    style={'marginBottom': '8px', 'fontSize': '13px'}
                ),
                html.Div(id='sector-charts', style={'display': 'flex', 'gap': '8px', 'flexWrap': 'wrap'})
            ], style={
                'background': '#f5f5f5',
                'border': '2px dashed #ddd',
                'borderRadius': '12px',
                'padding': '16px',
                'flex': 1,
                'minHeight': '300px',
                'maxHeight': '300px',
                'overflow': 'hidden'
            }),
        ], style={'display': 'flex', 'gap': '16px', 'height': '300px'}),
        html.Div([
            html.Div('Chart 3', className='chart-placeholder'),
            html.Div('Chart 4', className='chart-placeholder'),
        ], style={'display': 'flex', 'gap': '16px', 'height': '300px'}),
    ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '16px', 'marginTop': '24px'})

], className='app-wrapper')


@callback(
    Output('sf-geojson', 'data'),
    Output('sf-geojson', 'hideout'),
    Output('colorbar', 'min'),
    Output('colorbar', 'max'),
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

    year_low, year_high = bounds_by_year[year]
    pills = [html.Span(n, className='pill') for n in current_selection]
    label = pills if current_selection else 'No neighborhoods selected'

    return (
        geojson_by_year[year],
        dict(selected=current_selection, low=year_low, high=year_high),
        year_low,
        year_high,
        current_selection,
        label
    )


@callback(
    Output('sector-charts', 'children'),
    Input('selected-neighborhoods', 'data'),
    Input('metric-toggle', 'value')
)
def update_sector_charts(selected, metric):
    if not selected:
        return []

    metric_max = naics_df[metric].max()
    chart_height = 260 if len(selected) <= 2 else 200

    charts = []
    for neighborhood in selected:
        df = naics_df[naics_df['neighborhood'] == neighborhood]

        fig = go.Figure()
        for sector in df['naics_group'].unique():
            sector_df = df[df['naics_group'] == sector].sort_values('year')
            fig.add_trace(go.Scatter(
                x=sector_df['year'],
                y=sector_df[metric],
                mode='lines',
                name=sector,
                line=dict(color=color_dict.get(sector, 'gray'))
            ))

        fig.update_layout(
            title=dict(text=neighborhood, font=dict(size=11)),
            height=chart_height,
            margin=dict(l=20, r=10, t=30, b=20),
            legend=dict(font=dict(size=8)),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            yaxis=dict(range=[0, metric_max])
        )

        charts.append(dcc.Graph(
            figure=fig,
            style={'flex': 1, 'minWidth': 0}
        ))

    return charts


if __name__ == '__main__':
    app.run(debug=True)