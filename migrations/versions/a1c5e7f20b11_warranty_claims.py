"""warranty_claims

Revision ID: a1c5e7f20b11
Revises: 04aa6a43be4d
Create Date: 2026-11-18 14:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c5e7f20b11'
down_revision: Union[str, None] = '04aa6a43be4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('warranty_claims',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('sale_item_id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=True),
    sa.Column('issue', sa.Text(), nullable=False),
    sa.Column('resolution', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('in_warranty', sa.Boolean(), nullable=False),
    sa.Column('opened_by', sa.Integer(), nullable=True),
    sa.Column('opened_at', sa.DateTime(), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
    sa.ForeignKeyConstraint(['opened_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['sale_item_id'], ['sale_items.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_warranty_claims_sale_item_id'), 'warranty_claims', ['sale_item_id'], unique=False)
    op.create_index(op.f('ix_warranty_claims_status'), 'warranty_claims', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_warranty_claims_status'), table_name='warranty_claims')
    op.drop_index(op.f('ix_warranty_claims_sale_item_id'), table_name='warranty_claims')
    op.drop_table('warranty_claims')
