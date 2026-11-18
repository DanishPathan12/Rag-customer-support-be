"""Add names to users and pending signup OTPs.

Revision ID: 0002_user_names
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0002_user_names"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _add_column_if_missing(table_name: str, column_name: str) -> None:
    inspector = inspect(op.get_bind())
    if inspector.has_table(table_name) and column_name not in {
        column["name"] for column in inspector.get_columns(table_name)
    }:
        op.add_column(
            table_name,
            sa.Column(column_name, sa.String(length=100), nullable=True),
        )


def upgrade() -> None:
    _add_column_if_missing("users", "first_name")
    _add_column_if_missing("users", "last_name")
    _add_column_if_missing("email_otps", "first_name")
    _add_column_if_missing("email_otps", "last_name")


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    for table_name in ("email_otps", "users"):
        if inspector.has_table(table_name):
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name in ("last_name", "first_name"):
                if column_name in columns:
                    op.drop_column(table_name, column_name)
