import json
import pandas as pd
import geopandas as gpd

# load
neighs_year_gdf  = gpd.read_parquet('data/processed/ALL_openings_closings_by_neighs_year.parquet')
naics_neighs_gdf = gpd.read_parquet('data/processed/ALL_openings_closings_by_naics_neighs_year.parquet')
sf_neigh         = gpd.read_file('data/processed/polygons/sf_neighborhoods.geojson').to_crs(epsg=4326)
demo_df          = pd.read_parquet('data/processed/demographics_by_neighs.parquet')
sf_city_demo     = pd.read_parquet('data/processed/demographics_sf_city.parquet')
resilience_df    = pd.read_parquet('data/processed/pandemic_resilience.parquet')

# cleaning
neighs_year_df  = pd.DataFrame(neighs_year_gdf.drop(columns='geometry'))
naics_neighs_df = pd.DataFrame(naics_neighs_gdf.drop(columns='geometry'))

neighs_year_df  = neighs_year_df[neighs_year_df['year'] >= 2019]
naics_neighs_df = naics_neighs_df[naics_neighs_df['year'] >= 2019]

neighs_year_df['open_close_ratio'] = neighs_year_df['opened'] / neighs_year_df['closed'].replace(0, float('nan'))

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

# export
neighs_year_df.to_parquet('data/processed/app/neighs_year.parquet', index=False)
naics_neighs_df.to_parquet('data/processed/app/naics_neighs.parquet', index=False)
demo_df.to_parquet('data/processed/app/demographics.parquet', index=False)
sf_city_demo.to_parquet('data/processed/app/demographics_city.parquet', index=False)
resilience_df.to_parquet('data/processed/app/resilience.parquet', index=False)
resilience_by_sector_df.to_parquet('data/processed/app/resilience_by_sector.parquet', index=False)
sf_neigh.to_file('data/processed/app/neighborhoods.geojson', driver='GeoJSON')

print('done')