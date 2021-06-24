from setuptools import setup


def get_long_description():
    with open("README.md", encoding="utf-8") as f:
        return f.read()


setup(
    name="restgdf",
    version="0.2",
    description="improved esri rest io for geopandas",
    long_description="provides getgdf function and Rest class for gdf from rest io",
    url="https://github.com/joshuasundance/restgdf",
    author="Joshua Sundance Bailey",
    author_email="36394687+joshuasundance@users.noreply.github.com",
    license="BSD",
    packages=["restgdf"],
    zip_safe=False,
    install_requires=["requests", "pandas", "fiona", "geopandas"],
)
