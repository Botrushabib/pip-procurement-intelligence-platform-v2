from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
import inspect

import pytest

from app.services.receiving_event_analytics_preparation import (
    PreparedReceivingEventLine,
    ReceivingAnalyticsEligibility,
)
from app.services.receiving_supplier_comparative_intelligence import (
    ReceivingSupplierComparativeDataQuality,
    ReceivingSupplierComparativeDataSufficiency,
    ReceivingSupplierComparativeIntelligence,
    ReceivingSupplierComparativeSummary,
    ReceivingSupplierComparisonObservation,
    ReceivingSupplierComparisonRequest,
    ReceivingSupplierPriceComparison,
    ReceivingSupplierProductComparison,
    SupplierPricePosition,
    analyze_receiving_supplier_comparison,
)


def make_prepared_line(
    event_id: int = 1,
    line_id: int = 101,
    line_number: int = 1,
    event_date: date | None = date(2026, 3, 15),
    receiving_reference: str = "REC-REF-001",
    company_id: int = 10,
    company_name: str | None = "Acme Corp",
    supplier_id: int = 20,
    supplier_name: str | None = "Supplier One",
    warehouse_id: int = 30,
    warehouse_name: str | None = "Main Warehouse",
    product_id: int = 200,
    product_code: str | None = "PROD-200",
    product_name: str | None = "Steel Rod",
    category_id: int | None = 50,
    category_name: str | None = "Metals",
    unit_id: int | None = 300,
    unit_name: str | None = "kg",
    quantity: Decimal = Decimal("100.00"),
    unit_price: Decimal = Decimal("25.00"),
    subtotal: Decimal = Decimal("2500.00"),
    source_file: str = "receiving_batch.xlsx",
    source_sheet: str = "Sheet1",
    source_row: int = 2,
    eligible: bool = True,
    eligibility_override: ReceivingAnalyticsEligibility | None = None,
) -> PreparedReceivingEventLine:
    if eligibility_override is not None:
        eligibility = eligibility_override
    else:
        eligibility = ReceivingAnalyticsEligibility(
            has_event_date=event_date is not None,
            has_product=product_id is not None and product_id > 0,
            has_quantity=quantity is not None and quantity > 0,
            has_unit_price=unit_price is not None and unit_price >= 0,
            has_supplier=supplier_id is not None and supplier_id > 0,
            has_warehouse=warehouse_id is not None and warehouse_id > 0,
        )
        if not eligible:
            eligibility = ReceivingAnalyticsEligibility(
                has_event_date=False,
                has_product=True,
                has_quantity=True,
                has_unit_price=True,
                has_supplier=True,
                has_warehouse=True,
            )

    year = event_date.year if event_date else None
    month = event_date.month if event_date else None

    return PreparedReceivingEventLine(
        event_id=event_id,
        line_id=line_id,
        line_number=line_number,
        event_date=event_date,
        year=year,
        month=month,
        receiving_reference=receiving_reference,
        company_id=company_id,
        company_name=company_name,
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        warehouse_id=warehouse_id,
        warehouse_name=warehouse_name,
        product_id=product_id,
        product_code=product_code,
        product_name=product_name,
        category_id=category_id,
        category_name=category_name,
        unit_id=unit_id,
        unit_name=unit_name,
        quantity=quantity,
        unit_price=unit_price,
        subtotal=subtotal,
        source_file=source_file,
        source_sheet=source_sheet,
        source_row=source_row,
        eligibility=eligibility,
    )


def test_01_empty_input():
    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[],
    )

    assert result.sufficiency == ReceivingSupplierComparativeDataSufficiency.INSUFFICIENT_DATA
    assert result.observations == ()
    assert result.supplier_summaries == ()
    assert result.supplier_product_comparisons == ()
    assert result.product_price_comparisons == ()
    assert result.data_quality.examined_lines == 0
    assert result.data_quality.analytics_eligible_lines == 0
    assert result.data_quality.matched_supplier_lines == 0


