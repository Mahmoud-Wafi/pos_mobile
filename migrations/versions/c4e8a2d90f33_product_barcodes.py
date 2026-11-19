"""product_barcodes

Revision ID: c4e8a2d90f33
Revises: b7d3f9a41c22
Create Date: 2026-11-19 14:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e8a2d90f33'
down_revision: Union[str, None] = 'b7d3f9a41c22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('product_barcodes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_product_barcodes_code'), 'product_barcodes', ['code'], unique=True)
    op.create_index(op.f('ix_product_barcodes_product_id'), 'product_barcodes', ['product_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_product_barcodes_product_id'), table_name='product_barcodes')
    op.drop_index(op.f('ix_product_barcodes_code'), table_name='product_barcodes')
    op.drop_table('product_barcodes')
