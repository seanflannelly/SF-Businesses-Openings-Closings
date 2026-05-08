"""
SF Business Trends Dashboard

Run with `python app.py` from the repo root. Requires all the parquets in
data/processed/app/ to exist first — run notebooks 01-07 in order to generate them.

The app has a Leaflet map of SF neighborhoods colored by their
opening-to-closing ratio. You can toggle between a recovery period view (2022-2024
aggregated) and a year-by-year slider that animates. Clicking neighborhoods (up to 4) adds them
to the charts below — a demographics breakdown, an open/close ratio over time line
chart, and a survival scatter that plots pre-2020 survival rate vs. post-COVID
recovery. Everything sorts by the sector dropdown at the top.
"""

import json
import pandas as pd
import geopandas as gpd
from dash import Dash, dcc, html, Input, Output, State, callback, ctx
import dash_leaflet as dl
from dash_extensions.javascript import assign
import plotly.graph_objects as go

app = Dash(__name__)
server = app.server  

# --- data ----------------------------------------------------------------
# neighs_year: one row per neighborhood per year, all sectors combined
# naics_neighs: one row per neighborhood per year per sector (one business with multiple codes can appear in multiple sectors)
# survival_by_sector: pre-2020 survival rate + recovery ratio per neighborhood per sector
neighs_year        = pd.read_parquet('data/processed/app/neighs_year.parquet')
naics_neighs       = pd.read_parquet('data/processed/app/naics_neighs.parquet')
sf_neigh           = gpd.read_file('data/processed/app/neighborhoods.geojson')
demo               = pd.read_parquet('data/processed/app/demographics.parquet')
city_demo          = pd.read_parquet('data/processed/app/demographics_city.parquet').iloc[0]
survival_by_sector = pd.read_parquet('data/processed/app/survival_by_sector.parquet')
survival_stats     = pd.read_parquet('data/processed/app/survival_stats.parquet').set_index('naics_group').to_dict('index')

years   = sorted(neighs_year['year'].unique().tolist())
sectors = sorted(s for s in naics_neighs['naics_group'].unique() if s != 'No Code') + ['No Code'] #ensuring no code is at the bottom

# need to make a new geojson out of the neighs_year for the tooltip property in leaflet
# this gets called on map startup and on update_map callback
def make_geojson(year, sector='All', selected=[]):
    if year == 'recovery':
        # aggregate 2022-2024 for the recovery period view
        if sector == 'All':
            year_data = neighs_year[neighs_year['year'].between(2022, 2024)].groupby('neighborhood')[['opened', 'closed']].sum().reset_index()
        else:
            year_data = naics_neighs[(naics_neighs['naics_group'] == sector) & (naics_neighs['year'].between(2022, 2024))].groupby('neighborhood')[['opened', 'closed']].sum().reset_index()
        year_data['open_close_ratio'] = year_data['opened'] / year_data['closed'].replace(0, float('nan'))
    elif sector == 'All':
        year_data = neighs_year[neighs_year['year'] == year][
            ['neighborhood', 'opened', 'closed', 'open_close_ratio']
        ]
    else:
        year_data = naics_neighs[
            (naics_neighs['naics_group'] == sector) & (naics_neighs['year'] == year)
        ][['neighborhood', 'opened', 'closed', 'open_close_ratio']].copy()

    gdf = sf_neigh.merge(year_data, on='neighborhood', how='left')
    gdf['tooltip'] = (
        '<b>' + gdf['neighborhood'] + '</b><br>' +
        'Opened: ' + gdf['opened'].fillna('N/A').astype(str) + '<br>' +
        'Closed: ' + gdf['closed'].fillna('N/A').astype(str) + '<br>' +
        'Ratio: ' + gdf['open_close_ratio'].round(2).fillna('N/A').astype(str)
    )
    geojson = json.loads(gdf.to_json())
    # selected features sorted to end so they're painted last in SVG, keeping their border on top
    geojson['features'].sort(key=lambda f: f['properties']['neighborhood'] in selected)
    return geojson


# --- constants -----------------------------------------------------
default_selection = []
default_year   = 2019
default_sector = 'All'
default_mode   = 'recovery'

slider_years = {}
for y in years:
    slider_years[int(y)] = str(y)

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
axis = dict(showgrid=True, gridcolor='whitesmoke', zeroline=False, tickfont=dict(size=10))