def test_02_no_supplier_filter_includes_all_suppliers():
    l1 = make_prepared_line(event_id=1, line_id=1, supplier_id=20)
    l2 = make_prepared_line(event_id=2, line_id=2, supplier_id=21)

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l1, l2],
    )

    assert result.sufficiency == ReceivingSupplierComparativeDataSufficiency.AVAILABLE
    assert len(result.observations) == 2
    assert len(result.supplier_summaries) == 2
    assert [s.supplier_id for s in result.supplier_summaries] == [20, 21]


def test_03_supplier_filter_with_tuple_subset():
    l1 = make_prepared_line(event_id=1, line_id=1, supplier_id=20)
    l2 = make_prepared_line(event_id=2, line_id=2, supplier_id=21)
    l3 = make_prepared_line(event_id=3, line_id=3, supplier_id=22)

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(supplier_ids=(20, 22)),
        records=[l1, l2, l3],
    )

    assert len(result.observations) == 2
    assert [s.supplier_id for s in result.supplier_summaries] == [20, 22]


def test_04_single_supplier_metrics():
    l1 = make_prepared_line(
        event_id=1,
        line_id=101,
        supplier_id=20,
        supplier_name="Alpha",
        product_id=200,
        quantity=Decimal("50.00"),
        unit_price=Decimal("10.00"),
        subtotal=Decimal("500.00"),
        event_date=date(2026, 3, 10),
    )
    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(supplier_ids=(20,)),
        records=[l1],
    )

    assert len(result.supplier_summaries) == 1
    s = result.supplier_summaries[0]
    assert s.supplier_id == 20
    assert s.supplier_name == "Alpha"
    assert s.observation_count == 1
    assert s.distinct_event_count == 1
    assert s.distinct_product_count == 1
    assert s.distinct_category_count == 1
    assert s.distinct_receiving_date_count == 1
    assert s.total_quantity == Decimal("50.00")
    assert s.total_spend == Decimal("500.00")
    assert s.weighted_average_unit_price == Decimal("10.00")
    assert s.arithmetic_average_unit_price == Decimal("10.00")
    assert s.min_unit_price == Decimal("10.00")
    assert s.max_unit_price == Decimal("10.00")
    assert s.price_spread == Decimal("0.00")
    assert s.first_receiving_date == date(2026, 3, 10)
    assert s.latest_receiving_date == date(2026, 3, 10)
    assert s.average_days_between_receipts is None


def test_05_supplier_summary_distinct_counts_and_frequency():
    # 3 distinct dates for supplier 20: Mar 1, Mar 11, Mar 21 (span 20d, intervals 2 -> 10d)
    l1 = make_prepared_line(event_id=1, line_id=1, supplier_id=20, product_id=201, category_id=50, event_date=date(2026, 3, 1))
    l2 = make_prepared_line(event_id=2, line_id=2, supplier_id=20, product_id=202, category_id=51, event_date=date(2026, 3, 11))
    l3 = make_prepared_line(event_id=3, line_id=3, supplier_id=20, product_id=201, category_id=50, event_date=date(2026, 3, 21))
    l4 = make_prepared_line(event_id=4, line_id=4, supplier_id=20, product_id=202, category_id=51, event_date=date(2026, 3, 21))  # duplicate date

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l1, l2, l3, l4],
    )

    s = result.supplier_summaries[0]
    assert s.distinct_event_count == 4
    assert s.distinct_product_count == 2
    assert s.distinct_category_count == 2
    assert s.distinct_receiving_date_count == 3
    assert s.average_days_between_receipts == Decimal("10")


