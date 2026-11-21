"""sale cash tendered / change given

Revision ID: d5f1b3c7a901
Revises: c4e8a2d90f33
Create Date: 2026-11-21 15:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5f1b3c7a901'
down_revision: Union[str, None] = 'c4e8a2d90f33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('sales') as batch:
        batch.add_column(sa.Column('cash_tendered', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('change_given', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('sales') as batch:
        batch.drop_column('change_given')
        batch.drop_column('cash_tendered')
