import json
import pandas as pd
import geopandas as gpd
from dash import Dash, dcc, html, Input, Output, State, callback, ctx
import dash_leaflet as dl
from dash_extensions.javascript import assign
import plotly.graph_objects as go

# ── App ───────────────────────────────────────────────────────────────────────
app = Dash(__name__)
server = app.server

# ── Data ──────────────────────────────────────────────────────────────────────
neighs_year_gdf  = gpd.read_parquet('data/processed/ALL_openings_closings_by_neighs_year.parquet').to_crs(epsg=4326)
neighs_year_gdf  = neighs_year_gdf[neighs_year_gdf['year'] >= 2019]

naics_neighs_gdf = gpd.read_parquet('data/processed/ALL_openings_closings_by_naics_neighs_year.parquet').to_crs(epsg=4326)
naics_neighs_gdf = naics_neighs_gdf[naics_neighs_gdf['year'] >= 2019]

sf_neigh         = gpd.read_file('data/processed/polygons/sf_neighborhoods.geojson').to_crs(epsg=4326)
demo_df          = pd.read_parquet('data/processed/demographics_by_neighs.parquet')
demo_df          = demo_df[['neighborhood', 'median_income', 'pct_white', 'pct_black',
                             'pct_asian', 'pct_latina_o', 'pct_other']].drop_duplicates('neighborhood')
sf_city_demo     = pd.read_parquet('data/processed/demographics_sf_city.parquet')
resilience_df    = pd.read_parquet('data/processed/pandemic_resilience.parquet')

neighs_year_gdf['open_close_ratio'] = (
    neighs_year_gdf['opened'] / neighs_year_gdf['closed'].replace(0, float('nan'))
)

years   = sorted(neighs_year_gdf['year'].unique().tolist())
sectors = sorted(naics_neighs_gdf['naics_group'].unique().tolist())

# compute once at load time after filtering to 2019+
all_totals = (
    neighs_year_gdf[neighs_year_gdf['year'].between(2020, 2024)]
    .groupby('neighborhood')[['opened', 'closed']]
    .sum()
    .reset_index()
)
all_totals['total'] = all_totals['opened'] + all_totals['closed']
active_neighs = set(all_totals[all_totals['total'] >= 500]['neighborhood'])

# filter both geodataframes
neighs_year_gdf  = neighs_year_gdf[neighs_year_gdf['neighborhood'].isin(active_neighs)]
naics_neighs_gdf = naics_neighs_gdf[naics_neighs_gdf['neighborhood'].isin(active_neighs)]
sf_neigh         = sf_neigh[sf_neigh['neighborhood'].isin(active_neighs)]

# ── Constants ─────────────────────────────────────────────────────────────────
LOW  = 0.0
HIGH = 2.0
MID  = 1.0
DEFAULT_SELECTION   = []
DEFAULT_YEAR        = 2024
NEIGHBORHOOD_COLORS = ['#378ADD', '#E87040', '#4CAF50', '#9C27B0']
CITY_COLOR          = '#2C7BB6'  # deep blue
RACE_COLS           = ['pct_white', 'pct_black', 'pct_asian', 'pct_latina_o', 'pct_other']
RACE_LABELS         = ['White', 'Black', 'Asian/PI', 'Latino', 'Other']

CHART_STYLE = {
    'background': 'white',
    'border': '1px solid #e8e8e8',
    'borderRadius': '12px',
    'padding': '16px',
    'flex': 1,
    'overflow': 'hidden',
    'boxShadow': '0 1px 4px rgba(0,0,0,0.06)'
}

AXIS_STYLE = dict(
    showgrid=True,
    gridcolor='#f5f5f5',
    zeroline=False,
    tickfont=dict(size=10)
)

# ── GeoJSON cache ─────────────────────────────────────────────────────────────
def make_geojson(year):
    gdf = sf_neigh[['neighborhood', 'geometry']].merge(
        neighs_year_gdf[neighs_year_gdf['year'] == year][
            ['neighborhood', 'opened', 'closed', 'open_close_ratio']
        ],
        on='neighborhood', how='left'
    )
    for idx, row in gdf.iterrows():
        ratio     = row['open_close_ratio']
        ratio_str = f"{ratio:.2f}" if pd.notna(ratio) else "N/A"
        gdf.at[idx, 'tooltip'] = (
            f"<b>{row['neighborhood']}</b><br>"
            f"Opened: {int(row['opened']) if pd.notna(row['opened']) else 'N/A'}<br>"
            f"Closed: {int(row['closed']) if pd.notna(row['closed']) else 'N/A'}<br>"
            f"Ratio: {ratio_str}"
        )
    return json.loads(gdf.to_json())