def test_06_supplier_product_comparison_latest_price_and_tie_break():
    # Same supplier, product, unit across 2 dates
    l1 = make_prepared_line(event_id=1, line_id=1, supplier_id=20, product_id=200, unit_id=300, event_date=date(2026, 1, 1), unit_price=Decimal("10"))
    l2 = make_prepared_line(event_id=2, line_id=2, supplier_id=20, product_id=200, unit_id=300, event_date=date(2026, 1, 2), unit_price=Decimal("15"))
    l3 = make_prepared_line(event_id=3, line_id=10, line_number=1, supplier_id=20, product_id=200, unit_id=300, event_date=date(2026, 1, 2), unit_price=Decimal("18"))

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l1, l2, l3],
    )

    sp = result.supplier_product_comparisons[0]
    assert sp.latest_price == Decimal("18")
    assert sp.first_receiving_date == date(2026, 1, 1)
    assert sp.latest_receiving_date == date(2026, 1, 2)


def test_07_cross_supplier_price_comparison_two_suppliers():
    # Product 200, Unit 300:
    # Supplier 20: 100 qty @ $10 = 1000 (weighted avg = 10)
    # Supplier 21: 50 qty @ $20 = 1000 (weighted avg = 20)
    l1 = make_prepared_line(event_id=1, line_id=1, supplier_id=20, supplier_name="Alpha", product_id=200, unit_id=300, quantity=Decimal("100"), unit_price=Decimal("10"), subtotal=Decimal("1000"))
    l2 = make_prepared_line(event_id=2, line_id=2, supplier_id=21, supplier_name="Beta", product_id=200, unit_id=300, quantity=Decimal("50"), unit_price=Decimal("20"), subtotal=Decimal("1000"))

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l1, l2],
    )

    assert len(result.product_price_comparisons) == 1
    pc = result.product_price_comparisons[0]
    assert pc.product_id == 200
    assert pc.unit_id == 300
    assert pc.supplier_count == 2
    assert pc.lowest_weighted_average_price == Decimal("10")
    assert pc.highest_weighted_average_price == Decimal("20")
    assert pc.price_spread == Decimal("10")
    assert pc.lowest_price_supplier_id == 20
    assert pc.lowest_price_supplier_name == "Alpha"
    assert pc.highest_price_supplier_id == 21
    assert pc.highest_price_supplier_name == "Beta"

    # Supplier Product Comparisons positions & price difference vs lowest
    assert len(result.supplier_product_comparisons) == 2
    sp_alpha = result.supplier_product_comparisons[0]
    sp_beta = result.supplier_product_comparisons[1]

    assert sp_alpha.supplier_id == 20
    assert sp_alpha.price_position == SupplierPricePosition.LOWEST
    assert sp_alpha.price_difference_vs_lowest == Decimal("0")
    assert sp_alpha.price_difference_percentage_vs_lowest == Decimal("0")

    assert sp_beta.supplier_id == 21
    assert sp_beta.price_position == SupplierPricePosition.HIGHEST
    assert sp_beta.price_difference_vs_lowest == Decimal("10")
    assert sp_beta.price_difference_percentage_vs_lowest == Decimal("100")


def test_08_cross_supplier_price_comparison_three_suppliers_above_lowest():
    # Supplier 20: $10 (lowest)
    # Supplier 21: $15 (above lowest)
    # Supplier 22: $20 (highest)
    l1 = make_prepared_line(event_id=1, line_id=1, supplier_id=20, product_id=200, unit_id=300, quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100"))
    l2 = make_prepared_line(event_id=2, line_id=2, supplier_id=21, product_id=200, unit_id=300, quantity=Decimal("10"), unit_price=Decimal("15"), subtotal=Decimal("150"))
    l3 = make_prepared_line(event_id=3, line_id=3, supplier_id=22, product_id=200, unit_id=300, quantity=Decimal("10"), unit_price=Decimal("20"), subtotal=Decimal("200"))

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l1, l2, l3],
    )

    sp20, sp21, sp22 = result.supplier_product_comparisons
    assert sp20.price_position == SupplierPricePosition.LOWEST
    assert sp21.price_position == SupplierPricePosition.ABOVE_LOWEST
    assert sp22.price_position == SupplierPricePosition.HIGHEST

    assert sp21.price_difference_vs_lowest == Decimal("5")
    assert sp21.price_difference_percentage_vs_lowest == Decimal("50")


