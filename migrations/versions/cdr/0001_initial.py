"""initial cdr schema

Revision ID: 0001
Revises:
Create Date: 2025-06-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_cdr"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("cdr",)
depends_on: Union[str, Sequence[str], None] = None

choise_enum = sa.Enum("YES", "NO", name="choise")


def upgrade() -> None:
    op.create_table(
        "ps_aors",
        sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("reg_server", sa.String(length=60), nullable=True),
        sa.Column("max_contacts", sa.Integer(), nullable=True),
        sa.Column("remove_existing", choise_enum, nullable=True),
        sa.Column("minimum_expiration", sa.Integer(), nullable=True),
        sa.Column("default_expiration", sa.Integer(), nullable=True),
        sa.Column("qualify_frequency", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("pk", "id"),
    )

    op.create_table(
        "ps_auths",
        sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column(
            "auth_type",
            sa.Enum("userpass", "md5", name="authtype"),
            nullable=True,
        ),
        sa.Column("password", sa.String(length=80), nullable=True),
        sa.Column("username", sa.String(length=80), nullable=True),
        sa.PrimaryKeyConstraint("pk", "id"),
    )

    op.create_table(
        "ps_endpoints",
        sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(length=40), nullable=True),
        sa.Column("transport", sa.String(length=40), nullable=True),
        sa.Column("aors", sa.String(length=200), nullable=True),
        sa.Column("auth", sa.String(length=40), nullable=True),
        sa.Column("aors_id", sa.Integer(), nullable=True),
        sa.Column("auths_id", sa.Integer(), nullable=True),
        sa.Column("callerid", sa.String(length=80), nullable=True),
        sa.Column("context", sa.String(length=40), nullable=True),
        sa.Column("disallow", sa.String(length=200), nullable=True),
        sa.Column("allow", sa.String(length=200), nullable=True),
        sa.Column("direct_media", choise_enum, nullable=True),
        sa.Column("rewrite_contact", choise_enum, nullable=True),
        sa.Column("rtp_symmetric", choise_enum, nullable=True),
        sa.Column("force_rport", choise_enum, nullable=True),
        sa.Column("mwi_from_user", sa.String(length=40), nullable=True),
        sa.Column("mailboxes", sa.String(length=80), nullable=True),
        sa.Column("trust_id_inbound", choise_enum, nullable=True),
        sa.Column("trust_id_outbound", choise_enum, nullable=True),
        sa.ForeignKeyConstraint(["aors_id"], ["ps_aors.pk"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["auths_id"], ["ps_auths.pk"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pk"),
    )

    op.create_table(
        "ps_contacts",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("uri", sa.String(length=255), nullable=True),
        sa.Column("expiration_time", sa.String(length=40), nullable=True),
        sa.Column("qualify_frequency", sa.Integer(), nullable=True),
        sa.Column("endpoint", sa.String(length=40), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ps_domain_aliases",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ps_endpoint_id_ips",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("endpoint", sa.String(length=40), nullable=True),
        sa.Column("match", sa.String(length=80), nullable=True),
        sa.Column("srv_lookups", choise_enum, nullable=True),
        sa.Column("match_geader", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ast_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instance_id", sa.Integer(), nullable=False),
        sa.Column("cat_metric", sa.Integer(), nullable=True),
        sa.Column("var_metric", sa.Integer(), nullable=True),
        sa.Column("filename", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("var_name", sa.String(length=128), nullable=False),
        sa.Column("var_val", sa.String(length=128), nullable=False),
        sa.Column("commented", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ast_config_id"), "ast_config", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_ast_config_instance_id"),
        "ast_config",
        ["instance_id"],
        unique=False,
    )

    op.create_table(
        "ast_config_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instance_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_snapshot", sa.Text(), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("author", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instance_id",
            "filename",
            "version",
            name="uq_ast_config_history_instance_file_version",
        ),
    )
    op.create_index(
        op.f("ix_ast_config_history_id"), "ast_config_history", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_ast_config_history_instance_id"),
        "ast_config_history",
        ["instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ast_config_history_filename"),
        "ast_config_history",
        ["filename"],
        unique=False,
    )

    op.create_table(
        "asterisk_cdr",
        sa.Column("accountcode", sa.String(length=80), nullable=True),
        sa.Column("src", sa.String(length=80), nullable=True),
        sa.Column("dst", sa.String(length=80), nullable=True),
        sa.Column("dcontext", sa.String(length=80), nullable=True),
        sa.Column("clid", sa.String(length=80), nullable=True),
        sa.Column("channel", sa.String(length=80), nullable=True),
        sa.Column("dstchannel", sa.String(length=80), nullable=True),
        sa.Column("lastapp", sa.String(length=80), nullable=True),
        sa.Column("lastdata", sa.String(length=80), nullable=True),
        sa.Column("start", sa.DateTime(), nullable=True),
        sa.Column("answer", sa.DateTime(), nullable=True),
        sa.Column("end", sa.DateTime(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("billsec", sa.Integer(), nullable=True),
        sa.Column("disposition", sa.String(length=45), nullable=True),
        sa.Column("amaflags", sa.Integer(), nullable=True),
        sa.Column("uniqueid", sa.String(length=150), nullable=False),
        sa.Column("userfield", sa.String(length=255), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("uniqueid"),
    )


def downgrade() -> None:
    op.drop_table("asterisk_cdr")

    op.drop_index(
        op.f("ix_ast_config_history_filename"), table_name="ast_config_history"
    )
    op.drop_index(
        op.f("ix_ast_config_history_instance_id"), table_name="ast_config_history"
    )
    op.drop_index(op.f("ix_ast_config_history_id"), table_name="ast_config_history")
    op.drop_table("ast_config_history")

    op.drop_index(op.f("ix_ast_config_instance_id"), table_name="ast_config")
    op.drop_index(op.f("ix_ast_config_id"), table_name="ast_config")
    op.drop_table("ast_config")

    op.drop_table("ps_endpoint_id_ips")
    op.drop_table("ps_domain_aliases")
    op.drop_table("ps_contacts")
    op.drop_table("ps_endpoints")
    op.drop_table("ps_auths")
    op.drop_table("ps_aors")