geojson_by_year = {year: make_geojson(year) for year in years}

# ── Map style ─────────────────────────────────────────────────────────────────
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
        fillOpacity: 1,
        color: 'white',
        weight: 2,
        opacity: 1
    };
}
""")

# ── Layout ────────────────────────────────────────────────────────────────────
app.layout = html.Div([

    # header
    html.H1('SF Business Openings and Closings'),
    html.P('Selected neighborhoods:'),
    html.Div(
        id='selected-display',
        style={'display': 'flex', 'gap': '8px', 'padding': '10px 0', 'flexWrap': 'wrap'}
    ),
    dcc.Store(id='selected-neighborhoods', data=DEFAULT_SELECTION),
    html.Div('Opening to Closing Ratio by Year', style={
        'fontSize': '22px', 'color': '#555', 'textAlign': 'right', 'marginBottom': '2px'
    }),
    html.Div('Select up to four neighborhoods to compare', style={
        'fontSize': '13px', 'color': '#999', 'textAlign': 'right', 'marginBottom': '8px'
    }),

    # map
    html.Div([
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
                    colorscale=['#dc0000', '#ffffff', '#0000dc'],
                    width=200, height=12,
                    min=LOW, max=HIGH,
                    tickValues=[0.0, 1.0, 2.0],
                    tickText=['0', '1 (equal)', '2+'],
                    position='bottomright',
                )
            ],
            style={'height': '600px'}
        ),
    ], className='map-container'),

    # year slider + play button
    html.Div([
        html.Button('▶ Play', id='play-button', n_clicks=0),
        dcc.Slider(
            id='year-slider',
            min=min(years), max=max(years), step=1,
            value=DEFAULT_YEAR,
            marks={y: str(y) for y in years},
        ),
    ], style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'marginTop': '8px'}),
    dcc.Interval(id='animation-interval', interval=1000, disabled=True),

    # charts row 1: demographics + sector vitality
    html.Div([
        html.Div([
            html.Div([
                html.P('Neighborhood Demographics',
                       style={'fontSize': '13px', 'fontWeight': '600', 'color': '#444', 'margin': '0 0 8px 0'}),
                dcc.Graph(id='demographics-chart', config={'displayModeBar': False}),
                html.P('Median Household Income',
                       style={'fontSize': '11px', 'color': '#999', 'textAlign': 'center', 'margin': '4px 0 2px 0'}),
                html.Div(id='income-display', style={
                    'display': 'flex', 'gap': '24px',
                    'justifyContent': 'center', 'flexWrap': 'wrap', 'padding': '4px 0'
                })
            ], style=CHART_STYLE),
            html.Div([
                html.P('Business Vitality Over Time',
                       style={'fontSize': '13px', 'fontWeight': '600', 'color': '#444', 'margin': '0 0 4px 0'}),
                dcc.Dropdown(
                    id='sector-dropdown',
                    options=[{'label': 'All Sectors', 'value': 'All'}] +
                            [{'label': s, 'value': s} for s in sectors],
                    value='All', clearable=False,
                    style={'marginBottom': '8px', 'fontSize': '13px'}
                ),
                dcc.Graph(id='sector-chart', config={'displayModeBar': False})
            ], style=CHART_STYLE),
        ], style={'display': 'flex', 'gap': '16px'}),

        # charts row 2: pandemic resilience
        html.Div([
            html.Div([
                dcc.Graph(id='resilience-chart', config={'displayModeBar': False})
            ], style=CHART_STYLE),
        ], style={'display': 'flex', 'gap': '16px'}),

    ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '16px', 'marginTop': '24px'})

], className='app-wrapper')


# ── Callbacks ─────────────────────────────────────────────────────────────────

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
        return min(years), True, '▶ Play'
    return current_year + 1, False, '⏸ Pause'


@callback(
    Output('sf-geojson', 'data'),
    Output('sf-geojson', 'hideout'),
    Output('selected-neighborhoods', 'data'),
    Output('selected-display', 'children'),
    Input('year-slider', 'value'),
    Input('sf-geojson', 'n_clicks'),
    Input('resilience-chart', 'clickData'),
    State('sf-geojson', 'clickData'),
    State('selected-neighborhoods', 'data')
)
def update_map(year, map_clicks, scatter_click, map_click_data, current_selection):
    if ctx.triggered_id == 'sf-geojson' and map_clicks and map_click_data:
        clicked = map_click_data['properties']['neighborhood']
        if clicked in current_selection:
            current_selection.remove(clicked)
        elif len(current_selection) < 4:
            current_selection.append(clicked)

    elif ctx.triggered_id == 'resilience-chart' and scatter_click:
        clicked = scatter_click['points'][0]['text']
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
    fig = go.Figure()

    # citywide baseline always shown in gray
    city_row    = sf_city_demo.iloc[0]
    city_values = [city_row[c] * 100 for c in RACE_COLS]
    fig.add_trace(go.Bar(
        name='San Francisco (citywide)',
        x=RACE_LABELS, y=city_values,
        marker_color=CITY_COLOR, opacity=0.5
    ))

    income_pills = [html.Div([
        html.Div(
            f"${city_row['median_income']:,.0f}" if pd.notna(city_row['median_income']) else 'No data',
            style={'fontSize': '18px', 'fontWeight': '600', 'color': CITY_COLOR}
        ),
        html.Div('San Francisco', style={'fontSize': '11px', 'color': '#aaa'})
    ], style={'textAlign': 'center'})]

    # selected neighborhoods
    for i, neighborhood in enumerate(selected):
        if neighborhood not in demo_df['neighborhood'].values:
            continue
        row    = demo_df[demo_df['neighborhood'] == neighborhood].iloc[0]
        values = [row[c] * 100 for c in RACE_COLS]
        fig.add_trace(go.Bar(
            name=neighborhood, x=RACE_LABELS, y=values,
            marker_color=NEIGHBORHOOD_COLORS[i]
        ))
        income     = row['median_income']
        income_str = f"${income:,.0f}" if pd.notna(income) else 'No data'
        income_pills.append(html.Div([
            html.Div(income_str, style={'fontSize': '18px', 'fontWeight': '600', 'color': NEIGHBORHOOD_COLORS[i]}),
            html.Div(neighborhood, style={'fontSize': '11px', 'color': '#aaa'})
        ], style={'textAlign': 'center'}))

    fig.update_layout(
        barmode='group', height=200,
        margin=dict(l=20, r=20, t=10, b=20),
        legend=dict(font=dict(size=8), orientation='h', y=-0.3),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(range=[0, 100], title=dict(text='% of population', font=dict(size=11)), **AXIS_STYLE),
        xaxis=dict(tickfont=dict(size=10)),
    )
    return fig, income_pills


@callback(
    Output('sector-chart', 'figure'),
    Input('selected-neighborhoods', 'data'),
    Input('sector-dropdown', 'value')
)
def update_sector_chart(selected, sector):
    fig = go.Figure()

    # citywide baseline
    if sector == 'All':
        city_df = neighs_year_gdf[neighs_year_gdf['year'] <= 2024].groupby('year')[['opened', 'closed']].sum().reset_index()
    else:
        city_df = naics_neighs_gdf[
            (naics_neighs_gdf['naics_group'] == sector) &
            (naics_neighs_gdf['year'] <= 2024)
        ].groupby('year')[['opened', 'closed']].sum().reset_index()

    city_df['open_close_ratio'] = city_df['opened'] / city_df['closed'].replace(0, float('nan'))
    fig.add_trace(go.Scatter(
        x=city_df['year'], y=city_df['open_close_ratio'],
        mode='lines+markers', name='SF citywide',
        line=dict(color=CITY_COLOR, width=2, dash='dot'),
        marker=dict(size=4)
    ))

    # selected neighborhoods
    for i, neighborhood in enumerate(selected):
        if sector == 'All':
            df = neighs_year_gdf[
                (neighs_year_gdf['neighborhood'] == neighborhood) &
                (neighs_year_gdf['year'] <= 2024)
            ].sort_values('year')
        else:
            df = naics_neighs_gdf[
                (naics_neighs_gdf['neighborhood'] == neighborhood) &
                (naics_neighs_gdf['naics_group'] == sector) &
                (naics_neighs_gdf['year'] <= 2024)
            ].copy().sort_values('year')
            df['open_close_ratio'] = df['opened'] / df['closed'].replace(0, float('nan'))

        fig.add_trace(go.Scatter(
            x=df['year'], y=df['open_close_ratio'],
            mode='lines+markers', name=neighborhood,
            line=dict(color=NEIGHBORHOOD_COLORS[i], width=2),
            marker=dict(size=5)
        ))

    fig.add_hline(y=1, line_dash='dash', line_color='#ddd', line_width=1)
    fig.update_layout(
        height=240,
        margin=dict(l=20, r=10, t=10, b=20),
        legend=dict(font=dict(size=8), orientation='h', y=-0.3),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(range=[0, None], title=dict(text='Open/Close Ratio', font=dict(size=11)), **AXIS_STYLE),
        xaxis=dict(title=dict(text='Year', font=dict(size=11)), tickfont=dict(size=10))
    )
    return fig


@callback(
    Output('resilience-chart', 'figure'),
    Input('selected-neighborhoods', 'data')
)
def update_resilience_chart(selected):
    df = resilience_df.copy()

    x_min, x_max = df['covid_ratio'].min(), df['covid_ratio'].max()
    y_min, y_max = df['recovery_ratio'].min(), df['recovery_ratio'].max()
    x_pad = (x_max - x_min) * 0.08
    y_pad = (y_max - y_min) * 0.08

    fig = go.Figure()

    # all unselected neighborhoods
    unselected = df[~df['neighborhood'].isin(selected)]
    fig.add_trace(go.Scatter(
        x=unselected['covid_ratio'],
        y=unselected['recovery_ratio'],
        mode='markers+text',
        text=unselected['neighborhood'],
        textposition='top center',
        textfont=dict(size=7, color='#bbb'),
        hovertemplate='<b>%{text}</b><br>Pandemic vitality: %{x:.2f}<br>Recovery vitality: %{y:.2f}<extra></extra>',
        marker=dict(size=8, color='#5B8DB8', opacity=0.9, line=dict(width=0)),
        showlegend=False
    ))

    # selected neighborhoods highlighted
    for i, neighborhood in enumerate(selected):
        row = df[df['neighborhood'] == neighborhood]
        if row.empty:
            continue
        fig.add_trace(go.Scatter(
            x=row['covid_ratio'],
            y=row['recovery_ratio'],
            mode='markers+text',
            text=row['neighborhood'],
            textposition='top center',
            textfont=dict(size=9, color=NEIGHBORHOOD_COLORS[i]),
            hovertemplate='<b>%{text}</b><br>Pandemic vitality: %{x:.2f}<br>Recovery vitality: %{y:.2f}<extra></extra>',
            marker=dict(size=14, color=NEIGHBORHOOD_COLORS[i], line=dict(width=1, color='white')),
            name=neighborhood
        ))

    # quadrant lines at 1 (equal openings and closings)
    fig.add_shape(type='line', x0=1.0, x1=1.0, y0=y_min - y_pad, y1=y_max + y_pad,
                  line=dict(dash='dash', color='#ddd', width=1))
    fig.add_shape(type='line', x0=x_min - x_pad, x1=x_max + x_pad, y0=1.0, y1=1.0,
                  line=dict(dash='dash', color='#ddd', width=1))

    # midline labels
    fig.add_annotation(
        x=1.0, y=y_max + y_pad,
        text='← equal change →',
        showarrow=False,
        xanchor='center', yanchor='bottom',
        font=dict(size=9, color='#aaa'),
    )
    fig.add_annotation(
        x=x_max + x_pad, y=1.0,
        text='equal change',
        showarrow=False,
        xanchor='left', yanchor='middle',
        font=dict(size=9, color='#aaa'),
        textangle=-90,
    )

    # quadrant labels at corners
    for x, y, text, xanchor, yanchor in [
        (x_max + x_pad * 0.5, y_max + y_pad * 0.5, 'Growth during COVID +<br>Strong recovery', 'right', 'top'),
        (x_min - x_pad * 0.5, y_max + y_pad * 0.5, 'Decline during COVID +<br>Strong recovery',  'left',  'top'),
        (x_min - x_pad * 0.5, y_min - y_pad * 0.5, 'Decline during COVID +<br>Weak recovery',    'left',  'bottom'),
        (x_max + x_pad * 0.5, y_min - y_pad * 0.5, 'Growth during COVID +<br>Weak recovery',   'right', 'bottom'),
    ]:
        fig.add_annotation(
            x=x, y=y, text=text, showarrow=False,
            xanchor=xanchor, yanchor=yanchor,
            font=dict(size=10, color='#555'),
            bgcolor='rgba(255,255,255,0.85)',
            bordercolor='#ddd',
            borderwidth=1,
            borderpad=6
        )

    fig.update_layout(
        title=dict(text='Business Pandemic Resilience by Neighborhood', font=dict(size=13, color='#444'), x=0),
        xaxis=dict(
            title=dict(text='Openings/Closings Ratio During Pandemic (2020–2021)', font=dict(size=11)),
            range=[x_min - x_pad, x_max + x_pad],
            **AXIS_STYLE
        ),
        yaxis=dict(
            title=dict(text='Openings/Closings Ratio During Recovery (2022–2024)', font=dict(size=11)),
            range=[y_min - y_pad, y_max + y_pad],
            **AXIS_STYLE
        ),
        height=420,
        margin=dict(l=20, r=20, t=40, b=20),
        plot_bgcolor='white',
        paper_bgcolor='rgba(0,0,0,0)',
        legend=dict(font=dict(size=9)),
        font=dict(family='-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif')
    )
    return fig


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)