def test_09_equal_supplier_prices_and_deterministic_tie():
    # Suppliers 21 and 20 both at $10
    l1 = make_prepared_line(event_id=1, line_id=1, supplier_id=21, supplier_name="Beta", product_id=200, unit_id=300, quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100"))
    l2 = make_prepared_line(event_id=2, line_id=2, supplier_id=20, supplier_name="Alpha", product_id=200, unit_id=300, quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100"))

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l1, l2],
    )

    pc = result.product_price_comparisons[0]
    assert pc.lowest_weighted_average_price == Decimal("10")
    assert pc.highest_weighted_average_price == Decimal("10")
    assert pc.price_spread == Decimal("0")
    # Tie broken by supplier_id ASC (20 is Alpha)
    assert pc.lowest_price_supplier_id == 20
    assert pc.lowest_price_supplier_name == "Alpha"
    assert pc.highest_price_supplier_id == 20
    assert pc.highest_price_supplier_name == "Alpha"

    for sp in result.supplier_product_comparisons:
        assert sp.price_position == SupplierPricePosition.LOWEST


def test_10_same_product_different_units_separated():
    # Product 200 in kg (unit 300) vs L (unit 301)
    l_kg = make_prepared_line(event_id=1, line_id=1, supplier_id=20, product_id=200, unit_id=300, unit_name="kg", unit_price=Decimal("10"))
    l_l = make_prepared_line(event_id=2, line_id=2, supplier_id=21, product_id=200, unit_id=301, unit_name="L", unit_price=Decimal("20"))

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l_kg, l_l],
    )

    # 2 separate comparisons
    assert len(result.product_price_comparisons) == 2
    assert result.product_price_comparisons[0].unit_id == 300
    assert result.product_price_comparisons[1].unit_id == 301


def test_11_zero_lowest_price_percentage_is_none():
    l_zero = make_prepared_line(event_id=1, line_id=1, supplier_id=20, product_id=200, unit_id=300, quantity=Decimal("10"), unit_price=Decimal("0"), subtotal=Decimal("0"))
    l_pos = make_prepared_line(event_id=2, line_id=2, supplier_id=21, product_id=200, unit_id=300, quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100"))

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l_zero, l_pos],
    )

    sp_pos = result.supplier_product_comparisons[1]
    assert sp_pos.price_difference_vs_lowest == Decimal("10")
    assert sp_pos.price_difference_percentage_vs_lowest is None


def test_12_exact_filters_product_category_unit_company_warehouse_dates_ref():
    target = make_prepared_line(
        event_id=1,
        line_id=101,
        supplier_id=20,
        product_id=200,
        category_id=50,
        unit_id=300,
        company_id=10,
        warehouse_id=30,
        event_date=date(2026, 3, 15),
        receiving_reference="REC-TARGET",
    )
    other = make_prepared_line(
        event_id=2,
        line_id=102,
        supplier_id=20,
        product_id=200,
        category_id=50,
        unit_id=300,
        company_id=99,
        warehouse_id=30,
        event_date=date(2026, 3, 15),
        receiving_reference="REC-TARGET",
    )

    req = ReceivingSupplierComparisonRequest(
        product_id=200,
        category_id=50,
        unit_id=300,
        company_id=10,
        warehouse_id=30,
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
        reference="REC-TARGET",
    )
    result = analyze_receiving_supplier_comparison(req, records=[target, other])

    assert len(result.observations) == 1
    assert result.observations[0].line_id == 101


