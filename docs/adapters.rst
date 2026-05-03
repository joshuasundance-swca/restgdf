Output adapters
===============

The ``restgdf.adapters`` subpackage composes streaming primitives into
tabular output shapes. Each adapter works against the async iterators
exposed by :class:`~restgdf.FeatureLayer` and avoids importing heavy
dependencies (pandas, geopandas) at module load time — they are guarded
behind runtime checks and raise :class:`~restgdf.errors.OptionalDependencyError`
with an install hint when missing.

restgdf.adapters.dict
---------------------

Pure-Python row conversion. Part of the base ``pip install restgdf`` install.

.. automodule:: restgdf.adapters.dict
   :members:
   :show-inheritance:

restgdf.adapters.stream
-----------------------

Async iterator helpers that compose pagination into per-row or per-batch shapes.
Part of the base install.

.. automodule:: restgdf.adapters.stream
   :members:
   :show-inheritance:

restgdf.adapters.pandas
-----------------------

DataFrame materialization. Requires ``pandas`` (installed via ``restgdf[geo]``
or standalone).

.. automodule:: restgdf.adapters.pandas
   :members:
   :show-inheritance:

restgdf.adapters.geopandas
---------------------------

GeoDataFrame materialization. Requires ``restgdf[geo]`` (geopandas + pyogrio).

.. automodule:: restgdf.adapters.geopandas
   :members:
   :show-inheritance:
