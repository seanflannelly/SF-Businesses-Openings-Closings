import pandas as pd
import numpy as np
import geopandas as gpd
import plotly.graph_objects as go
import plotly.express as px
import matplotlib.pyplot as plt


def group_points_by_poly_year(
    points: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    id_col: str = "GEOID",
):
    """
    Groups all the business location points by polygon ID, year and status (open or closed).
    
    Parameters:
        points: geodataframe with point data
        polygons: geodataframe with polygon geometries
        id_col: column name to use as the polygon identifier (default: "GEOID")
        naics_filter: optional string label for the NAICS filter applied
    
    Returns:
        GeoDataFrame
    """
    points = gpd.sjoin(points, polygons, how="left", predicate="within")

    year_col = 'year_open' if 'year_open' in points.columns else 'year'

    tract_year = (
        points
        .groupby([id_col, year_col, "status"])
        .size()
        .reset_index(name="count")
        .pivot(index=[id_col, year_col], columns="status", values="count")
        .fillna(0)
        .reset_index()
        .sort_values(year_col)
    )

    tracts_plot = polygons[[id_col, "geometry"]].merge(
        tract_year,
        on=id_col,
        how="left"
    ).fillna(0)

    return tracts_plot


def group_points_by_poly(
    points: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    id_col: str = "GEOID"
):
    points = gpd.sjoin(points, polygons, how="left", predicate="within")

    tract_grouped = (
        points
        .groupby([id_col, "status"])
        .size()
        .reset_index(name="count")
        .pivot(index=[id_col], columns="status", values="count")
        .fillna(0)
        .reset_index()
    )

    biz_stock = (
        points
        .groupby(id_col)['uniqueid']
        .nunique()
        .reset_index(name='biz_stock')
    )

    tracts_plot = polygons[[id_col, "geometry"]].merge(tract_grouped, on=id_col, how="left").fillna(0)
    tracts_plot = tracts_plot.merge(biz_stock, on=id_col, how="left")

    return tracts_plot