def test_13_data_quality_and_missing_counters():
    l_valid = make_prepared_line(event_id=1, line_id=1, eligible=True)
    l_ineligible = make_prepared_line(event_id=2, line_id=2, eligible=False)
    l_missing_sup = make_prepared_line(
        event_id=3,
        line_id=3,
        supplier_id=None,  # type: ignore[arg-type]
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=True,
            has_product=True,
            has_quantity=True,
            has_unit_price=True,
            has_supplier=False,
            has_warehouse=True,
        ),
    )
    l_missing_cat = make_prepared_line(event_id=4, line_id=4, category_id=None)
    l_missing_unit = make_prepared_line(
        event_id=5,
        line_id=5,
        unit_id=None,
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=True,
            has_product=True,
            has_quantity=True,
            has_unit_price=True,
            has_supplier=True,
            has_warehouse=True,
        ),
    )

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l_valid, l_ineligible, l_missing_sup, l_missing_cat, l_missing_unit],
    )

    assert result.data_quality.examined_lines == 5
    assert result.data_quality.analytics_eligible_lines == 3  # l_valid + l_missing_cat + l_missing_unit
    assert result.data_quality.matched_supplier_lines == 1
    assert result.data_quality.missing_supplier_count == 1
    assert result.data_quality.missing_category_count == 1
    assert result.data_quality.missing_unit_count == 1


def test_14_duplicate_lines_preservation():
    l1 = make_prepared_line(event_id=1, line_id=101, line_number=1, quantity=Decimal("10"), subtotal=Decimal("100"))
    l2 = make_prepared_line(event_id=1, line_id=102, line_number=1, quantity=Decimal("10"), subtotal=Decimal("100"))

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l1, l2],
    )

    assert len(result.observations) == 2
    s = result.supplier_summaries[0]
    assert s.observation_count == 2
    assert s.total_quantity == Decimal("20")
    assert s.total_spend == Decimal("200")


def test_15_decimal_precision():
    q1 = Decimal("123.456789")
    p1 = Decimal("98.765432")
    s1 = q1 * p1
    line = make_prepared_line(quantity=q1, unit_price=p1, subtotal=s1)

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[line],
    )

    s = result.supplier_summaries[0]
    assert isinstance(s.total_quantity, Decimal)
    assert isinstance(s.total_spend, Decimal)
    assert isinstance(s.weighted_average_unit_price, Decimal)
    assert s.total_quantity == q1
    assert s.total_spend == s1


def test_16_immutability_and_input_non_mutation():
    line = make_prepared_line()
    orig_qty = line.quantity
    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[line],
    )

    assert line.quantity == orig_qty
    with pytest.raises(FrozenInstanceError):
        result.supplier_summaries[0].observation_count = 999  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        result.product_price_comparisons[0].supplier_count = 999  # type: ignore[misc]


def test_17_deterministic_ordering_all_collections():
    l1 = make_prepared_line(event_id=2, line_id=20, line_number=1, supplier_id=22, product_id=205, unit_id=300, event_date=date(2026, 3, 2))
    l2 = make_prepared_line(event_id=1, line_id=10, line_number=2, supplier_id=21, product_id=201, unit_id=302, event_date=date(2026, 3, 1))
    l3 = make_prepared_line(event_id=1, line_id=11, line_number=1, supplier_id=21, product_id=201, unit_id=301, event_date=date(2026, 3, 1))

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l1, l2, l3],
    )

    # Observations sorted by (event_date, event_id, line_number, line_id)
    assert [obs.line_id for obs in result.observations] == [11, 10, 20]

    # Supplier summaries sorted by supplier_id ASC
    assert [s.supplier_id for s in result.supplier_summaries] == [21, 22]

    # Product price comparisons sorted by (product_id ASC, unit_id ASC)
    assert [(p.product_id, p.unit_id) for p in result.product_price_comparisons] == [(201, 301), (201, 302), (205, 300)]


