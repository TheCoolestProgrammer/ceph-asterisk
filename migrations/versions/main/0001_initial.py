"""initial main schema

Revision ID: 0001
Revises:
Create Date: 2025-06-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_main"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("main",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("login", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.Enum("ADMIN", name="role"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_login"), "users", ["login"], unique=True)

    op.create_table(
        "asterisk_instances",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("sip_port", sa.Integer(), nullable=True),
        sa.Column("http_port", sa.Integer(), nullable=True),
        sa.Column("rtp_port_start", sa.Integer(), nullable=True),
        sa.Column("rtp_port_end", sa.Integer(), nullable=True),
        sa.Column("ami_port", sa.Integer(), nullable=True),
        sa.Column("config_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("create_date", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_asterisk_instances_id"), "asterisk_instances", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_asterisk_instances_name"), "asterisk_instances", ["name"], unique=True
    )
    op.create_index(
        op.f("ix_asterisk_instances_sip_port"),
        "asterisk_instances",
        ["sip_port"],
        unique=True,
    )
    op.create_index(
        op.f("ix_asterisk_instances_http_port"),
        "asterisk_instances",
        ["http_port"],
        unique=True,
    )
    op.create_index(
        op.f("ix_asterisk_instances_rtp_port_start"),
        "asterisk_instances",
        ["rtp_port_start"],
        unique=True,
    )
    op.create_index(
        op.f("ix_asterisk_instances_rtp_port_end"),
        "asterisk_instances",
        ["rtp_port_end"],
        unique=True,
    )
    op.create_index(
        op.f("ix_asterisk_instances_ami_port"),
        "asterisk_instances",
        ["ami_port"],
        unique=True,
    )

    op.create_table(
        "audio_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("format", sa.String(length=5), nullable=True),
        sa.Column("size_kb", sa.Float(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("create_date", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audio_files_id"), "audio_files", ["id"], unique=False)
    op.create_index(
        op.f("ix_audio_files_name"), "audio_files", ["name"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audio_files_name"), table_name="audio_files")
    op.drop_index(op.f("ix_audio_files_id"), table_name="audio_files")
    op.drop_table("audio_files")

    op.drop_index(op.f("ix_asterisk_instances_ami_port"), table_name="asterisk_instances")
    op.drop_index(
        op.f("ix_asterisk_instances_rtp_port_end"), table_name="asterisk_instances"
    )
    op.drop_index(
        op.f("ix_asterisk_instances_rtp_port_start"), table_name="asterisk_instances"
    )
    op.drop_index(
        op.f("ix_asterisk_instances_http_port"), table_name="asterisk_instances"
    )
    op.drop_index(
        op.f("ix_asterisk_instances_sip_port"), table_name="asterisk_instances"
    )
    op.drop_index(op.f("ix_asterisk_instances_name"), table_name="asterisk_instances")
    op.drop_index(op.f("ix_asterisk_instances_id"), table_name="asterisk_instances")
    op.drop_table("asterisk_instances")

    op.drop_index(op.f("ix_users_login"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
