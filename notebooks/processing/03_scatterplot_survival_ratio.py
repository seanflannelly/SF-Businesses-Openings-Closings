import sys
import pandas as pd
import geopandas as gpd
import plotly.graph_objects as go

sys.path.insert(0, '../../src')
from functions import assign_naics_group, assign_group_from_lic

gdf      = gpd.read_parquet('../../data/processed/ALL_openings_closings_by_neighs_year.parquet')
naics_gdf = gpd.read_parquet('../../data/processed/ALL_openings_closings_by_naics_neighs_year.parquet')
biz      = gpd.read_parquet('../../data/processed/ALL_openings_closings.parquet')

gdf_df   = pd.DataFrame(gdf.drop(columns='geometry'))
naics_df = pd.DataFrame(naics_gdf.drop(columns='geometry'))
biz_df   = pd.DataFrame(biz.drop(columns='geometry'))

sectors = sorted(naics_df['naics_group'].unique().tolist())

totals = gdf_df[gdf_df['year'].between(2020, 2024)].groupby('neighborhood')[['opened', 'closed']].sum()
totals['total'] = totals['opened'] + totals['closed']
active_neighs = set(totals[totals['total'] >= 500].index)

recovery = (
    gdf_df[gdf_df['year'].between(2022, 2024)]
    .groupby('neighborhood')[['opened', 'closed']].sum().reset_index()
)
recovery['recovery_ratio'] = recovery['opened'] / recovery['closed'].replace(0, float('nan'))

biz_df['naics_code'] = biz_df['naics_code'].str.split()
biz_exp = biz_df.explode('naics_code').copy()
biz_exp['naics_group'] = biz_exp['naics_code'].apply(assign_naics_group)
no_code = biz_exp['naics_group'] == 'No Code'
biz_exp.loc[no_code, 'naics_group'] = biz_exp.loc[no_code, 'lic_code'].apply(assign_group_from_lic)


def get_sector_df(sector):
    if sector == 'All':
        rec = recovery[['neighborhood', 'recovery_ratio', 'opened', 'closed']].copy()
        biz = biz_df.drop_duplicates('uniqueid')
    else:
        src = naics_df[(naics_df['naics_group'] == sector) & (naics_df['year'].between(2022, 2024))]
        rec = src.groupby('neighborhood')[['opened', 'closed']].sum().reset_index()
        rec['recovery_ratio'] = rec['opened'] / rec['closed'].replace(0, float('nan'))
        biz = biz_exp[biz_exp['naics_group'] == sector].drop_duplicates('uniqueid')

    # businesses that were actually open when the pandemic hit — started before 2020, not yet closed
    pre2020 = biz[
        (biz['location_start_date'] < '2020-01-01') &
        (biz['location_end_date'].isna() | (biz['location_end_date'] >= '2020-01-01'))
    ].copy()
    pre2020['survived'] = pre2020['location_end_date'].isna() | (pre2020['location_end_date'] >= '2024-01-01')
    surv = (
        pre2020.groupby('neighborhoods_analysis_boundaries')
        .agg(total=('uniqueid', 'count'), survived=('survived', 'sum'))
        .reset_index()
        .rename(columns={'neighborhoods_analysis_boundaries': 'neighborhood'})
    )
    surv['survival_rate'] = surv['survived'] / surv['total']

    merged = rec[['neighborhood', 'recovery_ratio', 'opened', 'closed']].merge(
        surv[['neighborhood', 'survival_rate', 'total']], on='neighborhood'
    ).dropna()
    merged = merged[merged['neighborhood'].isin(active_neighs)]
    return merged[merged['total'] >= 10]


all_sectors = ['All'] + sectors
sector_data = {}
for s in all_sectors:
    sector_data[s] = get_sector_df(s)

fig = go.Figure()
for i, sector in enumerate(all_sectors):
    d = sector_data[sector]
    fig.add_trace(go.Scatter(
        x=d['survival_rate'], y=d['recovery_ratio'],
        mode='markers+text', text=d['neighborhood'],
        textposition='top center',
        customdata=d['total'],
        hovertemplate='<b>%{text}</b><br>Survival rate: %{x:.1%}<br>Recovery vitality: %{y:.2f}<br>Pre-2020 businesses: %{customdata:,}<extra></extra>',
        marker=dict(size=12, color=d['survival_rate'], colorscale='RdBu', showscale=True),
        visible=(i == 0),
        name=sector,
    ))

fig.add_hline(y=1, line_dash='dash')

buttons = []
for i, s in enumerate(all_sectors):
    visible = []
    for j in range(len(all_sectors)):
        visible.append(j == i)
    buttons.append(dict(label=s, method='update',
                        args=[{'visible': visible},
                              {'title': f'Pre-2020 Business Survival Rate vs. Recovery — {s}'}]))
fig.update_layout(
    title='Pre-2020 Business Survival Rate vs. Recovery Vitality (2022-2024) — All Sectors',
    updatemenus=[dict(buttons=buttons, direction='down', x=0.01, xanchor='left', y=1.12, yanchor='top')],
    xaxis=dict(title='Survival Rate (% of pre-2020 businesses still open in 2024)', tickformat='.0%'),
    yaxis_title='Business Vitality During Recovery (2022-2024)',
)
fig.show()

# citywide survival rate per sector computed from raw business data (not neighborhood aggregates)
citywide_rates = {}
for s in all_sectors:
    b = biz_df.drop_duplicates('uniqueid') if s == 'All' else biz_exp[biz_exp['naics_group'] == s].drop_duplicates('uniqueid')
    pre = b[
        (b['location_start_date'] < '2020-01-01') &
        (b['location_end_date'].isna() | (b['location_end_date'] >= '2020-01-01'))
    ]
    survived = pre['location_end_date'].isna() | (pre['location_end_date'] >= '2024-01-01')
    citywide_rates[s] = survived.mean() if len(pre) > 0 else float('nan')

# export survival data for all sectors
rows = []
for s in all_sectors:
    d = sector_data[s].copy()
    d['naics_group'] = s
    d['citywide_rate'] = citywide_rates[s]
    rows.append(d)
survival = pd.concat(rows, ignore_index=True)
survival.to_parquet('../../data/processed/app/survival_by_sector.parquet', index=False)
