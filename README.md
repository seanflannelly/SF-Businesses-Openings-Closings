# SF Business Openings and Closings by Neighborhood

CYPLAN 255 — Urban Informatics and Data Visualization, UC Berkeley

Abigail Lambert, Mia Flynn, Sean Flannelly

---

This project tracks business openings and closings across SF neighborhoods using business registration data from the Treasurer and Tax Collector's Office. We look at how the pandemic reshaped commercial activity across the city and whether those patterns line up with race and income.

## Data

- [SF Open Data — Registered Business Locations](https://data.sfgov.org/Economy-and-Community/Registered-Business-Locations-San-Francisco/g8m3-pdis/about_data)
- U.S. Census Bureau American Community Survey 5-year estimates (neighborhood demographics)

## Repo Structure

```
notebooks/processing/       # cleaning scripts, run 01–07
notebooks/visualizations/   # charts for the site
data/raw/                   # SF geometries
data/processed/             # generated parquets
src/functions.py            # shared utilities
app.py                      # Dash dashboard
index.html                  # site wrapper
css/                        # site styles
assets/                     # Dash assets (custom css, js)
outputs/                    # exported chart htmls
```

## Running Locally

```bash
pip install -r requirements.txt
# optionally run notebooks 01–07 to regenerate processed data
python app.py
# open index.html in a browser
```

## Key Findings

coming soon
