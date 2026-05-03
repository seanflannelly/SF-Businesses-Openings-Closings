# region imports
import pandas as pd
import geopandas as gpd
import numpy as np
import os
import matplotlib.pyplot as plt
from shapely.geometry import LineString
import plotly.express as px
import functions
import gdown
import geopandas as gpd
# endregion


# region read RBL all dates with GEOID
# Download the parquet file locally first

local_path1 = "/Users/Sean1/Documents/GitHub/CYPLAN255-Final-Project/data/rbl_GEOID_all_dates.parquet"
local_path2 = "/Users/Sean1/Documents/GitHub/CYPLAN255-Final-Project/data/sf_tracts.parquet"

# file_id1 = "1XCrIeUc8LLfVrjt7faxnFj5FcJwPy9Un"
# file_id2 = "1v03cWWfZQYLxzYfq70W9pNW6Ada_fSTc"
#gdown.download(f"https://drive.google.com/uc?id={file_id1}", local_path1, quiet=False)
#gdown.download(f"https://drive.google.com/uc?id={file_id2}", local_path2, quiet=False)

gdf = gpd.read_parquet(local_path1)
sf_tracts = gpd.read_parquet(local_path2)
# endregion



# =============================================================================
# Changing to pd.datetime
# =============================================================================
gdf['location_end_date'] = pd.to_datetime(gdf['location_end_date'])
gdf['location_start_date'] = pd.to_datetime(gdf['location_start_date'])
gdf['open_month_year'] = gdf['location_start_date'].dt.strftime('%B %Y')
gdf['close_month_year'] = gdf['location_end_date'].dt.strftime('%B %Y')


# =============================================================================
# Sorting by pre-covid openings
# =============================================================================
pre_covid_mask = gdf['location_start_date'] < '2020-03-01'
pre_covid_tracts = gdf[pre_covid_mask]

survival_mask = (gdf['location_start_date'].dt.year < 2020) & gdf['location_end_date'].isna()
survival_tracts = gdf[survival_mask].sort_values('location_start_date')

# =============================================================================
# grouping by tract
# =============================================================================

pre_covid_tracts_grouped = functions.group_points_by_tract(
    points=pre_covid_tracts,
    tracts=sf_tracts
)

survival_tracts_grouped = functions.group_points_by_tract(
    points=survival_tracts,
    tracts=sf_tracts
)

# =============================================================================
# calculating survival rate
# =============================================================================

# adding closed businesses and opened businesses that have not closed 
# (because closed businesses also are listed in opened, just in a diff year)
survival_tracts_grouped['total'] = pre_covid_tracts_grouped['closed'] + survival_tracts_grouped['opened']
survival_tracts_grouped['survival_rate'] = survival_tracts_grouped['opened'] / survival_tracts_grouped['total']

# =============================================================================
# exporting survival rate gdf
# =============================================================================

# survival_tracts_grouped.to_parquet('/Users/Sean1/Documents/GitHub/CYPLAN255-Final-Project/data/survival_rates_GEOID.parquet')

# =============================================================================
# mapping
# =============================================================================

import plotly.graph_objects as go

fig = px.choropleth_mapbox(
    survival_tracts_grouped,
    geojson=survival_tracts_grouped.set_index("GEOID").__geo_interface__,
    locations="GEOID",
    color="survival_rate",
    hover_name="GEOID",
    center={"lat": 37.7749, "lon": -122.4194},
    zoom=10,
    mapbox_style="carto-positron",
    color_continuous_scale="Reds",
    height=500,
    width=700

)


fig.show()



