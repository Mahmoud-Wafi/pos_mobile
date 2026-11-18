"""repair_tickets

Revision ID: b7d3f9a41c22
Revises: a1c5e7f20b11
Create Date: 2026-11-18 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7d3f9a41c22'
down_revision: Union[str, None] = 'a1c5e7f20b11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('repair_tickets',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ticket_no', sa.String(length=30), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('customer_name', sa.String(length=150), nullable=False),
    sa.Column('customer_phone', sa.String(length=30), nullable=True),
    sa.Column('device_desc', sa.String(length=200), nullable=False),
    sa.Column('imei', sa.String(length=20), nullable=True),
    sa.Column('issue', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('estimate', sa.Integer(), nullable=False),
    sa.Column('final_price', sa.Integer(), nullable=False),
    sa.Column('parts_cost', sa.Integer(), nullable=False),
    sa.Column('paid', sa.Integer(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('received_by', sa.Integer(), nullable=True),
    sa.Column('received_at', sa.DateTime(), nullable=False),
    sa.Column('ready_at', sa.DateTime(), nullable=True),
    sa.Column('delivered_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['received_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_repair_tickets_ticket_no'), 'repair_tickets', ['ticket_no'], unique=True)
    op.create_index(op.f('ix_repair_tickets_imei'), 'repair_tickets', ['imei'], unique=False)
    op.create_index(op.f('ix_repair_tickets_status'), 'repair_tickets', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_repair_tickets_status'), table_name='repair_tickets')
    op.drop_index(op.f('ix_repair_tickets_imei'), table_name='repair_tickets')
    op.drop_index(op.f('ix_repair_tickets_ticket_no'), table_name='repair_tickets')
    op.drop_table('repair_tickets')
