"""seed locations and categories

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-14
"""

import sqlalchemy as sa
from alembic import op

from app.models.seed import CATEGORIES, LOCATIONS, PROVIDERS, provider_types_for

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    meta = sa.MetaData()
    countries = sa.Table("countries", meta, autoload_with=conn)
    states = sa.Table("states", meta, autoload_with=conn)
    cities = sa.Table("cities", meta, autoload_with=conn)
    categories = sa.Table("categories", meta, autoload_with=conn)
    provider_types = sa.Table("category_provider_types", meta, autoload_with=conn)

    for country in LOCATIONS:
        country_id = conn.execute(
            countries.insert()
            .values(name=country["country"], iso_code=country["iso_code"])
            .returning(countries.c.id)
        ).scalar_one()
        for state in country["states"]:
            state_id = conn.execute(
                states.insert()
                .values(country_id=country_id, name=state["name"])
                .returning(states.c.id)
            ).scalar_one()
            for city in state["cities"]:
                conn.execute(
                    cities.insert().values(
                        state_id=state_id, name=city["name"], aliases=city["aliases"]
                    )
                )

    for order, category in enumerate(CATEGORIES):
        category_id = conn.execute(
            categories.insert()
            .values(slug=category["slug"], name=category["name"], sort_order=order)
            .returning(categories.c.id)
        ).scalar_one()
        for provider in PROVIDERS:
            for provider_type in provider_types_for(category, provider):
                conn.execute(
                    provider_types.insert().values(
                        category_id=category_id, provider=provider, provider_type=provider_type
                    )
                )


def downgrade() -> None:
    for table in ("category_provider_types", "categories", "cities", "states", "countries"):
        op.execute(f"DELETE FROM {table}")
