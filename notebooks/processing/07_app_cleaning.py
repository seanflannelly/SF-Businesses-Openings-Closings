"""
07 - App Cleaning

Loads all processed data (neighborhood openings/closings, NAICS breakdowns, demographics,
resilience metrics, and survival rates) and prepares data for app to data/processed/app/.
"""

import json
import pandas as pd
import geopandas as gpd

# load
neighs_year_gdf  = gpd.read_parquet('data/processed/ALL_openings_closings_by_neighs_year.parquet')
naics_neighs_gdf = gpd.read_parquet('data/processed/ALL_openings_closings_by_naics_neighs_year.parquet')
sf_neigh         = gpd.read_file('data/processed/polygons/sf_neighborhoods.geojson').to_crs(epsg=4326)
demo_df          = pd.read_parquet('data/processed/demographics_by_neighs.parquet')
sf_city_demo     = pd.read_parquet('data/processed/demographics_sf_city.parquet')

# cleaning
neighs_year_df  = pd.DataFrame(neighs_year_gdf.drop(columns='geometry'))
naics_neighs_df = pd.DataFrame(naics_neighs_gdf.drop(columns='geometry'))

neighs_year_df  = neighs_year_df[(neighs_year_df['year'] >= 2019) & (neighs_year_df['year'] <= 2024)]
naics_neighs_df = naics_neighs_df[(naics_neighs_df['year'] >= 2019) & (naics_neighs_df['year'] <= 2024)]

neighs_year_df['open_close_ratio']  = neighs_year_df['opened']  / neighs_year_df['closed'].replace(0, float('nan'))
naics_neighs_df['open_close_ratio'] = naics_neighs_df['opened'] / naics_neighs_df['closed'].replace(0, float('nan'))

demo_df = demo_df[['neighborhood', 'median_income', 'pct_white', 'pct_black',
                    'pct_asian', 'pct_latina_o', 'pct_other']].drop_duplicates('neighborhood')

# filter low activity neighborhoods
totals = (
    neighs_year_df[neighs_year_df['year'].between(2020, 2024)]
    .groupby('neighborhood')[['opened', 'closed']].sum().reset_index()
)
totals['total'] = totals['opened'] + totals['closed']
active_neighs   = set(totals[totals['total'] >= 500]['neighborhood'])

neighs_year_df  = neighs_year_df[neighs_year_df['neighborhood'].isin(active_neighs)]
naics_neighs_df = naics_neighs_df[naics_neighs_df['neighborhood'].isin(active_neighs)]
sf_neigh        = sf_neigh[sf_neigh['neighborhood'].isin(active_neighs)].copy()
sf_neigh['geometry'] = sf_neigh.geometry.simplify(0.0005, preserve_topology=True)

# compute resilience per sector using the same covid/recovery windows as the all-sector version
def resilience_per_sector(df):
    covid = df[df['year'].isin([2020, 2021])].groupby('neighborhood')[['opened', 'closed']].sum()
    covid['covid_ratio'] = covid['opened'] / covid['closed'].replace(0, float('nan'))
    recovery = df[df['year'].isin([2022, 2023, 2024])].groupby('neighborhood')[['opened', 'closed']].sum()
    recovery['recovery_ratio'] = recovery['opened'] / recovery['closed'].replace(0, float('nan'))
    return (covid[['covid_ratio']]
            .join(recovery[['recovery_ratio']], how='inner')
            .dropna()
            .reset_index())

sectors = []
for sector, grp in naics_neighs_df.groupby('naics_group'):
    part = resilience_per_sector(grp)
    part['naics_group'] = sector
    sectors.append(part)
resilience_by_sector_df = pd.concat(sectors, ignore_index=True)

# precompute per-sector axis bounds for the resilience scatter chart
survival_df = pd.read_parquet('data/processed/app/survival_by_sector.parquet')
rows = []
for sector, grp in survival_df.groupby('naics_group'):
    x_min, x_max = grp['survival_rate'].min(), grp['survival_rate'].max()
    y_min, y_max = grp['recovery_ratio'].min(), grp['recovery_ratio'].max()
    x_pad = (x_max - x_min) * 0.08
    y_pad = (y_max - y_min) * 0.08
    rows.append(dict(
        naics_group=sector,
        x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max,
        x_pad=x_pad, y_pad=y_pad,
        x_mean=grp['survival_rate'].mean(),
        citywide_rate=grp['citywide_rate'].iloc[0],
    ))
survival_stats_df = pd.DataFrame(rows)

# export
neighs_year_df.to_parquet('data/processed/app/neighs_year.parquet', index=False)
naics_neighs_df.to_parquet('data/processed/app/naics_neighs.parquet', index=False)
demo_df.to_parquet('data/processed/app/demographics.parquet', index=False)
sf_city_demo.to_parquet('data/processed/app/demographics_city.parquet', index=False)
resilience_by_sector_df.to_parquet('data/processed/app/resilience_by_sector.parquet', index=False)
survival_stats_df.to_parquet('data/processed/app/survival_stats.parquet', index=False)
sf_neigh.to_file('data/processed/app/neighborhoods.geojson', driver='GeoJSON')

print('done')