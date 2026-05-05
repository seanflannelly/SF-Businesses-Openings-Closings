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

    # Consumer Services
    'H46': 'Consumer Services', 'H48': 'Consumer Services',
    'H67': 'Consumer Services', 'H68': 'Consumer Services',
    'H69': 'Consumer Services', 'H70': 'Consumer Services',
    'H44': 'Consumer Services', 'H43': 'Consumer Services',
    'C01': 'Consumer Services', 'C02': 'Consumer Services',
    'J01': 'Consumer Services', 'J02': 'Consumer Services',
    'H56': 'Consumer Services', 'H57': 'Consumer Services',
    'HHH': 'Consumer Services', 'P43': 'Consumer Services',
    'P48': 'Consumer Services', 'P51': 'Consumer Services',
    'Q05': 'Consumer Services',

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
    'Professional & Business Services':     ['5100-5199', '5210-5239', '5240-5249', '5300-5399', '5400-5499', '5500-5599', '5600-5699'],
    'Food & Entertainment':                 ['7100-7199', '7200-7299'],
    'Consumer Services':                    ['8100-8139'],
    'Education & Health':                   ['6100-6299'],
    'Manufacturing & Industrial':           ['3100-3399', '4200-4299', '4800-4999'],
    'Utilities & Construction':             ['2200-2299', '2300-2399'],
}

def assign_naics_group(naics_code: str) -> str:
    """Assigns a sector group from a NAICS code string."""
    if not isinstance(naics_code, str):
        return 'No Code'
    for group, codes in NAICS_GROUPS.items():
        if naics_code in codes:
            return group
    return 'No Code'

def assign_group_from_lic(lic_code: str) -> str:
    """
    Assigns a sector group from a lic_code string.
    For multiple codes, picks the sector that appears most frequently.
    """
    if not isinstance(lic_code, str):
        return 'No Code'
    groups = []
    for code in lic_code.strip().split():
        group = LIC_TO_NAICS_GROUP.get(code)
        if group:
            groups.append(group)
    if not groups:
        return 'No Code'
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
    Businesses with neither code are labeled 'No Code' and retained.

    Parameters:
        points: geodataframe with point data
        polygons: geodataframe with polygon geometries
        id_col: column name to use as the polygon identifier (default: "GEOID")

    Returns:
        DataFrame grouped by polygon, sector group, and year
    """
    points = gpd.sjoin(points, polygons, how="left", predicate="within")

    year_col = 'year_open' if 'year_open' in points.columns else 'year'

    points['naics_code'] = points['naics_code'].str.split()
    points = points.explode('naics_code')

    points['naics_group'] = points['naics_code'].apply(assign_naics_group)

    missing_mask = points['naics_group'] == 'No Code'
    points.loc[missing_mask, 'naics_group'] = points.loc[missing_mask, 'lic_code'].apply(assign_group_from_lic)

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

    geom = polygons[[id_col, 'geometry']].drop_duplicates(id_col)
    result = geom.merge(tract_naics_year, on=id_col, how='left').fillna(0)
    
    return gpd.GeoDataFrame(result, geometry='geometry', crs=polygons.crs)
