"""Sphinx configuration for restgdf.

See https://www.sphinx-doc.org/en/master/usage/configuration.html for the full
list of options.
"""

from __future__ import annotations

import datetime
import os
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

# Make the package importable for autodoc without requiring it to be installed.
sys.path.insert(0, os.path.abspath(".."))

# -- Project information -----------------------------------------------------

project = "restgdf"
author = "Joshua Sundance Bailey"
copyright = f"2023-{datetime.date.today().year}, {author}"  # noqa: A001

try:
    release = _pkg_version("restgdf")
except PackageNotFoundError:  # pragma: no cover - only in uninstalled dev checkouts
    release = "0.0.0+unknown"
version = ".".join(release.split(".")[:2])

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinxcontrib.autodoc_pydantic",
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx_llm.txt",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Accept both .rst and .md sources (myst_parser handles .md).
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# Turn on nitpicky mode so undefined cross-references become warnings. Pair
# with ``nitpick_ignore`` for known-safe misses.
nitpicky = True

# Private bases (re-exported or used as type bounds) that we deliberately
# don't expose publicly. Ignore their undefined xrefs.
nitpick_ignore = [
    ("py:class", "restgdf._models._drift.PermissiveModel"),
    ("py:class", "restgdf._models._drift.StrictModel"),
    ("py:class", "pydantic.main.BaseModel"),
    ("py:class", "pydantic.networks.HttpUrl"),
    # aiohttp / yarl / multidict have no intersphinx inventory of stable URLs
    # for every class we reference; ignore missing targets rather than spam.
    ("py:class", "yarl.URL"),
    ("py:class", "yarl._url.URL"),
    ("py:class", "multidict._multidict.CIMultiDictProxy"),
    ("py:class", "aiohttp.client.ClientSession"),
    # Self-referential pydantic generics can confuse the resolver.
    ("py:class", "restgdf._models.responses.LayerMetadata"),
    # Private auth-subtype mixin – deliberately not public.
    ("py:class", "restgdf.errors._AuthSubtypeBase"),
    # Union syntax ``int | None`` in numpydoc attribute section.
    ("py:class", "int | None"),
]

nitpick_ignore_regex = [
    # Silence ``Callable[...]``/``Mapping[...]`` partial-parse warnings.
    (r"py:class", r"^typing\..*"),
    (r"py:class", r"^collections\.abc\..*"),
    # autodoc-pydantic's auto-generated field summary links resolve to
    # ``py:obj``/``py:attr`` targets that aren't registered (fields render as
    # pydantic-specific directives). Harmless noise.
    (r"py:(obj|attr|func|class|meth|mod)", r"restgdf\._models\..*"),
    (
        r"py:(attr|class|func)",
        r"^(Crawl|Count|Layer|ObjectIds|Features|Token|Error|Service|Field|Feature|Settings)[A-Za-z]*(\.[A-Za-z_]+)?$",
    ),
    (r"py:func", r"^(safe_crawl|reset_settings_cache|_parse_response|__post_init__)$"),
    (r"py:meth", r"^__post_init__$"),
    # aiohttp/asyncio internals aren't in the aiohttp intersphinx inventory.
    (r"py:class", r"^aiohttp\..*"),
    (r"py:class", r"^asyncio\..*"),
    (r"py:class", r"^multidict\..*"),
    (r"py:class", r"^SecretStr$"),
    # Docstring literal ``Optional[...]`` / ``tuple[str, ...]`` slices are
    # parsed as malformed class references by Sphinx.
    (r"py:class", r"^(Optional|Union|List|Dict|Tuple|tuple|list|dict)\[.*"),
    (r"py:class", r"^\.\.\]$"),
]

# autodoc-pydantic re-renders nested models (e.g. TokenSessionConfig nests
# AGOLUserPass), which collides with our standalone autopydantic_model
# directives. ``ref.obj``/``ref.attr`` warnings are also dominated by the
# auto-generated field summary (see ``nitpick_ignore_regex`` above).
suppress_warnings = [
    "autosectionlabel.*",
    # CHANGELOG.md and MIGRATION.md are included from the repo root via MyST
    # ``{include}`` directives. Their relative links (e.g. ``./MIGRATION.md``)
    # target the GitHub rendering; when included into the docs they become
    # dangling xrefs. Silence just those rather than rewriting repo-level docs.
    "myst.xref_missing",
]

# -- Autodoc / napoleon / autodoc-pydantic -----------------------------------

autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"
autodoc_member_order = "bysource"
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}

# Clean up rendered signatures for common aliases.
autodoc_type_aliases = {
    "Mapping[str, Any]": "Mapping",
    "DataFrame": "pandas.DataFrame",
    "GeoDataFrame": "geopandas.GeoDataFrame",
}

napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_use_param = False
napoleon_use_ivar = True
napoleon_preprocess_types = True

# https://autodoc-pydantic.readthedocs.io/en/stable/users/configuration.html
autodoc_pydantic_model_show_json = False
autodoc_pydantic_model_show_config_summary = False
autodoc_pydantic_model_show_validator_summary = True
autodoc_pydantic_model_show_validator_members = False
autodoc_pydantic_model_show_field_summary = True
autodoc_pydantic_model_member_order = "bysource"
autodoc_pydantic_model_undoc_members = True
autodoc_pydantic_field_list_validators = False
autodoc_pydantic_field_show_alias = True
autodoc_pydantic_field_show_constraints = True
autodoc_pydantic_field_show_default = True
autodoc_pydantic_settings_show_json = False
autodoc_pydantic_settings_show_config_summary = False

# -- Intersphinx -------------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
    "geopandas": ("https://geopandas.org/en/stable/", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
    "aiohttp": ("https://docs.aiohttp.org/en/stable/", None),
    "requests": ("https://requests.readthedocs.io/en/latest/", None),
}

# -- MyST --------------------------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "linkify",
    "smartquotes",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3
myst_url_schemes = ("http", "https", "mailto", "ftp")

# -- HTML output -------------------------------------------------------------

html_theme = "furo"
html_title = f"restgdf {release}"
html_static_path = ["_static"] if os.path.isdir("_static") else []

html_theme_options = {
    "source_repository": "https://github.com/joshuasundance-swca/restgdf/",
    "source_branch": "main",
    "source_directory": "docs/",
    "navigation_with_keys": True,
    "top_of_page_buttons": ["view", "edit"],
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/joshuasundance-swca/restgdf",
            "html": "",
            "class": "fa-brands fa-solid fa-github fa-2x",
        },
    ],
}

# -- Copybutton --------------------------------------------------------------

copybutton_prompt_text = r">>> |\.\.\. |\$ |In \[\d*\]: | {2,5}\.\.\.: | {5,8}: "
copybutton_prompt_is_regexp = True
copybutton_only_copy_prompt_lines = True
copybutton_remove_prompts = True

# -- sphinx-llm --------------------------------------------------------------

# Generate llms.txt / llms-full.txt alongside HTML for LLM consumption
# (https://llmstxt.org/). Can be disabled per-build via -D llms_txt_enabled=0.
llms_txt_description = (
    "lightweight async Esri REST client with optional GeoPandas extras"
)
