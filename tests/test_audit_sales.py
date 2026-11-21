"""Audit regression tests: stock aggregation, locking, duplicate IMEI (phase 1)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, override_engine
from app.core.money import egp_to_piasters as egp
from app.core.seed import seed_database
from app.services import inventory_service, sales_service, shift_service

from tests.test_sales import (accessory_product, active_shift, cashier, manager,  # noqa: F401  fixtures
                              phone_product, real_customer)


def _stock(session, mgr, product, qty):
    inventory_service.adjust_stock(session, mgr, product, qty, "set")   # absolute quantity
    session.commit()


def _post(session, user, sale, **kw):
    return sales_service.post_sale(session, user, sale, [{"method": "cash", "amount": sale.total}], **kw)


class TestAggregatedStock:
    def test_two_lines_of_same_product_are_totalled(self, db_session, manager, cashier, active_shift, accessory_product):
        _stock(db_session, manager, accessory_product, 5)
        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=4)
        sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=4)
        with pytest.raises(sales_service.InsufficientStockError):
            _post(db_session, cashier, sale)
        db_session.rollback()
        assert accessory_product.current_quantity() == 5

    def test_lines_within_stock_are_accepted(self, db_session, manager, cashier, active_shift, accessory_product):
        _stock(db_session, manager, accessory_product, 5)
        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=2)
        sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=3)
        _post(db_session, cashier, sale)
        assert accessory_product.current_quantity() == 0

    def test_manager_may_override_and_cashier_with_manager_approval(self, db_session, manager, cashier,
                                                                      active_shift, accessory_product):
        _stock(db_session, manager, accessory_product, 5)
        shift_service.open_shift(db_session, manager, opening_cash=0)
        s1 = sales_service.start_sale(db_session, manager)
        sales_service.add_line(db_session, manager, s1, accessory_product, quantity=4)
        sales_service.add_line(db_session, manager, s1, accessory_product, quantity=4)
        _post(db_session, manager, s1)                           # manager: allowed, stock goes negative
        assert accessory_product.current_quantity() == -3

        _stock(db_session, manager, accessory_product, 5)
        s2 = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, s2, accessory_product, quantity=4)
        sales_service.add_line(db_session, cashier, s2, accessory_product, quantity=4)
        _post(db_session, cashier, s2, manager_override=manager)  # approved by a manager
        assert accessory_product.current_quantity() == -3

    def test_update_line_counts_other_lines_of_same_product(self, db_session, manager, cashier, active_shift,
                                                             accessory_product):
        _stock(db_session, manager, accessory_product, 5)
        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=4)
        second = sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=1)
        with pytest.raises(sales_service.InsufficientStockError):
            sales_service.update_line(db_session, cashier, sale, second.id, quantity=3)
        sales_service.update_line(db_session, cashier, sale, second.id, quantity=1)

    def test_same_imei_cannot_be_added_twice(self, db_session, manager, cashier, active_shift, phone_product):
        d = inventory_service.add_devices(db_session, manager, phone_product, [
            {"imei1": "352001111222333", "condition": "new", "purchase_cost": egp("40000")}])[0]
        db_session.commit()
        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, phone_product, device=d)
        with pytest.raises(sales_service.DeviceNotAvailableError):
            sales_service.add_line(db_session, cashier, sale, phone_product, device=d)


def test_two_sessions_cannot_oversell_the_same_stock(tmp_path):
    """Two cashiers hold drafts for 4+4 of 5 units; the second post must fail after the first commits."""
    engine = create_engine(f"sqlite:///{tmp_path / 'c.db'}", connect_args={"check_same_thread": False})
    override_engine(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER
    from app.core.security import hash_password
    from app.models.user import Role, User

    setup = Session()
    seed_database(setup)

    def user(name, role):
        u = User(username=name, password_hash=hash_password("x"), full_name=name,
                 role_id=setup.query(Role).filter_by(name=role).first().id)
        setup.add(u); setup.commit(); return u
    mgr, c1, c2 = user("m", ROLE_MANAGER), user("c1", ROLE_CASHIER), user("c2", ROLE_CASHIER)
    p = inventory_service.create_product(setup, mgr, {"name": "Cable", "type": "accessory", "cost_price": egp("10"),
                                                      "sale_price": egp("20"), "min_price": egp("15"), "min_stock": 0,
                                                      "track_imei": False, "warranty_days": 0})
    inventory_service.adjust_stock(setup, mgr, p, 5, "init")
    shift_service.open_shift(setup, c1, opening_cash=0)
    shift_service.open_shift(setup, c2, opening_cash=0)
    setup.commit()
    pid, ids = p.id, (c1.id, c2.id)
    setup.close()

    from app.models.product import Product
    sa, sb = Session(), Session()
    ua, ub = sa.get(User, ids[0]), sb.get(User, ids[1])
    pa, pb = sa.get(Product, pid), sb.get(Product, pid)
    da = sales_service.start_sale(sa, ua); sales_service.add_line(sa, ua, da, pa, quantity=4); sa.commit()
    db_ = sales_service.start_sale(sb, ub); sales_service.add_line(sb, ub, db_, pb, quantity=4); sb.commit()
    assert pb.current_quantity() == 5          # B has the stale value cached

    sales_service.post_sale(sa, ua, da, [{"method": "cash", "amount": da.total}]); sa.commit()
    with pytest.raises(sales_service.InsufficientStockError):
        sales_service.post_sale(sb, ub, db_, [{"method": "cash", "amount": db_.total}])
    sb.rollback()
    assert Session().get(Product, pid).current_quantity() == 1
    sa.close(); sb.close(); engine.dispose()


# ── Phase 2: cash change ──────────────────────────────────────────────────────
from app.models.accounting import CashAccount, CashTransaction  # noqa: E402


def _drawer(session):
    return session.query(CashAccount).filter_by(type="drawer").first()


class TestCashChange:
    def _sale(self, db_session, cashier, product, qty=1):
        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, product, quantity=qty)
        return sale

    def test_exact_payment(self, db_session, manager, cashier, active_shift, accessory_product):
        before = _drawer(db_session).balance
        sale = self._sale(db_session, cashier, accessory_product)
        sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": egp("350")}])
        assert _drawer(db_session).balance - before == egp("350")
        assert (sale.cash_tendered, sale.change_given, sale.paid) == (egp("350"), 0, egp("350"))

    def test_overpayment_records_net_cash_and_change(self, db_session, manager, cashier, active_shift,
                                                      accessory_product):
        before = _drawer(db_session).balance
        sale = self._sale(db_session, cashier, accessory_product)
        sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": egp("400")}])
        assert _drawer(db_session).balance - before == egp("350")        # not 400
        tx = db_session.query(CashTransaction).filter_by(ref_type="sale", ref_id=sale.id).one()
        assert tx.amount == egp("350")
        assert (sale.cash_tendered, sale.change_given, sale.paid, sale.remaining) == (
            egp("400"), egp("50"), egp("350"), 0)
        assert sum(p.amount for p in sale.payments) == sale.total          # payment rows are net
        expected = shift_service.calculate_expected_cash(db_session, active_shift.id)
        assert expected == active_shift.opening_cash + egp("350")

    def test_split_cash_and_wallet_change_comes_from_cash_only(self, db_session, manager, cashier, active_shift,
                                                               accessory_product):
        before = _drawer(db_session).balance
        sale = self._sale(db_session, cashier, accessory_product)
        sales_service.post_sale(db_session, cashier, sale, [
            {"method": "vodafone", "amount": egp("200")}, {"method": "cash", "amount": egp("200")}])
        assert _drawer(db_session).balance - before == egp("150")          # 350 - 200 wallet
        assert sale.change_given == egp("50")
        assert {p.method: p.amount for p in sale.payments} == {"vodafone": egp("200"), "cash": egp("150")}

    def test_non_cash_overpayment_is_rejected(self, db_session, manager, cashier, active_shift, accessory_product):
        sale = self._sale(db_session, cashier, accessory_product)
        with pytest.raises(sales_service.SaleError):
            sales_service.post_sale(db_session, cashier, sale, [{"method": "instapay", "amount": egp("400")}])
        db_session.rollback()

    def test_negative_payment_rejected_and_short_cash_needs_a_customer(self, db_session, manager, cashier,
                                                                        active_shift, accessory_product):
        sale = self._sale(db_session, cashier, accessory_product)
        with pytest.raises(sales_service.SaleError):
            sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": -5}])
        with pytest.raises(sales_service.SaleError):                      # default cash customer cannot owe
            sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": egp("50")}])
        db_session.rollback()

    def test_credit_sale_with_change_on_the_cash_part(self, db_session, manager, cashier, active_shift,
                                                      accessory_product, real_customer):
        sale = sales_service.start_sale(db_session, cashier, customer_id=real_customer.id)
        sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=1)
        before = _drawer(db_session).balance
        sales_service.post_sale(db_session, cashier, sale, [
            {"method": "credit", "amount": egp("300")}, {"method": "cash", "amount": egp("100")}])
        assert _drawer(db_session).balance - before == egp("50")           # 350 - 300 credit
        assert sale.change_given == egp("50")
        assert sale.remaining == egp("300") and real_customer.balance == egp("300")


# ── Phase 3: returns ──────────────────────────────────────────────────────────
from app.models.sale import SaleReturn  # noqa: E402


class TestReturns:
    def _posted(self, db_session, cashier, product, qty=3, customer=None, payments=None):
        sale = sales_service.start_sale(db_session, cashier, customer_id=customer.id if customer else None)
        item = sales_service.add_line(db_session, cashier, sale, product, quantity=qty)
        sales_service.post_sale(db_session, cashier, sale, payments or [{"method": "cash", "amount": sale.total}])
        db_session.commit()
        return sale, item

    def _ret(self, db_session, user, sale, rows, **kw):
        return sales_service.return_sale_items(db_session, user, sale.id, rows, reason="r", **kw)

    @pytest.mark.parametrize("qty", [0, -1, -5])
    def test_zero_and_negative_quantities_rejected_without_side_effects(self, db_session, manager, cashier,
                                                                         active_shift, accessory_product, qty):
        sale, item = self._posted(db_session, cashier, accessory_product)
        drawer, stock = _drawer(db_session).balance, accessory_product.current_quantity()
        with pytest.raises(sales_service.SaleError):
            self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": qty}])
        db_session.rollback()
        assert db_session.query(SaleReturn).count() == 0
        assert _drawer(db_session).balance == drawer and accessory_product.current_quantity() == stock

    def test_empty_return_rejected(self, db_session, manager, cashier, active_shift, accessory_product):
        sale, _ = self._posted(db_session, cashier, accessory_product)
        with pytest.raises(sales_service.SaleError):
            self._ret(db_session, cashier, sale, [])
        db_session.rollback()
        assert db_session.query(SaleReturn).count() == 0

    def test_excessive_and_repeated_returns_rejected(self, db_session, manager, cashier, active_shift,
                                                      accessory_product):
        sale, item = self._posted(db_session, cashier, accessory_product, qty=3)
        with pytest.raises(sales_service.SaleError):
            self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": 4}])
        with pytest.raises(sales_service.SaleError):       # same line twice in one request = 2 + 2 > 3
            self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": 2},
                                                  {"sale_item_id": item.id, "quantity": 2}])
        db_session.rollback()
        self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": 2}])
        with pytest.raises(sales_service.SaleError):       # 2 already returned, 2 more > 3
            self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": 2}])

    def test_one_bad_line_means_nothing_is_applied(self, db_session, manager, cashier, active_shift,
                                                    accessory_product):
        sale, item = self._posted(db_session, cashier, accessory_product, qty=3)
        before = (_drawer(db_session).balance, accessory_product.current_quantity())
        with pytest.raises(sales_service.SaleError):
            self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": 1},
                                                  {"sale_item_id": 999999, "quantity": 1}])
        db_session.rollback()
        assert (_drawer(db_session).balance, accessory_product.current_quantity()) == before

    def test_partial_returns_refund_exactly_the_line_total(self, db_session, manager, cashier, active_shift,
                                                           accessory_product):
        sale, item = self._posted(db_session, cashier, accessory_product, qty=3)
        item.line_total = 10000          # 100.00 over 3 units: 33.33 + 33.33 + 33.34
        db_session.commit()
        total = 0
        for _ in range(3):
            total += self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": 1}]).refund_amount
        assert total == 10000

    def test_partial_return_restocks_and_pays_cash_from_drawer(self, db_session, manager, cashier, active_shift,
                                                                accessory_product):
        sale, item = self._posted(db_session, cashier, accessory_product, qty=3)
        drawer, stock = _drawer(db_session).balance, accessory_product.current_quantity()
        r = self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": 1}])
        assert r.refund_amount == egp("350")
        assert _drawer(db_session).balance == drawer - egp("350")
        assert accessory_product.current_quantity() == stock + 1

    def test_return_against_credit_sale_cancels_debt_first_then_cash(self, db_session, manager, cashier,
                                                                      active_shift, accessory_product,
                                                                      real_customer):
        # 3 x 350 = 1050; customer pays 350 cash, owes 700
        sale, item = self._posted(db_session, cashier, accessory_product, qty=3, customer=real_customer,
                                  payments=[{"method": "cash", "amount": egp("350")}])
        assert real_customer.balance == egp("700")
        drawer = _drawer(db_session).balance
        self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": 1}])   # 350 -> debt
        assert real_customer.balance == egp("350") and _drawer(db_session).balance == drawer
        self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": 2}])   # 700: 350 debt + 350 cash
        assert real_customer.balance == 0 and _drawer(db_session).balance == drawer - egp("350")

    def test_unrelated_debt_is_not_touched_by_a_paid_sale_return(self, db_session, manager, cashier, active_shift,
                                                                  accessory_product, real_customer):
        real_customer.balance = egp("500")       # old debt from other invoices
        db_session.commit()
        sale, item = self._posted(db_session, cashier, accessory_product, qty=1, customer=real_customer)
        drawer = _drawer(db_session).balance
        self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": 1}])
        assert real_customer.balance == egp("500")
        assert _drawer(db_session).balance == drawer - egp("350")

    def test_void_after_partial_return_returns_only_the_rest(self, db_session, manager, cashier, active_shift,
                                                              accessory_product):
        sale, item = self._posted(db_session, cashier, accessory_product, qty=3)
        self._ret(db_session, cashier, sale, [{"sale_item_id": item.id, "quantity": 1}])
        stock = accessory_product.current_quantity()
        shift_service.open_shift(db_session, manager, opening_cash=0)
        sales_service.void_sale(db_session, manager, sale.id, "cancel")
        assert sale.status == "void" and accessory_product.current_quantity() == stock + 2
        total = sum(r.refund_amount for r in sale.returns)
        assert total == sale.total


# ── Phase 4: profit after returns ─────────────────────────────────────────────
from app.core import clock  # noqa: E402
from app.services import report_service  # noqa: E402
from app.services.sales_profit import net_sales_profit  # noqa: E402


def _day(db_session):
    s, e = clock.day_bounds_utc(clock.local_today(), clock.local_today())
    return s, e


class TestProfitAfterReturns:
    """Charger: cost 200, price 350 (profit 150/unit)."""

    def _sale(self, db_session, cashier, product, qty, discount=0):
        sale = sales_service.start_sale(db_session, cashier)
        item = sales_service.add_line(db_session, cashier, sale, product, quantity=qty, discount=discount)
        sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": sale.total}])
        db_session.commit()
        return sale, item

    def test_no_returns_equals_old_definition(self, db_session, manager, cashier, active_shift, accessory_product):
        sale, _ = self._sale(db_session, cashier, accessory_product, 3)
        r = net_sales_profit(db_session, *_day(db_session))
        assert r["net_profit"] == sale.total_profit == 3 * 150 * 100

    def test_partial_restocked_return_removes_revenue_and_cost(self, db_session, manager, cashier, active_shift,
                                                                accessory_product):
        sale, item = self._sale(db_session, cashier, accessory_product, 3)
        sales_service.return_sale_items(db_session, cashier, sale.id,
                                        [{"sale_item_id": item.id, "quantity": 1}], reason="r", restock=True)
        r = net_sales_profit(db_session, *_day(db_session))
        assert r["net_revenue"] == egp("700") and r["net_profit"] == 2 * egp("150")

    def test_non_restocked_return_keeps_the_cost_as_a_loss(self, db_session, manager, cashier, active_shift,
                                                           accessory_product):
        sale, item = self._sale(db_session, cashier, accessory_product, 3)
        sales_service.return_sale_items(db_session, cashier, sale.id,
                                        [{"sale_item_id": item.id, "quantity": 1}], reason="r", restock=False)
        r = net_sales_profit(db_session, *_day(db_session))
        assert r["net_profit"] == 3 * egp("150") - egp("350")             # 100: the 200 cost is lost

    def test_discount_is_respected_in_returned_revenue(self, db_session, manager, cashier, active_shift,
                                                       accessory_product):
        sale, item = self._sale(db_session, cashier, accessory_product, 2, discount=egp("50"))   # 650 total
        sales_service.return_sale_items(db_session, cashier, sale.id,
                                        [{"sale_item_id": item.id, "quantity": 2}], reason="r")
        r = net_sales_profit(db_session, *_day(db_session))
        assert r["net_revenue"] == 0 and r["net_profit"] == 0

    def test_full_return_and_void_do_not_double_count(self, db_session, manager, cashier, active_shift,
                                                      accessory_product):
        s1, i1 = self._sale(db_session, cashier, accessory_product, 2)
        s2, _ = self._sale(db_session, cashier, accessory_product, 1)
        sales_service.return_sale_items(db_session, cashier, s1.id,
                                        [{"sale_item_id": i1.id, "quantity": 2}], reason="r")
        shift_service.open_shift(db_session, manager, opening_cash=0)
        sales_service.void_sale(db_session, manager, s2.id, "x")
        r = net_sales_profit(db_session, *_day(db_session))
        assert r["net_revenue"] == 0 and r["net_profit"] == 0
        assert len(r["sales"]) == 1          # only the posted invoice is listed (the voided one is not)

    def test_report_service_uses_the_same_numbers(self, db_session, manager, cashier, active_shift,
                                                  accessory_product):
        sale, item = self._sale(db_session, cashier, accessory_product, 3)
        sales_service.return_sale_items(db_session, cashier, sale.id,
                                        [{"sale_item_id": item.id, "quantity": 1}], reason="r")
        pl = report_service.profit_report(db_session, manager)
        assert pl["sales_profit"] == 2 * egp("150") and pl["gross_sales_profit"] == 3 * egp("150")
        assert pl["returns_revenue"] == egp("350") and pl["returns_cost_recovered"] == egp("200")
        assert report_service.sales_report(db_session, manager)["total_profit"] == pl["sales_profit"]
        ov = report_service.dashboard_overview(db_session, manager)
        assert ov["sales"]["today"]["profit"] == pl["sales_profit"]

    def test_reconciles_with_the_ledgers(self, db_session, manager, cashier, active_shift, accessory_product):
        """revenue - cost of units that stayed sold == net profit, from stock movements and cash."""
        sale, item = self._sale(db_session, cashier, accessory_product, 4)
        sales_service.return_sale_items(db_session, cashier, sale.id,
                                        [{"sale_item_id": item.id, "quantity": 1}], reason="r")
        units_sold_net = 4 - 1
        cash_in = sum(t.amount for t in db_session.query(CashTransaction).filter_by(type="in", category="sale"))
        cash_out = sum(t.amount for t in db_session.query(CashTransaction).filter_by(type="out", category="return"))
        r = net_sales_profit(db_session, *_day(db_session))
        assert cash_in - cash_out == r["net_revenue"]
        assert r["net_profit"] == r["net_revenue"] - units_sold_net * accessory_product.cost_price


# ── Phases 5-6: shifts and supplier payments ──────────────────────────────────
from app.models.shift import Shift  # noqa: E402
from app.services import accounting_service, purchase_service  # noqa: E402


class TestShiftLifecycle:
    def test_full_lifecycle_expected_cash_matches_the_ledger(self, db_session, manager, cashier, active_shift,
                                                             accessory_product, real_customer):
        drawer = _drawer(db_session)
        drawer.balance = active_shift.opening_cash          # drawer holds exactly the opening cash
        db_session.commit()
        # cash sale 350 (tendered 400 -> change 50)
        s1 = sales_service.start_sale(db_session, cashier)
        i1 = sales_service.add_line(db_session, cashier, s1, accessory_product, quantity=1)
        sales_service.post_sale(db_session, cashier, s1, [{"method": "cash", "amount": egp("400")}])
        # credit sale 700 with 200 cash
        s2 = sales_service.start_sale(db_session, cashier, customer_id=real_customer.id)
        sales_service.add_line(db_session, cashier, s2, accessory_product, quantity=2)
        sales_service.post_sale(db_session, cashier, s2, [{"method": "cash", "amount": egp("200")}])
        # partial return of the first sale (cash back)
        sales_service.return_sale_items(db_session, cashier, s1.id, [{"sale_item_id": i1.id, "quantity": 1}],
                                        reason="r")
        # expense 20 paid from the drawer
        cat = accounting_service.create_expense_category(db_session, manager, "كهرباء")
        accounting_service.add_expense(db_session, cashier, cat.id, egp("20"), drawer.id)
        db_session.commit()

        expected = shift_service.calculate_expected_cash(db_session, active_shift.id)
        assert expected == active_shift.opening_cash + egp("350") + egp("200") - egp("350") - egp("20")
        assert expected == drawer.balance                                   # ledger == shift expectation
        assert accounting_service.verify_drawer_balance_integrity(db_session, drawer.id)

        # counted 10 EGP short
        closed = shift_service.close_shift(db_session, cashier, active_shift.id, actual_cash=expected - egp("10"))
        db_session.commit()
        assert closed.diff == -egp("10") and closed.expected_cash == expected
        assert drawer.balance == expected - egp("10")                      # book balance now equals the count
        assert accounting_service.verify_drawer_balance_integrity(db_session, drawer.id)
        # the recorded expectation does not change after the adjustment entry exists
        assert shift_service.calculate_expected_cash(db_session, active_shift.id) == expected
        # the shortage reaches P&L exactly once
        pl = report_service.profit_report(db_session, manager)
        assert pl["shift_diff"] == -egp("10")
        assert pl["net_profit"] == pl["sales_profit"] + pl["wallet_profit"] - pl["total_expenses"] - egp("10")

    def test_overage_is_added_to_the_drawer(self, db_session, manager, cashier, active_shift, accessory_product):
        drawer = _drawer(db_session)
        drawer.balance = active_shift.opening_cash
        db_session.commit()
        closed = shift_service.close_shift(db_session, cashier, active_shift.id,
                                           actual_cash=active_shift.opening_cash + egp("25"))
        assert closed.diff == egp("25") and drawer.balance == active_shift.opening_cash + egp("25")

    def test_bank_account_expense_does_not_change_drawer_expectation(self, db_session, manager, cashier,
                                                                      active_shift):
        from app.models.accounting import CashAccount
        bank = CashAccount(name="بنك", type="bank", balance=egp("1000"))
        db_session.add(bank); db_session.commit()
        before = shift_service.calculate_expected_cash(db_session, active_shift.id)
        cat = accounting_service.create_expense_category(db_session, manager, "رسوم")
        accounting_service.add_expense(db_session, cashier, cat.id, egp("100"), bank.id)
        assert shift_service.calculate_expected_cash(db_session, active_shift.id) == before

    def test_drawer_transfer_moves_expected_cash(self, db_session, manager, cashier, active_shift):
        """Moving cash from the drawer to a safe lowers what must be in the drawer at close."""
        from app.models.accounting import CashAccount
        from app.core.permissions import PermissionDenied  # noqa: F401
        safe = CashAccount(name="خزنة", type="safe", balance=0)
        drawer = _drawer(db_session)
        drawer.balance += egp("500")
        db_session.add(safe); db_session.commit()
        before = shift_service.calculate_expected_cash(db_session, active_shift.id)
        shift_service.open_shift(db_session, manager, opening_cash=0)     # the manager moves the cash...
        accounting_service.transfer(db_session, manager, drawer.id, safe.id, egp("300"))
        # ...and it is attributed to the manager's own shift, so the cashier's expectation is unchanged
        assert shift_service.calculate_expected_cash(db_session, active_shift.id) == before


class TestSupplierPayments:
    def _invoice(self, db_session, manager, product, total_units=10, cost="100", paid="0"):
        sup = purchase_service.create_supplier(db_session, manager, name="Sup2", phone="0101")
        db_session.commit()
        p = purchase_service.create_purchase(
            db_session, manager, supplier_id=sup.id, invoice_number=f"T-{sup.id}-{total_units}",
            items_data=[{"product_id": product.id, "quantity": total_units, "unit_cost": egp(cost)}],
            paid_amount=egp(paid))
        db_session.commit()
        return sup, p

    def test_partial_then_full_payment_keeps_all_balances_consistent(self, db_session, manager, accessory_product):
        _drawer(db_session).balance = egp("5000")
        sup, inv = self._invoice(db_session, manager, accessory_product)             # 1000 owed
        assert sup.balance == egp("1000") and inv.balance == egp("1000")
        purchase_service.pay_supplier(db_session, manager, sup.id, egp("400"), purchase_id=inv.id)
        purchase_service.pay_supplier(db_session, manager, sup.id, egp("600"), purchase_id=inv.id)
        assert (sup.balance, inv.balance, inv.paid) == (0, 0, egp("1000"))
        assert _drawer(db_session).balance == egp("4000")
        paid_tx = db_session.query(CashTransaction).filter(
            CashTransaction.category == "supplier_payment").all()
        assert sum(x.amount for x in paid_tx) == egp("1000")                       # ledger matches the payments

    def test_overpayment_is_rejected(self, db_session, manager, accessory_product):
        _drawer(db_session).balance = egp("5000")
        sup, inv = self._invoice(db_session, manager, accessory_product)
        with pytest.raises(purchase_service.PurchaseError):
            purchase_service.pay_supplier(db_session, manager, sup.id, egp("1001"), purchase_id=inv.id)
        with pytest.raises(purchase_service.PurchaseError):                           # general payment > owed
            purchase_service.pay_supplier(db_session, manager, sup.id, egp("1001"))
        db_session.rollback()
        assert _drawer(db_session).balance == egp("5000")

    def test_insufficient_account_balance_is_rejected_and_nothing_changes(self, db_session, manager,
                                                                           accessory_product):
        _drawer(db_session).balance = egp("5000")
        sup, inv = self._invoice(db_session, manager, accessory_product)
        _drawer(db_session).balance = egp("300")
        db_session.commit()
        with pytest.raises(purchase_service.PurchaseError):
            purchase_service.pay_supplier(db_session, manager, sup.id, egp("400"), purchase_id=inv.id)
        db_session.rollback()
        assert (sup.balance, inv.balance) == (egp("1000"), egp("1000"))
        assert _drawer(db_session).balance == egp("300")

    def test_invoice_payment_from_empty_drawer_is_rejected(self, db_session, manager, accessory_product):
        _drawer(db_session).balance = egp("100")
        with pytest.raises(purchase_service.PurchaseError):
            self._invoice(db_session, manager, accessory_product, paid="1000")
        db_session.rollback()

    def test_supplier_payment_is_counted_in_the_open_shift(self, db_session, manager, cashier, active_shift,
                                                            accessory_product):
        _drawer(db_session).balance = active_shift.opening_cash + egp("5000")
        sup, inv = self._invoice(db_session, manager, accessory_product)
        before = shift_service.calculate_expected_cash(db_session, active_shift.id)
        purchase_service.pay_supplier(db_session, manager, sup.id, egp("250"), purchase_id=inv.id)
        assert shift_service.calculate_expected_cash(db_session, active_shift.id) == before - egp("250")


# ── Phase 7: permissions enforced inside the services ─────────────────────────
class TestServiceLevelPermissions:
    @pytest.fixture
    def wallet_emp(self, db_session):
        from app.core.permissions import ROLE_WALLET_EMPLOYEE
        from app.core.security import hash_password
        from app.models.user import Role, User
        r = db_session.query(Role).filter_by(name=ROLE_WALLET_EMPLOYEE).first()
        u = User(username="we", password_hash=hash_password("x"), full_name="we", role_id=r.id)
        db_session.add(u); db_session.commit()
        return u

    def test_wallet_employee_cannot_sell(self, db_session, wallet_emp, manager, accessory_product):
        from app.core.permissions import PermissionDenied
        sale = sales_service.start_sale(db_session, manager)
        with pytest.raises(PermissionDenied):
            sales_service.add_line(db_session, wallet_emp, sale, accessory_product)
        with pytest.raises(PermissionDenied):
            sales_service.post_sale(db_session, wallet_emp, sale, [])

    def test_cashier_cannot_void_buy_pay_suppliers_or_draw_money(self, db_session, cashier, manager,
                                                                  accessory_product, active_shift):
        from app.core.permissions import PermissionDenied
        with pytest.raises(PermissionDenied):
            sales_service.void_sale(db_session, cashier, 1, "x")
        with pytest.raises(PermissionDenied):
            purchase_service.create_supplier(db_session, cashier, name="x", phone="1")
        with pytest.raises(PermissionDenied):
            purchase_service.pay_supplier(db_session, cashier, 1, 100)
        with pytest.raises(PermissionDenied):
            accounting_service.owner_draw(db_session, cashier, _drawer(db_session).id, 100)
        from app.services import wallet_service
        with pytest.raises(PermissionDenied):
            wallet_service.create_commission_rule(db_session, cashier, "vodafone", "cash_in", 0, 0, 100, 0)

    def test_cashier_cannot_oversell_without_manager_even_by_direct_call(self, db_session, cashier, manager,
                                                                          accessory_product, active_shift):
        _stock(db_session, manager, accessory_product, 1)
        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=2)
        with pytest.raises(sales_service.InsufficientStockError):
            _post(db_session, cashier, sale)
        with pytest.raises(sales_service.InsufficientStockError):                  # a cashier "override" is ignored
            _post(db_session, cashier, sale, manager_override=cashier)
        db_session.rollback()


# ── Phase 7: IMEI integrity ───────────────────────────────────────────────────
class TestImeiIntegrity:
    def test_imei_unique_across_both_fields_and_luhn(self, db_session, manager, phone_product):
        from app.services import inventory_service as inv
        errs = tuple(c for c in vars(inv).values() if isinstance(c, type) and issubclass(c, Exception)
                     and c.__module__ == inv.__name__) + (ValueError,)
        inventory_service.add_devices(db_session, manager, phone_product, [
            {"imei1": "352001111222333", "imei2": "352001111222341", "condition": "new",
             "purchase_cost": egp("100")}])
        db_session.commit()
        for bad in ({"imei1": "352001111222333"},                 # duplicate imei1
                    {"imei1": "352001111222341"},                 # imei1 equals another device's imei2
                    {"imei1": "490154203237518", "imei2": "352001111222333"},   # imei2 equals imei1 elsewhere
                    {"imei1": "123"},                              # malformed
                    {"imei1": "35200111122233X"},                  # not digits
                    {"imei1": "490154203237518", "imei2": "490154203237518"}):   # imei1 == imei2
            with pytest.raises(errs):
                inventory_service.add_devices(db_session, manager, phone_product,
                                              [{**bad, "condition": "new", "purchase_cost": egp("100")}])
                db_session.flush()
            db_session.rollback()

    def test_sold_device_returns_to_stock_once_and_can_be_resold(self, db_session, manager, cashier, active_shift,
                                                                  phone_product):
        d = inventory_service.add_devices(db_session, manager, phone_product, [
            {"imei1": "352001111222333", "condition": "new", "purchase_cost": egp("40000")}])[0]
        db_session.commit()
        s1 = sales_service.start_sale(db_session, cashier)
        it = sales_service.add_line(db_session, cashier, s1, phone_product, device=d)
        _post(db_session, cashier, s1)
        assert d.status == "sold" and phone_product.current_quantity() == 0
        sales_service.return_sale_items(db_session, cashier, s1.id, [{"sale_item_id": it.id, "quantity": 1}],
                                        reason="r")
        assert d.status == "in_stock" and phone_product.current_quantity() == 1
        with pytest.raises(sales_service.SaleError):                 # cannot be returned again
            sales_service.return_sale_items(db_session, cashier, s1.id,
                                            [{"sale_item_id": it.id, "quantity": 1}], reason="r")
        db_session.rollback()
        s2 = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, s2, phone_product, device=d)
        _post(db_session, cashier, s2)
        assert d.status == "sold"
        from app.models.stock import StockMovement
        net = sum(m.quantity for m in db_session.query(StockMovement).filter_by(device_id=d.id)
                  if m.type in ("sale", "return_in"))
        assert net == -1                                              # sold, returned, sold again