def test_18_read_only_and_no_domain_crossing():
    line = make_prepared_line()
    service = ReceivingSupplierComparativeIntelligence()
    res = service.analyze(ReceivingSupplierComparisonRequest(), records=[line])
    assert len(res.supplier_summaries) == 1
    assert isinstance(res.observations, tuple)
    assert isinstance(res.supplier_summaries, tuple)
    assert isinstance(res.supplier_product_comparisons, tuple)
    assert isinstance(res.product_price_comparisons, tuple)


def test_19_single_date_frequency_returns_none():
    l1 = make_prepared_line(event_id=1, line_id=1, supplier_id=20, event_date=date(2026, 3, 1))
    l2 = make_prepared_line(event_id=2, line_id=2, supplier_id=20, event_date=date(2026, 3, 1))

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l1, l2],
    )

    s = result.supplier_summaries[0]
    assert s.distinct_receiving_date_count == 1
    assert s.average_days_between_receipts is None


def test_20_missing_product_and_quantity_and_price_counters():
    l_missing_prod = make_prepared_line(
        event_id=1,
        line_id=1,
        product_id=None,  # type: ignore[arg-type]
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=True,
            has_product=False,
            has_quantity=True,
            has_unit_price=True,
            has_supplier=True,
            has_warehouse=True,
        ),
    )
    l_missing_date = make_prepared_line(
        event_id=2,
        line_id=2,
        event_date=None,
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=False,
            has_product=True,
            has_quantity=True,
            has_unit_price=True,
            has_supplier=True,
            has_warehouse=True,
        ),
    )
    l_missing_price = make_prepared_line(
        event_id=3,
        line_id=3,
        unit_price=None,  # type: ignore[arg-type]
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=True,
            has_product=True,
            has_quantity=True,
            has_unit_price=False,
            has_supplier=True,
            has_warehouse=True,
        ),
    )
    l_missing_qty = make_prepared_line(
        event_id=4,
        line_id=4,
        quantity=None,  # type: ignore[arg-type]
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=True,
            has_product=True,
            has_quantity=False,
            has_unit_price=True,
            has_supplier=True,
            has_warehouse=True,
        ),
    )

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(),
        records=[l_missing_prod, l_missing_date, l_missing_price, l_missing_qty],
    )

    assert result.data_quality.missing_product_count == 1
    assert result.data_quality.missing_date_count == 1
    assert result.data_quality.missing_price_count == 1
    assert result.data_quality.missing_quantity_count == 1
    assert result.data_quality.matched_supplier_lines == 0


def test_21_empty_supplier_scope_matches_nothing():
    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(supplier_ids=()),
        records=[make_prepared_line()],
    )

    assert result.observations == ()
    assert result.data_quality.examined_lines == 1
    assert result.data_quality.matched_supplier_lines == 0


def test_22_architecture_requires_explicit_records_and_has_no_database_dependencies():
    import app.services.receiving_supplier_comparative_intelligence as module

    source = inspect.getsource(module)
    signature = inspect.signature(ReceivingSupplierComparativeIntelligence.analyze)

    assert "Session" not in source
    assert "SessionLocal" not in source
    assert "ReceivingEventQueryService" not in source
    assert "ReceivingEventAnalyticsPreparation" not in source
    assert signature.parameters["records"].default is inspect.Parameter.empty


def test_23_reference_normalization_and_inclusive_date_boundaries():
    line = make_prepared_line(
        event_date=date(2026, 3, 15),
        receiving_reference="  Rec   Target ",
    )
    request = ReceivingSupplierComparisonRequest(
        date_from=date(2026, 3, 15),
        date_to=date(2026, 3, 15),
        reference="rec target",
    )

    result = analyze_receiving_supplier_comparison(request, records=[line])

    assert result.data_quality.matched_supplier_lines == 1
    assert len(result.observations) == 1


