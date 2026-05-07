import json
import pandas as pd
import geopandas as gpd
from dash import Dash, dcc, html, Input, Output, State, callback, ctx
import dash_leaflet as dl
from dash_extensions.javascript import assign
import plotly.graph_objects as go

app = Dash(__name__)
server = app.server

# ── data ──────────────────────────────────────────────────────────────────────
neighs_year = pd.read_parquet('data/processed/app/neighs_year.parquet')
naics_neighs = pd.read_parquet('data/processed/app/naics_neighs.parquet')
sf_neigh    = gpd.read_file('data/processed/app/neighborhoods.geojson')
demo        = pd.read_parquet('data/processed/app/demographics.parquet')
city_demo   = pd.read_parquet('data/processed/app/demographics_city.parquet')
resilience           = pd.read_parquet('data/processed/app/resilience.parquet')
resilience_by_sector = pd.read_parquet('data/processed/app/resilience_by_sector.parquet')

years   = sorted(neighs_year['year'].unique().tolist())
sectors = sorted(naics_neighs['naics_group'].unique().tolist())

# need to make a new geojson out of the neighs_year 
def make_geojson(year, sector='All'):
    """Merge neighborhood geometry with business stats for the given year/sector."""
    if sector == 'All':
        year_data = neighs_year[neighs_year['year'] == year][
            ['neighborhood', 'opened', 'closed', 'open_close_ratio']
        ]
    else:
        # naics_neighs doesn't carry a pre-computed ratio column
        sector_data = naics_neighs[
            (naics_neighs['naics_group'] == sector) & (naics_neighs['year'] == year)
        ][['neighborhood', 'opened', 'closed']].copy()
        sector_data['open_close_ratio'] = (
            sector_data['opened'] / sector_data['closed'].replace(0, float('nan'))
        )
        year_data = sector_data

    gdf = sf_neigh.merge(year_data, on='neighborhood', how='left')
    for idx, row in gdf.iterrows():
        ratio = row['open_close_ratio']
        gdf.at[idx, 'tooltip'] = (
            f"<b>{row['neighborhood']}</b><br>"
            f"Opened: {int(row['opened']) if pd.notna(row['opened']) else 'N/A'}<br>"
            f"Closed: {int(row['closed']) if pd.notna(row['closed']) else 'N/A'}<br>"
            f"Ratio: {f'{ratio:.2f}' if pd.notna(ratio) else 'N/A'}"
        )
    return json.loads(gdf.to_json())


# ── constants ─────────────────────────────────────────────────────────────────
default_selection = []
default_year   = 2024
default_sector = 'All'

colors     = ['#378ADD', '#E87040', '#4CAF50', '#9C27B0']  # up to 4 neighborhoods
city_color = '#2C7BB6'
race_cols  = ['pct_white', 'pct_black', 'pct_asian', 'pct_latina_o', 'pct_other']
race_labels = ['White', 'Black', 'Asian/PI', 'Latino', 'Other']

card = {
    'background': 'white',
    'border': '1px solid #e2e4e9',
    'borderRadius': '8px',
    'padding': '20px',
    'flex': 1,
    'overflow': 'hidden',
    'boxShadow': '0 2px 8px rgba(0,0,0,0.06)',
}

# shared axis style for plotly charts
axis = dict(showgrid=True, gridcolor='#f5f5f5', zeroline=False, tickfont=dict(size=10))