def clip_to_2016(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    year_col = 'year_open' if 'year_open' in gdf.columns else 'year'
    return gdf[(gdf[year_col] >= 2016) & (gdf[year_col] <= 2025)]

def filter_by_naics_name(gdf: gpd.GeoDataFrame, naics_name:str):
  """
    filters a GeoDataFrame by an naics code string

    Returns: GeoDataFrame filtered
  """
  naics_dict = {
    
    #all
    

    'Information': '5100-5199',
    'Financial Services': '5210-5239',
    'Accommodations': '7210-7219',
    'Retail Trade': '4400-4599',
    'Construction': '2300-2399',
    'Food Services': '7220-7229',
    'Manufacturing': '3100-3399',
    'Real Estate and Rental and Leasing Services': '5300-5399',
    'Arts, Entertainment, and Recreation': '7100-7199',
    'Private Education and Health Services': '6100-6299',
    'Administrative and Support Services': '5600-5699',
    'Professional, Scientific, and Technical Services': '5400-5499',
    'Certain Services': '8100-8139',
    'Wholesale Trade': '4200-4299',
    'Transportation and Warehousing': '4800-4999',
    'Insurance': '5240-5249',
    'Utilities': '2200-2299',

    #special categories
    'Retail, Food and Arts/Entertainment':'7220-7229|4400-4599|7100-7199'  
  }

  naics=naics_dict[naics_name]
  gdf = gdf[gdf['naics_code'].str.contains(naics, na=False)]

  return gdf
  
#---------------------

def calc_business_dynamics(open_close_gdf: gpd.GeoDataFrame, biz_gdf: gpd.GeoDataFrame, poly_gdf: gpd.GeoDataFrame, id_col: str = 'GEO_ID', naics_name: str = None) -> gpd.GeoDataFrame:
    """
    Groups by tract and year and calculates business dynamics metrics for each tract and year.
    Takes an optional naics_name variable to filter by naics code

    Parameters:
        open_close_gdf: GeoDataFrame with raw business point data (openings and closings)
        biz_gdf: GeoDataFrame with individual business records
        poly_gdf: GeoDataFrame with tract/block group geometries and id_col (usually GEO_ID)
        naics_name: optional NAICS name string to filter by (supports | for multiple codes)
    
    Returns:
        GeoDataFrame with net_change, growth_pct_over_2016, biz_stock, net_entry_rate, gross_exit_rate
    """
    open_close = open_close_gdf.copy()
    biz = biz_gdf.copy()

    # filter to naics if provided
    if naics_name and naics_name != 'all':
        open_close = filter_by_naics_name(open_close, naics_name)
        biz = filter_by_naics_name(biz, naics_name)

    # group points to tracts
    gdf = group_points_by_poly_year(open_close, poly_gdf, id_col=id_col, naics_filter=naics_name)

    ## net change (openings-closings)
    gdf['net_change'] = gdf['opened'] - gdf['closed']

    # get 2016 baseline of net change for each geometry
    baseline = gdf[gdf['year'] == 2016][[id_col, 'net_change']].rename(columns={'net_change': 'baseline_2016'})

    # merge baseline into gdf of openings closings and tracts
    gdf = gdf.merge(baseline, on=id_col)

    # calculating percent chg in growth from baseline of 2016
    gdf['growth_pct_over_2016'] = (gdf['net_change'] / gdf['baseline_2016']) * 100

    ## getting total number of businesses active in each year

    # first filling year_closed with 2025 in order to include active businesses in the range
    biz['year_closed'] = biz['year_closed'].fillna(2025).astype(int)
    biz['year_open'] = biz['year_open'].astype(int)

    # creating an active_years list for each business, which includes an integer of each year it was active at all
    biz['active_years'] = biz.apply(
        lambda row: list(range(row['year_open'], row['year_closed'] + 1)), axis=1
    )

    # explode takes a column of lists and creates a row for each item in the column, but still indexed by the same other info/columns
    # so here, it's creating a row for each active year of the business
    biz_exploded = biz.explode('active_years').rename(columns={'active_years': 'year'})

    # joining this exploded gdf with tract/grp GEOID of its location
    biz_exploded = gpd.sjoin(biz_exploded, poly_gdf[[id_col, 'geometry']], how='left', predicate='within')

    # grouping by geoid and year and counting the number of businesses in each year
    biz_stock = biz_exploded.groupby([id_col, 'year']).size().reset_index(name='biz_stock')

    # joining that grouped df into gdf, which is already grouped by geoid and year
    # joining on the left, which means biz_stock rows for years not included in open_close will not be carried over
    gdf = gdf.merge(biz_stock, on=[id_col, 'year'], how='left')

    # calculating net entry rate for each tract/grp and year
    gdf['net_entry_rate'] = (gdf['net_change'] / gdf['biz_stock']) * 100

    # gross exit rate, to help show how much turnover there was in relation to the net entry
    gdf['gross_exit_rate'] = (gdf['opened'] / gdf['biz_stock']) * 100

    # total activity
    gdf['total_activity'] = gdf['opened'] + gdf['closed']

    return gdf

def choropleth_animated(gdf: gpd.GeoDataFrame, color_col: str, epc_tracts: gpd.GeoDataFrame, start_year: int = 2016) -> go.Figure:
    """
    Creates an animated choropleth map with EPC tract outlines.
    
    Parameters:
        gdf: GeoDataFrame with tract data
        color_col: column to use for choropleth color
        epc_tracts: GeoDataFrame with EPC tract geometries
        start_year: year to start animation from (default 2016)
    
    Returns:
        Plotly figure
    """
    plot_gdf = gdf[gdf['year'] >= start_year].copy()
    plot_gdf['is_epc'] = plot_gdf['GEOID'].isin(epc_tracts['GEOID'])

    vabs = plot_gdf[color_col].abs().quantile(0.99)

    fig = px.choropleth_mapbox(
        plot_gdf,
        geojson=plot_gdf.set_index("GEOID").__geo_interface__,
        locations="GEOID",
        color=color_col,
        hover_name="GEOID",
        hover_data={'is_epc': True, 'opened': True, 'closed': True, 'gross_exit_rate': True, 'biz_stock': True},
        animation_frame="year",
        mapbox_style="carto-positron",
        zoom=10,
        center={"lat": 37.7749, "lon": -122.4194},
        color_continuous_scale="RdBu",
        color_continuous_midpoint=0,
        range_color=[-vabs, vabs],
        height=600,
        width=700
    )

    epc_outline = plot_gdf[plot_gdf['is_epc']]
    fig.add_trace(go.Choroplethmapbox(
        geojson=epc_outline.set_index("GEOID").__geo_interface__,
        locations=epc_outline["GEOID"],
        z=[1] * len(epc_outline),
        colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
        marker_line_color='black',
        marker_line_width=3,
        showscale=False,
        hoverinfo='skip',
        name='EPC Tracts'
    ))

    fig.update_layout(title=f'{color_col} — {plot_gdf["naics_filter"].iloc[0]}')

    return fig



#big crosswalk dictionary for businesses that have a business license code but no naics code. built using license code descriptions from the data
# broader categories are built using the NAICS-code supergroupings used by Meltzer (2016)
# dictionary created using ai assistance
LIC_TO_NAICS_GROUP = {
    # Retail
    'H03': 'Retail', 'H07': 'Retail', 'H31': 'Retail', 'H61': 'Retail',
    'H14': 'Retail', 'H05': 'Retail', 'WM08': 'Retail', 'WM18': 'Retail',
    'WM19': 'Retail', 'WM21': 'Retail', 'WM26': 'Retail', 'WM30': 'Retail',
    'WM03': 'Retail', 'POS01': 'Retail',

    # Food & Entertainment
    'H24': 'Food & Entertainment', 'H25': 'Food & Entertainment',
    'H26': 'Food & Entertainment', 'H28': 'Food & Entertainment',
    'H33': 'Food & Entertainment', 'H34': 'Food & Entertainment',
    'H36': 'Food & Entertainment', 'H74': 'Food & Entertainment',
    'H75': 'Food & Entertainment', 'H76': 'Food & Entertainment',
    'H78': 'Food & Entertainment', 'H79': 'Food & Entertainment',
    'H84': 'Food & Entertainment', 'H85': 'Food & Entertainment',
    'H86': 'Food & Entertainment', 'H87': 'Food & Entertainment',
    'H88': 'Food & Entertainment', 'H90': 'Food & Entertainment',
    'H91': 'Food & Entertainment', 'H98': 'Food & Entertainment',
    'H99': 'Food & Entertainment', 'H23': 'Food & Entertainment',
    'J07': 'Food & Entertainment', 'J11': 'Food & Entertainment',
    'J12': 'Food & Entertainment', 'J04': 'Food & Entertainment',
    'P12': 'Food & Entertainment', 'P22': 'Food & Entertainment',
    'P23': 'Food & Entertainment', 'P54': 'Food & Entertainment',
    'P21': 'Food & Entertainment', 'A45': 'Food & Entertainment',
    'SSFCP': 'Food & Entertainment', 'RSSFCP': 'Food & Entertainment',
    'RSSPP': 'Food & Entertainment', 'CCFP': 'Food & Entertainment',

    # Personal Services
    'H46': 'Personal Services', 'H48': 'Personal Services',
    'H67': 'Personal Services', 'H68': 'Personal Services',
    'H69': 'Personal Services', 'H70': 'Personal Services',
    'H44': 'Personal Services', 'H43': 'Personal Services',
    'C01': 'Personal Services', 'C02': 'Personal Services',
    'J01': 'Personal Services', 'J02': 'Personal Services',
    'H56': 'Personal Services', 'H57': 'Personal Services',
    'HHH': 'Personal Services', 'P43': 'Personal Services',
    'P48': 'Personal Services', 'P51': 'Personal Services',
    'Q05': 'Personal Services',

    # Manufacturing & Industrial
    'D23': 'Manufacturing & Industrial', 'D24': 'Manufacturing & Industrial',
    'D30': 'Manufacturing & Industrial', 'D32': 'Manufacturing & Industrial',
    'D39': 'Manufacturing & Industrial', 'D20': 'Manufacturing & Industrial',
    'WM28': 'Manufacturing & Industrial', 'H64': 'Manufacturing & Industrial',
    'H65': 'Manufacturing & Industrial',

    # Utilities & Construction
    'D19': 'Utilities & Construction', 'D26': 'Utilities & Construction',
    'D27': 'Utilities & Construction', 'D28': 'Utilities & Construction',
    'D29': 'Utilities & Construction', 'D31': 'Utilities & Construction',
    'D03': 'Utilities & Construction', 'D04': 'Utilities & Construction',
    'D02': 'Utilities & Construction', 'D08': 'Utilities & Construction',
    'D10': 'Utilities & Construction', 'D13': 'Utilities & Construction',
    'D14': 'Utilities & Construction', 'D25': 'Utilities & Construction',
    'D33': 'Utilities & Construction', 'D36': 'Utilities & Construction',
    'D46': 'Utilities & Construction', 'D47': 'Utilities & Construction',
    'D51': 'Utilities & Construction', 'WM15': 'Utilities & Construction',
    'WM33': 'Utilities & Construction', 'CENF': 'Utilities & Construction',
    'CPAF': 'Utilities & Construction', 'CRP': 'Utilities & Construction',
    'H58': 'Utilities & Construction', 'H59': 'Utilities & Construction',
    'H60': 'Utilities & Construction', 'H96': 'Utilities & Construction',
    'H97': 'Utilities & Construction', 'H100': 'Utilities & Construction',
    'H101': 'Utilities & Construction', 'H102': 'Utilities & Construction',
}

NAICS_GROUPS = {
    'Retail':                               ['4400-4599', '4500-4599'],
    'Service':                              ['5100-5199', '5210-5239', '5240-5249', '5300-5399', '5400-5499', '5500-5599', '5600-5699'],
    'Food & Entertainment':                 ['7100-7199', '7200-7299'],
    'Personal Services':                    ['8100-8139'],
    'Education & Health':                   ['6100-6299'],
    'Manufacturing & Industrial':           ['3100-3399', '4200-4299', '4800-4999'],
    'Utilities & Construction':             ['2200-2299', '2300-2399'],
}

def assign_naics_group(naics_code: str) -> str:
    """Assigns a supergroup from naics codes"""
    if not isinstance(naics_code, str):
        return None
    for group, codes in NAICS_GROUPS.items():
        if naics_code in codes:
            return group
    return None

def assign_group_from_lic(lic_code: str) -> str:
    """
    Assigns a supergroup from lic_code.
    For multiple codes, if license can apply twice to same category, it only returns once
    """
    if not isinstance(lic_code, str):
        return 'Other'
    groups = []
    for code in lic_code.strip().split():
        group = LIC_TO_NAICS_GROUP.get(code)
        if group:
            groups.append(group)
    if not groups:
        return 'Other'
    return max(set(groups), key=groups.count)

def group_points_by_poly_naics_year(
    points: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    id_col: str = "GEOID",
):
    """
    Groups business location points by polygon ID, sector group, and year.
    Sector groups follow Meltzer (2016) NAICS groupings.
    Businesses with multiple NAICS codes are exploded so each code gets its own row.
    Businesses missing NAICS codes are classified via lic_code using a majority vote crosswalk.

    Parameters:
        points: geodataframe with point data
        polygons: geodataframe with polygon geometries
        id_col: column name to use as the polygon identifier (default: "GEOID")

    Returns:
        GeoDataFrame grouped by polygon, sector group, and year
    """
    points = gpd.sjoin(points, polygons, how="left", predicate="within")

    year_col = 'year_open' if 'year_open' in points.columns else 'year'

    points['naics_code'] = points['naics_code'].str.split()
    points = points.explode('naics_code')

    points['naics_group'] = points['naics_code'].apply(assign_naics_group)

    missing_mask = points['naics_group'].isna()
    points.loc[missing_mask, 'naics_group'] = points.loc[missing_mask, 'lic_code'].apply(assign_group_from_lic)

    points = points[points['naics_group'] != 'Other'].copy()

    tract_naics_year = (
        points
        .groupby([id_col, 'naics_group', year_col, 'status'])
        .size()
        .reset_index(name='count')
        .pivot(index=[id_col, 'naics_group', year_col], columns='status', values='count')
        .fillna(0)
        .reset_index()
        .sort_values(year_col)
    )

    geom = polygons[[id_col]].drop_duplicates(id_col)
    result = geom.merge(tract_naics_year, on=id_col, how='left').fillna(0)

    return result
