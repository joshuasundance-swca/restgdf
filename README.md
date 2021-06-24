# restgdf: improved esri rest io for geopandas

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
![](coverage.svg)

```gpd.read_file(url, driver="ESRIJSON")``` does not account for max record count limitations

so if you read a service with 100000 features but there's a limit of 1000 records per query, then your gdf will only have 1000 features

these functions use a generator to read all features from a service, not limited by max record count

keyword arguments to ```restgdf.getgdf``` are passed on to ```requests.Session.post```; include query parameters like where str and token str in data dict

this enables enhanced control over queries and allow use of any valid authentication scheme with use of ```requests.Session.auth``` or ```data={"token": str}```

* ```conda create -n restgdf requests geopandas```
* ```git clone https://github.com/joshuasundance-swca/restgdf```
* ```pip install .```

```
from restgdf import getgdf

# anonymous access
gdf = getgdf(url)

# s.auth with limiting query
with Session() as s:
    s.auth = requests_ntlm.HttpNtlmAuth("domain\\username", "password")
    gdf = getgdf(url, s, data={"where": query})

# token auth
with Session() as s:
    gdf = getgdf(url, s, data={"token": tkn})

# the use of a Session object is optional but will enhance performance

# or use the Rest class
beaches = Rest(r'https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6')
beaches.fields
beaches.getuniquevalues('City')
beaches.getgdf()
daytona = beaches.where("LOWER(City) LIKE 'daytona%'")

# more documentation to come...
```

[ArcGIS REST API reference](https://developers.arcgis.com/rest/)
