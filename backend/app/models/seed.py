"""Reference data. Imported by the initial migration and by the test suite, so both agree."""

from __future__ import annotations

LOCATIONS: list[dict] = [
    {
        "country": "India",
        "iso_code": "IN",
        "states": [
            {"name": "Karnataka", "cities": [{"name": "Bengaluru", "aliases": ["Bangalore"]}]},
            {"name": "Maharashtra", "cities": [{"name": "Mumbai", "aliases": ["Bombay"]}]},
            {"name": "Delhi", "cities": [{"name": "New Delhi", "aliases": ["Delhi"]}]},
        ],
    }
]

# Every category maps to a native type on both providers. Grocery vs. convenience is fuzzy
# in Indian OSM data, where many kirana stores are tagged shop=convenience.
CATEGORIES: list[dict] = [
    {
        "slug": "supermarket",
        "name": "Supermarket",
        "google": ["supermarket"],
        "overpass": ["shop=supermarket"],
    },
    {
        "slug": "grocery_store",
        "name": "Grocery Store",
        "google": ["grocery_store"],
        "overpass": ["shop=grocery", "shop=greengrocer"],
    },
    {
        "slug": "convenience_store",
        "name": "Convenience Store",
        "google": ["convenience_store"],
        "overpass": ["shop=convenience"],
    },
    {
        "slug": "pharmacy",
        "name": "Pharmacy",
        "google": ["pharmacy", "drugstore"],
        "overpass": ["amenity=pharmacy", "shop=chemist"],
    },
]

PROVIDERS = ("google", "overpass", "fixture")


def provider_types_for(category: dict, provider: str) -> list[str]:
    # The fixture provider speaks OSM tags, since its data is an Overpass snapshot.
    return category["overpass" if provider == "fixture" else provider]
