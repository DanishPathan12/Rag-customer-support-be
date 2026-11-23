"""Add administrator access and a dedicated administrator OTP purpose.

Revision ID: 0003_admin_role
Revises: 0002_user_names
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0003_admin_role"
down_revision = "0002_user_names"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return inspector.has_table(table_name) and column_name in {
        column["name"] for column in inspector.get_columns(table_name)
    }


def upgrade() -> None:
    if not _has_column("users", "is_admin"):
        op.add_column(
            "users",
            sa.Column(
                "is_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    # The original non-native enum was stored as VARCHAR(6), which cannot
    # hold the new ADMIN_LOGIN enum name.
    if _has_column("email_otps", "purpose"):
        with op.batch_alter_table("email_otps") as batch_op:
            batch_op.alter_column(
                "purpose",
                existing_type=sa.String(length=6),
                type_=sa.String(length=11),
                existing_nullable=False,
            )


def downgrade() -> None:
    if _has_column("email_otps", "purpose"):
        with op.batch_alter_table("email_otps") as batch_op:
            batch_op.alter_column(
                "purpose",
                existing_type=sa.String(length=11),
                type_=sa.String(length=6),
                existing_nullable=False,
            )
    if _has_column("users", "is_admin"):
        op.drop_column("users", "is_admin")
