# restgdf

improved esri rest io for geopandas


[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD3-yellow.svg)](https://opensource.org/license/bsd-3-clause/)
[![python](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)

[![Publish to PyPI](https://github.com/joshuasundance-swca/restgdf/actions/workflows/publish_on_pypi.yml/badge.svg)](https://github.com/joshuasundance-swca/restgdf/actions/workflows/publish_on_pypi.yml)
![GitHub tag (with filter)](https://img.shields.io/github/v/tag/joshuasundance-swca/restgdf)
[![Read the Docs](https://img.shields.io/readthedocs/restgdf)](https://restgdf.readthedocs.io/en/latest/)

![Code Climate maintainability](https://img.shields.io/codeclimate/maintainability/joshuasundance-swca/restgdf)
![Code Climate issues](https://img.shields.io/codeclimate/issues/joshuasundance-swca/restgdf)
![Code Climate technical debt](https://img.shields.io/codeclimate/tech-debt/joshuasundance-swca/restgdf)
[![coverage](coverage.svg)](./COVERAGE.md)

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v1.json)](https://github.com/charliermarsh/ruff)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)
![Known Vulnerabilities](https://snyk.io/test/github/joshuasundance-swca/restgdf/badge.svg)

`gpd.read_file(url, driver="ESRIJSON")` does not account for max record count limitations

so if you read a service with 100000 features but there's a limit of 1000 records per query, then your gdf will only have 1000 features

these functions use asyncio to read all features from a service, not limited by max record count

keyword arguments to `FeatureLayer.getgdf` are passed on to `requests.Session.post`; include query parameters like where str and token str in data dict

this enables enhanced control over queries and allow use of any valid authentication scheme (eg `requests_ntlm.HttpNtlmAuth`) with use of `requests.Session.auth` or `data={"token": str}`

# Usage

```bash
pip install restgdf
```

```python
import asyncio

from aiohttp import ClientSession

from restgdf import FeatureLayer


beaches_url = r"https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6"

zipcodes_url = "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_ZIP_Codes_2016/FeatureServer/0"

async def main():
    async with ClientSession() as session:
        beaches = await FeatureLayer.from_url(beaches_url, session=session)
        beaches_gdf = await beaches.getgdf()

        daytona = await beaches.where("LOWER(City) LIKE 'daytona%'")
        daytona_gdf = await daytona.getgdf()

        oh_zipcodes = await FeatureLayer.from_url(zipcodes_url, where="STATE = 'OH'", session=session)
        oh_zipcodes_gdf = await oh_zipcodes.getgdf()

    return beaches_gdf, daytona_gdf, oh_zipcodes_gdf


beaches_gdf, daytona_gdf, oh_zipcodes_gdf = asyncio.run(main())

print(beaches_gdf.shape)
# (243, 10)

print(daytona_gdf.shape)
# (83, 10)

print(oh_zipcodes_gdf.shape)
# (1026, 8)
```

# Documentation

https://restgdf.readthedocs.io/

# Uses

- [restgdf_api](https://github.com/joshuasundance-swca/restgdf_api)
- [govgis_nov2023](https://huggingface.co/datasets/joshuasundance/govgis_nov2023)
