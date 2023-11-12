"""A package for getting GeoDataFrames from ArcGIS FeatureLayers."""

from restgdf.featurelayer.featurelayer import FeatureLayer
from restgdf.directory.directory import Directory

__all__ = ["Directory", "FeatureLayer"]


__version__ = "0.8.2"