@pytest.mark.parametrize(
    "field,value,expected_field",
    [
        ("supplier_id", None, "missing_supplier_count"),
        ("supplier_id", 0, "missing_supplier_count"),
        ("product_id", None, "missing_product_count"),
        ("product_id", 0, "missing_product_count"),
        ("category_id", None, "missing_category_count"),
        ("category_id", 0, "missing_category_count"),
        ("unit_id", None, "missing_unit_count"),
        ("unit_id", 0, "missing_unit_count"),
        ("quantity", None, "missing_quantity_count"),
        ("quantity", Decimal("0"), "missing_quantity_count"),
        ("unit_price", None, "missing_price_count"),
        ("unit_price", Decimal("-1"), "missing_price_count"),
    ],
)
def test_24_raw_invalid_values_are_counted_and_excluded(
    field, value, expected_field
):
    line = make_prepared_line(**{field: value})
    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(), records=[line]
    )

    assert getattr(result.data_quality, expected_field) == 1
    assert result.data_quality.matched_supplier_lines == 0


def test_25_missing_counters_are_independent_and_ignore_filters():
    missing_product = make_prepared_line(product_id=0, supplier_id=20)
    missing_category = make_prepared_line(category_id=0, supplier_id=21)
    filtered_out = make_prepared_line(
        supplier_id=22, product_id=0, company_id=99
    )

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(company_id=10),
        records=[missing_product, missing_category, filtered_out],
    )

    assert result.data_quality.examined_lines == 3
    assert result.data_quality.missing_product_count == 2
    assert result.data_quality.missing_category_count == 1
    assert result.data_quality.matched_supplier_lines == 0


def test_26_tied_lowest_and_highest_use_supplier_id_for_selection():
    records = [
        make_prepared_line(supplier_id=30, unit_price=Decimal("10"), subtotal=Decimal("100")),
        make_prepared_line(event_id=2, line_id=102, supplier_id=20, unit_price=Decimal("10"), subtotal=Decimal("100")),
        make_prepared_line(event_id=3, line_id=103, supplier_id=40, unit_price=Decimal("20"), subtotal=Decimal("200")),
        make_prepared_line(event_id=4, line_id=104, supplier_id=35, unit_price=Decimal("20"), subtotal=Decimal("200")),
    ]

    result = analyze_receiving_supplier_comparison(
        ReceivingSupplierComparisonRequest(), records=records
    )

    comparison = result.product_price_comparisons[0]
    assert comparison.lowest_price_supplier_id == 20
    assert comparison.highest_price_supplier_id == 35
    positions = {
        item.supplier_id: item.price_position
        for item in result.supplier_product_comparisons
    }
    assert positions[20] == SupplierPricePosition.LOWEST
    assert positions[30] == SupplierPricePosition.LOWEST
    assert positions[35] == SupplierPricePosition.HIGHEST
    assert positions[40] == SupplierPricePosition.HIGHEST


def test_27_observation_preserves_complete_provenance_and_outputs_are_frozen():
    line = make_prepared_line(
        event_id=7,
        line_id=8,
        line_number=9,
        source_file="source.xlsx",
        source_sheet="Receiving",
        source_row=11,
    )
    request = ReceivingSupplierComparisonRequest()
    result = analyze_receiving_supplier_comparison(request, records=[line])
    observation = result.observations[0]

    assert observation.event_id == 7
    assert observation.line_id == 8
    assert observation.line_number == 9
    assert observation.source_file == "source.xlsx"
    assert observation.source_sheet == "Receiving"
    assert observation.source_row == 11
    assert observation.quantity == line.quantity
    assert observation.unit_price == line.unit_price
    assert observation.subtotal == line.subtotal
    assert observation.receiving_reference == line.receiving_reference

    with pytest.raises(FrozenInstanceError):
        request.reference = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        observation.line_id = 99  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.sufficiency = ReceivingSupplierComparativeDataSufficiency.AVAILABLE  # type: ignore[misc]