# --- map styling ---------------------------------------------------
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
        fillColor: `rgb(${r},${g},${b})`,
        fillOpacity: 1,
        color: isSelected ? '#27ae60' : 'white',
        weight: isSelected ? 4 : 2,
        opacity: 1,
    };
}
""")


# --- html layout --------------------------------------------------------
#each 'id' is linked to a callback below
app.layout = html.Div([

    html.H1('San Francisco Neighborhood Business Trends', style={'padding':'1px'}),

    # sector filter dropdown
    html.Div([
        html.Span('Choose a business sector to filter by:', style={'fontSize': '13px', 'fontWeight': '600', 'color': '#374151'}),
        dcc.Dropdown(
            id='sector-dropdown',
            options=[{'label': 'All Sectors', 'value': 'All'}] +
                    [{'label': s, 'value': s} for s in sectors],
            value=default_sector,
            clearable=False,
            style={'width': '260px', 'fontSize': '13px'},
        ),
    ], className='sector-bar'),

    #selected neighborhood indicator with pillbox styling
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
                #basemap
                dl.TileLayer(url='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'),
                #active map, calling make_geojson function above to update data
                dl.GeoJSON(
                    id='sf-geojson',
                    data=make_geojson(default_mode, default_sector),
                    options=dict(style=style_handle),
                    hideout=dict(selected=default_selection, low=0.0, high=2.0, mid=1.0),
                    zoomToBounds=True,
                ),
                #color bar
                dl.Colorbar(
                    colorscale=['#dc0000', 'white', '#0000dc'],
                    width=200, height=12,
                    min=0.0, max=2.0,
                    tickValues=[0.0, 2.0],
                    tickText=['0<br>More closings', '2+<br>More openings'],
                    position='bottomright',
                ),
            ],
            style={'height': '600px'},
        ),
    ], className='map-container'),

    # toggle between recovery period aggregate and year-by-year view
    dcc.RadioItems(
        id='map-mode',
        options=[
            {'label': 'Recovery Period (2022–2024)', 'value': 'recovery'},
            {'label': 'Year by Year', 'value': 'year'},
        ],
        value=default_mode,
        inline=True,
        style={'fontSize': '13px', 'marginTop': '12px', 'gap': '16px'},
    ),

    # year slider + play button — hidden when recovery mode is active
    html.Div([
        html.Button('▶ Play', id='play-button', n_clicks=0),
        dcc.Slider(
            id='year-slider',
            min=min(years), max=max(years), step=1,
            value=default_year,
            marks=slider_years,
        ),
    ], id='slider-container',
       style={'display': 'none', 'alignItems': 'center', 'gap': '12px', 'marginTop': '8px'}),
    dcc.Interval(id='animation-interval', interval=1000, disabled=True),

    # charts
    html.Div([
        html.Div([
            # demographics breakdown for selected neighborhoods
            html.Div([
                html.P('Neighborhood Demographics',
                       style={'fontSize': '13px', 'fontWeight': '600', 'color': 'dimgray', 'margin': '0 0 8px 0'}),
                dcc.Graph(id='demographics-chart', config={'displayModeBar': False}),
                html.P('Median Household Income',
                       style={'fontSize': '11px', 'color': 'darkgray', 'textAlign': 'center', 'margin': '4px 0 2px 0'}),
                html.Div(id='income-display',
                         style={'display': 'flex', 'gap': '24px', 'justifyContent': 'center',
                                'flexWrap': 'wrap', 'padding': '4px 0'}),
                html.P('Source: U.S. Census Bureau, American Community Survey 5-Year Estimates',
                       style={'fontSize': '10px', 'color': 'darkgray', 'margin': '8px 0 0 0'}),
            ], style=card),

            # open/close ratio over time, filtered by the global sector dropdown
            html.Div([
                html.P(id='sector-chart-title',
                       style={'fontSize': '13px', 'fontWeight': '600', 'color': 'dimgray', 'margin': '0 0 4px 0'}),
                dcc.Graph(id='sector-chart', config={'displayModeBar': False}),
            ], style=card),

        ], style={'display': 'flex', 'gap': '16px'}),

        # second sector dropdown — visible when sticky bar has scrolled out of view
        html.Div([
            html.Span('Choose a business sector to filter by:', style={'fontSize': '13px', 'fontWeight': '600', 'color': '#374151'}),
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

        # survival scatter — click to select neighborhoods
        html.Div([
            html.Div([
                html.Div([
                    html.P(id='survival-chart-title',
                           style={'fontSize': '13px', 'fontWeight': '600', 'color': 'dimgray', 'margin': 0}),
                    html.P('Hover over a point to see details. Click to select a neighborhood.',
                           style={'fontSize': '12px', 'color': 'darkgray', 'margin': 0}),
                ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'baseline', 'marginBottom': '4px'}),
                dcc.Graph(id='survival-chart', config={'displayModeBar': False}),
            ], style=card),
        ], style={'display': 'flex', 'gap': '16px'}),

    ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '16px', 'marginTop': '24px'}),

    html.P('Source: City and County of San Francisco Treasurer & Tax Collector\'s Office',
           style={'fontSize': '10px', 'color': 'darkgray', 'marginTop': '24px'}),

], className='app-wrapper')


# --- callbacks -----------------------------------------------------

#we have two dropdowns because of the scroll, so just making sure they are synced
@callback(
    Output('sector-dropdown', 'value', allow_duplicate=True),
    Output('sector-dropdown-2', 'value', allow_duplicate=True),
    Input('sector-dropdown', 'value'),
    Input('sector-dropdown-2', 'value'),
    prevent_initial_call=True,
)
def sync_sector_dropdowns(val1, val2):
    return (val1, val1) if ctx.triggered_id == 'sector-dropdown' else (val2, val2)


# show/hide the slider based on which map mode is selected
@callback(
    Output('slider-container', 'style'),
    Input('map-mode', 'value'),
)
def toggle_slider(mode):
    if mode == 'recovery':
        return {'display': 'none'}
    return {'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'marginTop': '8px'}


# year slider animation 
@callback(
    Output('year-slider', 'value', allow_duplicate=True),
    Output('animation-interval', 'disabled'),
    Output('play-button', 'children'),
    Input('animation-interval', 'n_intervals'),
    Input('play-button', 'n_clicks'),
    Input('map-mode', 'value'),
    State('year-slider', 'value'),
    State('year-slider', 'max'),
    State('animation-interval', 'disabled'),
    prevent_initial_call=True,
)
def animate(n_intervals, n_clicks, mode, current_year, max_year, is_disabled):
    if mode == 'recovery' or not n_clicks:
        return current_year, True, '▶ Play'
    if ctx.triggered_id == 'play-button':
        return current_year, not is_disabled, '⏸ Pause' if is_disabled else '▶ Play'
    if current_year >= max_year:
        return min(years), True, '▶ Play'
    return current_year + 1, False, '⏸ Pause'


##updating the map whenever the mode or sector is changed, and whenever the year slider is active
@callback(
    Output('sf-geojson', 'data'),
    Output('sf-geojson', 'hideout'), #for javascript styling
    Output('selected-neighborhoods', 'data'),
    Output('selected-display', 'children'),
    Input('year-slider', 'value'),
    Input('sector-dropdown', 'value'),
    Input('map-mode', 'value'),
    Input('sf-geojson', 'n_clicks'),
    Input('survival-chart', 'clickData'),
    State('sf-geojson', 'clickData'),
    State('selected-neighborhoods', 'data'),
)
def update_map(year, sector, mode, map_clicks, scatter_click, map_click_data, selected):
    clicked = None
    
    if ctx.triggered_id == 'sf-geojson' and map_clicks and map_click_data:
        clicked = map_click_data['properties']['neighborhood']
    elif ctx.triggered_id == 'survival-chart' and scatter_click:
        clicked = scatter_click['points'][0]['text']

    if clicked:
        if clicked in selected:
            selected.remove(clicked)
        elif len(selected) < 4:
            selected.append(clicked)

    pills = [html.Span(n, className='pill') for n in selected]
    label = pills if selected else 'No neighborhoods selected'

    return (
        make_geojson('recovery' if mode == 'recovery' else year, sector, selected),
        dict(selected=selected, low=0.0, high=2.0, mid=1.0),
        selected,
        label,
    )


# updating demographics bar chart whenever new neighborhood clicked
@callback(
    Output('demographics-chart', 'figure'),
    Output('income-display', 'children'),
    Input('selected-neighborhoods', 'data'),
)
def update_demographics(selected):
    fig = go.Figure()

    #sf citwide bar constant
    fig.add_trace(go.Bar(
        name='San Francisco (citywide)',
        x=race_labels,
        y=[city_demo[c] * 100 for c in race_cols],
        marker_color=city_color, opacity=0.5,
    ))

    #adding list of median income divs, with SF as constant
    income_pills = [html.Div([
        html.Div(
            f"${city_demo['median_income']:,.0f}" if pd.notna(city_demo['median_income']) else 'No data',
            style={'fontSize': '18px', 'fontWeight': '600', 'color': city_color},
        ),
        html.Div('San Francisco', style={'fontSize': '11px', 'color': 'darkgray'}),
    ], style={'textAlign': 'center'})]

    #picking out each row in selected, then adding a bar for it to the group
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
        #appending the income data to the income_pills list of divs
        income_str = f"${row['median_income']:,.0f}" if pd.notna(row['median_income']) else 'No data'
        income_pills.append(html.Div([
            html.Div(income_str, style={'fontSize': '18px', 'fontWeight': '600', 'color': colors[i]}),
            html.Div(neighborhood, style={'fontSize': '11px', 'color': 'darkgray'}),
        ], style={'textAlign': 'center'}))

    #chart styling, grouping the bars
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



#update the line chart whenever new sector or neighbhorhood selected
@callback(
    Output('sector-chart', 'figure'),
    Output('sector-chart-title', 'children'),
    Input('selected-neighborhoods', 'data'),
    Input('sector-dropdown', 'value'),
)
def update_sector_chart(selected, sector):
    fig = go.Figure()

    if sector == 'All':
        city_df = neighs_year.groupby('year')[['opened', 'closed']].sum().reset_index()
    else:
        city_df = naics_neighs[naics_neighs['naics_group'] == sector].groupby('year')[['opened', 'closed']].sum().reset_index()

    city_df['open_close_ratio'] = city_df['opened'] / city_df['closed'].replace(0, float('nan'))
    fig.add_trace(go.Scatter(
        x=city_df['year'], y=city_df['open_close_ratio'],
        mode='lines+markers', name='SF citywide',
        customdata=city_df[['opened', 'closed']].values,
        hovertemplate='<b>%{fullData.name}</b><br>Opened: %{customdata[0]:,}<br>Closed: %{customdata[1]:,}<br>Ratio: %{y:.2f}<extra></extra>',
        line=dict(color=city_color, width=2, dash='dot'),
        marker=dict(size=4),
    ))

    #grabbing the whole row of whatever neighs are selected
    for i, neighborhood in enumerate(selected):
        if sector == 'All':
            df = neighs_year[neighs_year['neighborhood'] == neighborhood].sort_values('year')
        else:
            df = naics_neighs[
                (naics_neighs['neighborhood'] == neighborhood) &
                (naics_neighs['naics_group'] == sector)
            ].sort_values('year')

        #then plotting that row using the year and ratio, opened/closed on hover
        fig.add_trace(go.Scatter(
            x=df['year'], y=df['open_close_ratio'],
            mode='lines+markers', name=neighborhood,
            customdata=df[['opened', 'closed']].values,
            hovertemplate='<b>%{fullData.name}</b><br>Opened: %{customdata[0]:,}<br>Closed: %{customdata[1]:,}<br>Ratio: %{y:.2f}<extra></extra>',
            line=dict(color=colors[i], width=2),
            marker=dict(size=5),
        ))

    # shaded band over 2020-2021 to mark the pandemic period
    fig.add_vrect(x0=2020, x1=2021.5, fillcolor='gainsboro', opacity=0.3, line_width=0,
                  annotation_text='COVID-19', annotation_position='top left',
                  annotation_font=dict(size=10, color='darkgray'))

    # midline at ratio=1 marks equal openings and closings
    fig.add_hline(y=1, line_dash='dash', line_color='gainsboro', line_width=1)
    
    #chart styling
    fig.update_layout(
        height=240,
        margin=dict(l=20, r=10, t=10, b=20),
        legend=dict(font=dict(size=8), orientation='h', y=-0.3),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(range=[0, None], title=dict(text='Open/Close Ratio', font=dict(size=11)), **axis),
        xaxis=dict(title=dict(text='Year', font=dict(size=11)), tickfont=dict(size=10)),
    )
    return fig, f'Opening/Closing Ratio Over Time for {sector} Businesses'



#survival chart, changes on selection and sector change
@callback(
    Output('survival-chart', 'figure'),
    Output('survival-chart-title', 'children'),
    Input('selected-neighborhoods', 'data'),
    Input('sector-dropdown', 'value'),
)
def update_survival_chart(selected, sector):
    df = survival_by_sector[survival_by_sector['naics_group'] == sector].copy()
    s = survival_stats[sector]

    #setting bounds from precomputed bounds in survival_stats
    x_min, x_max, y_min, y_max = s['x_min'], s['x_max'], s['y_min'], s['y_max']
    x_pad, y_pad, x_mean, citywide_rate = s['x_pad'], s['y_pad'], s['x_mean'], s['citywide_rate']

    #setting hover template, variables in brackets 
    hover = '<b>%{text}</b><br>Survival rate: %{x:.1%}<br>Pre-2020 businesses: %{customdata[0]:,}<br>Opened 2022–2024: %{customdata[1]:,}<br>Closed 2022–2024: %{customdata[2]:,}<br>Open/close ratio: %{y:.2f}<extra></extra>'

    fig = go.Figure()

    #adding baseline scatterdots for unselected
    unselected = df[~df['neighborhood'].isin(selected)]
    fig.add_trace(go.Scatter(
        x=unselected['survival_rate'],
        y=unselected['recovery_ratio'],
        mode='markers',
        text=unselected['neighborhood'],
        textposition='top center',
        textfont=dict(size=7, color='silver'),
        customdata=unselected[['total', 'opened', 'closed']].values,
        hovertemplate=hover,
        marker=dict(size=8, color='#5B8DB8', opacity=0.9, line=dict(width=0)),
        showlegend=False,
    ))

    #grabbing the whole row for selected neighborhoods 
    for i, neighborhood in enumerate(selected):
        row = df[df['neighborhood'] == neighborhood]
        if row.empty: #if no businesses in that neigh/sector combo
            continue 
        #adding a highlighted dot for selected neighs
        fig.add_trace(go.Scatter(
            x=row['survival_rate'],
            y=row['recovery_ratio'],
            mode='markers+text',
            text=row['neighborhood'],
            textposition='top center',
            textfont=dict(size=9, color=colors[i]),
            customdata=row[['total', 'opened', 'closed']].values,
            hovertemplate=hover,
            marker=dict(size=14, color=colors[i], line=dict(width=1, color='white')),
            name=neighborhood,
        ))

    #adding midlines and labels on midlines
    fig.add_shape(type='line', x0=x_mean, x1=x_mean, y0=y_min - y_pad, y1=y_max + y_pad,
                  line=dict(dash='dash', color='gainsboro', width=1))
    fig.add_annotation(x=x_mean, y=y_max + y_pad, text=f'Citywide: {citywide_rate:.0%} survived to 2024',
                       showarrow=False, xanchor='center', yanchor='bottom',
                       font=dict(size=9, color='darkgray'))
    fig.add_shape(type='line', x0=x_min - x_pad, x1=x_max + x_pad, y0=1.0, y1=1.0,
                  line=dict(dash='dash', color='gainsboro', width=1))

    #adding quadrant labels
    for x, y, text, xanchor, yanchor in [
        (x_max + x_pad * 0.5, y_max + y_pad * 0.5, 'High survival +<br>Post-COVID growth',  'right', 'top'),
        (x_min - x_pad * 0.5, y_max + y_pad * 0.5, 'Low survival +<br>Post-COVID growth',   'left',  'top'),
        (x_min - x_pad * 0.5, y_min - y_pad * 0.5, 'Low survival +<br>Post-COVID decline',     'left',  'bottom'),
        (x_max + x_pad * 0.5, y_min - y_pad * 0.5, 'High survival +<br>Post-COVID growth decline',    'right', 'bottom'),
    ]:  #shared styling
        fig.add_annotation(x=x, y=y, text=text, showarrow=False,
                           xanchor=xanchor, yanchor=yanchor,
                           font=dict(size=10, color='dimgray'),
                           bgcolor='rgba(255,255,255,0.85)',
                           bordercolor='gainsboro', borderwidth=1, borderpad=6)

    #chart styling
    fig.update_layout(
        xaxis=dict(title=dict(text='Survival Rate (% of pre-2020 businesses still open in 2024)', font=dict(size=11)),
                   tickformat='.0%', range=[x_min - x_pad, x_max + x_pad], **axis),
        yaxis=dict(title=dict(text='Openings/Closings Ratio During Recovery (2022–2024)', font=dict(size=11)),
                   range=[y_min - y_pad, y_max + y_pad], **axis),
        height=420,
        margin=dict(l=20, r=20, t=30, b=20),
        plot_bgcolor='white',
        paper_bgcolor='rgba(0,0,0,0)',
        legend=dict(font=dict(size=9)),
        font=dict(family='-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif'),
    )
    return fig, f'Pre-2020 Business Survival Rate vs. Recovery — {sector} businesses'

#running the app
if __name__ == '__main__':
    app.run(debug=True)
