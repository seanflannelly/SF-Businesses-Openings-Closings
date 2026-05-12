# San Francisco Business Openings and Closings by Neighborhood

CYPLAN 255: Urban Informatics and Data Visualization, UC Berkeley (Spring 2026)

Abigail Lambert, Mia Flynn, Sean Flannelly

---

This project tracks business openings and closings across SF neighborhoods using business registration data from the Treasurer and Tax Collector's Office. We examine how the COVID-19 pandemic reshaped commercial activity across the city, including how this relates to demographic variability and business sector within each neighborhood.

## Data

- [SF Open Data — Registered Business Locations](https://data.sfgov.org/Economy-and-Community/Registered-Business-Locations-San-Francisco/g8m3-pdis/about_data)
- U.S. Census Bureau American Community Survey 5-year estimates (2019-2023; neighborhood demographics)
- Map of 2020 Census Tracts Assigned to Analysis Neighborhoods (https://data.sfgov.org/Geographic-Locations-and-Boundaries/Map-of-2020-Census-Tracts-Assigned-to-Analysis-Nei/rqw6-h7c5)
- San Francisco Analysis Neighborhoods (https://data.sfgov.org/-/Analysis-Neighborhoods/p5b7-5n3h)

## Repo Structure

```
notebooks/processing/       # cleaning scripts, run 01–08
notebooks/visualizations/   # charts for the site, run 01-04 to regenerate
data/raw/                   # SF geometries
data/processed/             # generated parquets
src/functions.py            # shared utilities
app.py                      # Dash dashboard
index.html                  # site wrapper
css/                        # site styles
assets/                     # Dash assets (custom css, js)
outputs/                    # exported chart htmls
img/                        # screenshots of app for demonstration
```

## Running Locally

```bash
pip install -r requirements.txt
# optionally run notebooks 01–07 to regenerate processed data
python app.py
# open index.html in a browser
```