# ── map styling ───────────────────────────────────────────────────────────────
# red = more closings, blue = more openings; selected neighborhoods go green
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
        opacity: 1,
    };
}
""")


# ── layout ────────────────────────────────────────────────────────────────────
app.layout = html.Div([

    html.H1('San Francisco Neighborhood Business Trends'),

    # sector filter — sticky so it stays visible while scrolling through charts
    html.Div([
        html.Span('Sector:', style={'fontSize': '13px', 'fontWeight': '600', 'color': '#374151'}),
        dcc.Dropdown(
            id='sector-dropdown',
            options=[{'label': 'All Sectors', 'value': 'All'}] +
                    [{'label': s, 'value': s} for s in sectors],
            value=default_sector,
            clearable=False,
            style={'width': '260px', 'fontSize': '13px'},
        ),
    ], className='sector-bar'),

    html.P('Selected neighborhoods:'),
    html.Div(id='selected-display',
             style={'display': 'flex', 'gap': '8px', 'padding': '10px 0', 'flexWrap': 'wrap'}),
    dcc.Store(id='selected-neighborhoods', data=default_selection),

    # map
    html.Div([
        html.Div([
            html.Div('Opening to Closing Ratio by Year',
                     style={'fontSize': '18px', 'fontWeight': '700', 'color': '#1a1a2e', 'lineHeight': '1.2'}),
            html.Div('Select up to four neighborhoods to compare',
                     style={'fontSize': '12px', 'color': '#6b7280', 'marginTop': '2px'}),
        ], className='map-overlay'),
        dl.Map(
            center=[37.7749, -122.4194],
            zoom=12,
            children=[
                dl.TileLayer(url='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'),
                dl.GeoJSON(
                    id='sf-geojson',
                    data=make_geojson(default_year, default_sector),
                    options=dict(style=style_handle),
                    hideout=dict(selected=default_selection, low=0.0, high=2.0, mid=1.0),
                    zoomToBounds=True,
                ),
                dl.Colorbar(
                    colorscale=['#dc0000', '#ffffff', '#0000dc'],
                    width=200, height=12,
                    min=0.0, max=2.0,
                    tickValues=[0.0, 1.0, 2.0],
                    tickText=['0', '1 (equal)', '2+'],
                    position='bottomright',
                ),
            ],
            style={'height': '600px'},
        ),
    ], className='map-container'),

    # year slider + play button
    html.Div([
        html.Button('▶ Play', id='play-button', n_clicks=0),
        dcc.Slider(
            id='year-slider',
            min=min(years), max=max(years), step=1,
            value=default_year,
            marks={y: str(y) for y in years},
        ),
    ], style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'marginTop': '8px'}),
    dcc.Interval(id='animation-interval', interval=1000, disabled=True),

    # charts
    html.Div([
        html.Div([
            # demographics breakdown for selected neighborhoods
            html.Div([
                html.P('Neighborhood Demographics',
                       style={'fontSize': '13px', 'fontWeight': '600', 'color': '#444', 'margin': '0 0 8px 0'}),
                dcc.Graph(id='demographics-chart', config={'displayModeBar': False}),
                html.P('Median Household Income',
                       style={'fontSize': '11px', 'color': '#999', 'textAlign': 'center', 'margin': '4px 0 2px 0'}),
                html.Div(id='income-display',
                         style={'display': 'flex', 'gap': '24px', 'justifyContent': 'center',
                                'flexWrap': 'wrap', 'padding': '4px 0'}),
            ], style=card),

            # open/close ratio over time, filtered by the global sector dropdown
            html.Div([
                html.P('Business Vitality Over Time',
                       style={'fontSize': '13px', 'fontWeight': '600', 'color': '#444', 'margin': '0 0 4px 0'}),
                dcc.Graph(id='sector-chart', config={'displayModeBar': False}),
            ], style=card),

        ], style={'display': 'flex', 'gap': '16px'}),

        # second sector dropdown — visible when sticky bar has scrolled out of view
        html.Div([
            html.Span('Sector:', style={'fontSize': '13px', 'fontWeight': '600', 'color': '#374151'}),
            dcc.Dropdown(
                id='sector-dropdown-2',
                options=[{'label': 'All Sectors', 'value': 'All'}] +
                        [{'label': s, 'value': s} for s in sectors],
                value=default_sector,
                clearable=False,
                style={'width': '260px', 'fontSize': '13px'},
            ),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '10px',
                  'padding': '10px 0', 'borderBottom': '1px solid #e2e4e9'}),

        # pandemic resilience scatter — all sectors, click to select neighborhoods
        html.Div([
            html.Div([
                dcc.Graph(id='resilience-chart', config={'displayModeBar': False}),
            ], style=card),
        ], style={'display': 'flex', 'gap': '16px'}),

    ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '16px', 'marginTop': '24px'}),

], className='app-wrapper')


# ── callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output('sector-dropdown', 'value', allow_duplicate=True),
    Output('sector-dropdown-2', 'value', allow_duplicate=True),
    Input('sector-dropdown', 'value'),
    Input('sector-dropdown-2', 'value'),
    prevent_initial_call=True,
)
def sync_sector_dropdowns(val1, val2):
    return (val1, val1) if ctx.triggered_id == 'sector-dropdown' else (val2, val2)


@callback(
    Output('year-slider', 'max'),
    Output('year-slider', 'marks'),
    Output('year-slider', 'value'),
    Input('sector-dropdown', 'value'),
    State('year-slider', 'value'),
)
def update_slider_range(sector, current_year):
    # sector-level data is only complete through 2024
    max_year = 2024 if sector != 'All' else max(years)
    visible = [y for y in years if y <= max_year]
    return max_year, {y: str(y) for y in visible}, min(current_year, max_year)


@callback(
    Output('year-slider', 'value', allow_duplicate=True),
    Output('animation-interval', 'disabled'),
    Output('play-button', 'children'),
    Input('animation-interval', 'n_intervals'),
    Input('play-button', 'n_clicks'),
    State('year-slider', 'value'),
    State('year-slider', 'max'),
    State('animation-interval', 'disabled'),
    prevent_initial_call=True,
)
def animate(n_intervals, n_clicks, current_year, max_year, is_disabled):
    if not n_clicks:
        return current_year, True, '▶ Play'
    if ctx.triggered_id == 'play-button':
        playing = is_disabled
        return current_year, not is_disabled, '⏸ Pause' if playing else '▶ Play'
    if current_year >= max_year:
        return min(years), True, '▶ Play'
    return current_year + 1, False, '⏸ Pause'


@callback(
    Output('sf-geojson', 'data'),
    Output('sf-geojson', 'hideout'),
    Output('selected-neighborhoods', 'data'),
    Output('selected-display', 'children'),
    Input('year-slider', 'value'),
    Input('sector-dropdown', 'value'),
    Input('sf-geojson', 'n_clicks'),
    Input('resilience-chart', 'clickData'),
    State('sf-geojson', 'clickData'),
    State('selected-neighborhoods', 'data'),
)
def update_map(year, sector, map_clicks, scatter_click, map_click_data, selected):
    if ctx.triggered_id == 'sf-geojson' and map_clicks and map_click_data:
        clicked = map_click_data['properties']['neighborhood']
        if clicked in selected:
            selected.remove(clicked)
        elif len(selected) < 4:
            selected.append(clicked)

    elif ctx.triggered_id == 'resilience-chart' and scatter_click:
        clicked = scatter_click['points'][0]['text']
        if clicked in selected:
            selected.remove(clicked)
        elif len(selected) < 4:
            selected.append(clicked)

    pills = [html.Span(n, className='pill') for n in selected]
    label = pills if selected else 'No neighborhoods selected'

    return (
        make_geojson(year, sector),
        dict(selected=selected, low=0.0, high=2.0, mid=1.0),
        selected,
        label,
    )


@callback(
    Output('demographics-chart', 'figure'),
    Output('income-display', 'children'),
    Input('selected-neighborhoods', 'data'),
)
def update_demographics(selected):
    fig = go.Figure()

    city_row = city_demo.iloc[0]
    fig.add_trace(go.Bar(
        name='San Francisco (citywide)',
        x=race_labels,
        y=[city_row[c] * 100 for c in race_cols],
        marker_color=city_color, opacity=0.5,
    ))

    income_pills = [html.Div([
        html.Div(
            f"${city_row['median_income']:,.0f}" if pd.notna(city_row['median_income']) else 'No data',
            style={'fontSize': '18px', 'fontWeight': '600', 'color': city_color},
        ),
        html.Div('San Francisco', style={'fontSize': '11px', 'color': '#aaa'}),
    ], style={'textAlign': 'center'})]

    for i, neighborhood in enumerate(selected):
        if neighborhood not in demo['neighborhood'].values:
            continue
        row = demo[demo['neighborhood'] == neighborhood].iloc[0]
        fig.add_trace(go.Bar(
            name=neighborhood,
            x=race_labels,
            y=[row[c] * 100 for c in race_cols],
            marker_color=colors[i],
        ))
        income_str = f"${row['median_income']:,.0f}" if pd.notna(row['median_income']) else 'No data'
        income_pills.append(html.Div([
            html.Div(income_str, style={'fontSize': '18px', 'fontWeight': '600', 'color': colors[i]}),
            html.Div(neighborhood, style={'fontSize': '11px', 'color': '#aaa'}),
        ], style={'textAlign': 'center'}))

    fig.update_layout(
        barmode='group', height=200,
        margin=dict(l=20, r=20, t=10, b=20),
        legend=dict(font=dict(size=8), orientation='h', y=-0.3),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(range=[0, 100], title=dict(text='% of population', font=dict(size=11)), **axis),
        xaxis=dict(tickfont=dict(size=10)),
    )
    return fig, income_pills


@callback(
    Output('sector-chart', 'figure'),
    Input('selected-neighborhoods', 'data'),
    Input('sector-dropdown', 'value'),
)
def update_sector_chart(selected, sector):
    fig = go.Figure()

    if sector == 'All':
        city_df = neighs_year[neighs_year['year'] <= 2024].groupby('year')[['opened', 'closed']].sum().reset_index()
    else:
        city_df = naics_neighs[
            (naics_neighs['naics_group'] == sector) & (naics_neighs['year'] <= 2024)
        ].groupby('year')[['opened', 'closed']].sum().reset_index()

    city_df['open_close_ratio'] = city_df['opened'] / city_df['closed'].replace(0, float('nan'))
    fig.add_trace(go.Scatter(
        x=city_df['year'], y=city_df['open_close_ratio'],
        mode='lines+markers', name='SF citywide',
        line=dict(color=city_color, width=2, dash='dot'),
        marker=dict(size=4),
    ))

    for i, neighborhood in enumerate(selected):
        if sector == 'All':
            df = neighs_year[
                (neighs_year['neighborhood'] == neighborhood) & (neighs_year['year'] <= 2024)
            ].sort_values('year')
        else:
            df = naics_neighs[
                (naics_neighs['neighborhood'] == neighborhood) &
                (naics_neighs['naics_group'] == sector) &
                (naics_neighs['year'] <= 2024)
            ].copy().sort_values('year')
            df['open_close_ratio'] = df['opened'] / df['closed'].replace(0, float('nan'))

        fig.add_trace(go.Scatter(
            x=df['year'], y=df['open_close_ratio'],
            mode='lines+markers', name=neighborhood,
            line=dict(color=colors[i], width=2),
            marker=dict(size=5),
        ))

    fig.add_hline(y=1, line_dash='dash', line_color='#ddd', line_width=1)
    fig.update_layout(
        height=240,
        margin=dict(l=20, r=10, t=10, b=20),
        legend=dict(font=dict(size=8), orientation='h', y=-0.3),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(range=[0, None], title=dict(text='Open/Close Ratio', font=dict(size=11)), **axis),
        xaxis=dict(title=dict(text='Year', font=dict(size=11)), tickfont=dict(size=10)),
    )
    return fig


@callback(
    Output('resilience-chart', 'figure'),
    Input('selected-neighborhoods', 'data'),
    Input('sector-dropdown', 'value'),
)
def update_resilience_chart(selected, sector):
    if sector == 'All':
        df = resilience.copy()
    else:
        df = resilience_by_sector[resilience_by_sector['naics_group'] == sector].copy()

    x_min, x_max = df['covid_ratio'].min(), df['covid_ratio'].max()
    y_min, y_max = df['recovery_ratio'].min(), df['recovery_ratio'].max()
    x_pad = (x_max - x_min) * 0.08
    y_pad = (y_max - y_min) * 0.08

    fig = go.Figure()

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
        showlegend=False,
    ))

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
            textfont=dict(size=9, color=colors[i]),
            hovertemplate='<b>%{text}</b><br>Pandemic vitality: %{x:.2f}<br>Recovery vitality: %{y:.2f}<extra></extra>',
            marker=dict(size=14, color=colors[i], line=dict(width=1, color='white')),
            name=neighborhood,
        ))

    fig.add_shape(type='line', x0=1.0, x1=1.0, y0=y_min - y_pad, y1=y_max + y_pad,
                  line=dict(dash='dash', color='#ddd', width=1))
    fig.add_shape(type='line', x0=x_min - x_pad, x1=x_max + x_pad, y0=1.0, y1=1.0,
                  line=dict(dash='dash', color='#ddd', width=1))

    fig.add_annotation(x=1.0, y=y_max + y_pad, text='← equal change →',
                       showarrow=False, xanchor='center', yanchor='bottom',
                       font=dict(size=9, color='#aaa'))
    fig.add_annotation(x=x_max + x_pad, y=1.0, text='equal change',
                       showarrow=False, xanchor='left', yanchor='middle',
                       font=dict(size=9, color='#aaa'), textangle=-90)

    for x, y, text, xanchor, yanchor in [
        (x_max + x_pad * 0.5, y_max + y_pad * 0.5, 'Growth during COVID +<br>Strong recovery',  'right', 'top'),
        (x_min - x_pad * 0.5, y_max + y_pad * 0.5, 'Decline during COVID +<br>Strong recovery', 'left',  'top'),
        (x_min - x_pad * 0.5, y_min - y_pad * 0.5, 'Decline during COVID +<br>Weak recovery',   'left',  'bottom'),
        (x_max + x_pad * 0.5, y_min - y_pad * 0.5, 'Growth during COVID +<br>Weak recovery',    'right', 'bottom'),
    ]:
        fig.add_annotation(x=x, y=y, text=text, showarrow=False,
                           xanchor=xanchor, yanchor=yanchor,
                           font=dict(size=10, color='#555'),
                           bgcolor='rgba(255,255,255,0.85)',
                           bordercolor='#ddd', borderwidth=1, borderpad=6)

    fig.update_layout(
        title=dict(text='Business Pandemic Resilience by Neighborhood', font=dict(size=13, color='#444'), x=0),
        xaxis=dict(title=dict(text='Openings/Closings Ratio During Pandemic (2020–2021)', font=dict(size=11)),
                   range=[x_min - x_pad, x_max + x_pad], **axis),
        yaxis=dict(title=dict(text='Openings/Closings Ratio During Recovery (2022–2024)', font=dict(size=11)),
                   range=[y_min - y_pad, y_max + y_pad], **axis),
        height=420,
        margin=dict(l=20, r=20, t=40, b=20),
        plot_bgcolor='white',
        paper_bgcolor='rgba(0,0,0,0)',
        legend=dict(font=dict(size=9)),
        font=dict(family='-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif'),
    )
    return fig


if __name__ == '__main__':
    app.run(debug=True)
