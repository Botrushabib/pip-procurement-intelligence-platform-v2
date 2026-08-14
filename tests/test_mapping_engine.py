from datetime import datetime
from decimal import Decimal

from app.services.excel_reader import RawPurchaseTransactionRecord
from app.services.mapping_engine import (
    BRANCH,
    SUB_WAREHOUSE,
    WAREHOUSE,
    DestinationCandidate,
    MappingCandidate,
    MappingEngine,
    MappingStatus,
)
from app.services.validation_engine import ValidationEngine


def make_record(**changes):
    values = {
        "source_file": "purchases.xlsx",
        "source_sheet": "Report",
        "source_row": 7,
        "transaction_date": datetime(2026, 1, 15, 10, 30),
        "reference": "PO-001",
        "supplier_raw": "Supplier A",
        "product_raw": "Product A",
        "destination_raw": "Warehouse A",
        "quantity_raw": 2,
        "unit_raw": "Each",
        "unit_price_raw": 10.5,
        "subtotal_raw": Decimal("21.0"),
    }
    values.update(changes)
    return RawPurchaseTransactionRecord(**values)


def validated_record(record=None):
    return ValidationEngine().validate(record or make_record())


def candidates():
    return (
        [MappingCandidate("Supplier A", 1)],
        [MappingCandidate("Product A", 2)],
        [MappingCandidate("Each", 3)],
    )


def destination(destination_type=WAREHOUSE, **changes):
    values = {
        "destination_name": "Warehouse A",
        "destination_type": destination_type,
        "warehouse_id": 4,
    }
    values.update(changes)
    return DestinationCandidate(**values)


def map_valid(record=None, **changes):
    suppliers, products, units = candidates()
    values = {
        "suppliers": suppliers,
        "products": products,
        "units": units,
        "destinations": [destination()],
    }
    values.update(changes)
    return MappingEngine().map(validated_record(record), **values)


def test_invalid_validation_result_cannot_be_successfully_mapped():
    result = MappingEngine().map(ValidationEngine().validate(make_record(quantity_raw="2")))

    assert result.status is MappingStatus.UNMAPPED
    assert result.fully_mapped is False


def test_valid_validation_result_enters_mapping():
    result = map_valid()

    assert result.status is MappingStatus.MAPPED


def test_exact_supplier_product_and_unit_matches_are_mapped():
    result = map_valid()

    assert result.supplier == result.supplier.__class__(MappingStatus.MAPPED, 1)
    assert result.product.resolved_id == 2
    assert result.unit.resolved_id == 3


def test_unmapped_and_ambiguous_entity_matches_are_explicit():
    suppliers, products, units = candidates()
    result = map_valid(suppliers=[MappingCandidate("Other", 1)])
    assert result.supplier.status is MappingStatus.UNMAPPED

    result = map_valid(
        suppliers=suppliers + [MappingCandidate("supplier   a", 9)],
        products=products + [MappingCandidate("product a", 8)],
        units=units + [MappingCandidate("EACH", 7)],
    )
    assert result.supplier.status is MappingStatus.AMBIGUOUS
    assert result.product.status is MappingStatus.AMBIGUOUS
    assert result.unit.status is MappingStatus.AMBIGUOUS


def test_matching_is_normalized_but_not_fuzzy():
    result = map_valid(suppliers=[MappingCandidate("Supplier B", 1)])

    assert result.supplier.status is MappingStatus.UNMAPPED


def test_branch_destination_exposes_branch_id():
    result = map_valid(
        record=make_record(destination_raw="Branch A"),
        destinations=[destination(BRANCH, destination_name="Branch A", warehouse_id=None, branch_id=6)],
    )

    assert result.destination.status is MappingStatus.MAPPED
    assert result.destination.destination_type == BRANCH
    assert result.destination_type == BRANCH
    assert result.destination.branch_id == 6
    assert result.destination.warehouse_id is None
    assert result.destination.sub_warehouse_name is None


def test_warehouse_destination_exposes_warehouse_id():
    result = map_valid()

    assert result.destination.status is MappingStatus.MAPPED
    assert result.destination.destination_type == WAREHOUSE
    assert result.destination_type == WAREHOUSE
    assert result.destination.warehouse_id == 4
    assert result.destination.branch_id is None
    assert result.destination.sub_warehouse_name is None


def test_subwarehouse_destination_exposes_both_typed_values():
    result = map_valid(
        record=make_record(destination_raw="Cold Storage"),
        destinations=[
            destination(
                SUB_WAREHOUSE,
                destination_name="Cold Storage",
                sub_warehouse_name="Cold Storage",
            )
        ],
    )

    assert result.destination.status is MappingStatus.MAPPED
    assert result.destination.destination_type == SUB_WAREHOUSE
    assert result.destination_type == SUB_WAREHOUSE
    assert result.destination.warehouse_id == 4
    assert result.destination.branch_id is None
    assert result.destination.sub_warehouse_name == "Cold Storage"
    assert not hasattr(result.destination, "destination_id")


def test_invalid_subwarehouse_candidates_are_unmapped_without_inference():
    for candidate in [
        destination(SUB_WAREHOUSE, warehouse_id=None),
        destination(SUB_WAREHOUSE, sub_warehouse_name=None),
    ]:
        result = map_valid(destinations=[candidate])
        assert result.destination.status is MappingStatus.UNMAPPED


def test_unmapped_destination_preserves_explicit_candidate_type():
    result = map_valid(
        destinations=[destination(BRANCH, branch_id=None, warehouse_id=None)]
    )

    assert result.destination.status is MappingStatus.UNMAPPED
    assert result.destination.destination_type == BRANCH


def test_ambiguous_destination_preserves_only_unambiguous_type():
    same_type = map_valid(
        destinations=[destination(), destination(WAREHOUSE, warehouse_id=9)]
    )
    mixed_types = map_valid(
        destinations=[
            destination(),
            destination(BRANCH, destination_name="Warehouse A", branch_id=8, warehouse_id=None),
        ]
    )

    assert same_type.destination.status is MappingStatus.AMBIGUOUS
    assert same_type.destination.destination_type == WAREHOUSE
    assert mixed_types.destination.status is MappingStatus.AMBIGUOUS
    assert mixed_types.destination.destination_type is None


def test_destination_type_is_never_inferred_from_ids():
    result = map_valid(
        destinations=[
            DestinationCandidate(
                destination_name="Warehouse A",
                destination_type="UNKNOWN",
                branch_id=6,
                warehouse_id=4,
                sub_warehouse_name="Cold Storage",
            )
        ]
    )

    assert result.destination.status is MappingStatus.UNMAPPED
    assert result.destination.destination_type is None
    assert result.destination.branch_id is None
    assert result.destination.warehouse_id is None
    assert result.destination.sub_warehouse_name is None


def test_destination_type_and_ambiguity_are_preserved():
    result = map_valid(
        destinations=[destination(), destination(WAREHOUSE, warehouse_id=9)]
    )

    assert result.destination.status is MappingStatus.AMBIGUOUS
    assert result.status is MappingStatus.AMBIGUOUS


def test_overall_status_requires_all_four_mappings():
    unmapped = map_valid(units=[MappingCandidate("Box", 3)])
    ambiguous = map_valid(
        suppliers=[MappingCandidate("Supplier A", 1), MappingCandidate("Supplier A", 9)]
    )

    assert unmapped.status is MappingStatus.UNMAPPED
    assert ambiguous.status is MappingStatus.AMBIGUOUS


def test_raw_values_and_traceability_are_preserved():
    record = make_record(
        supplier_raw=" Supplier A ",
        product_raw=" Product A ",
        destination_raw=" Warehouse A ",
        unit_raw=" Each ",
    )
    result = map_valid(record)

    assert result.raw_record is record
    assert result.source_file == "purchases.xlsx"
    assert result.source_sheet == "Report"
    assert result.source_row == 7
    assert result.raw_record.supplier_raw == " Supplier A "
    assert result.raw_record.product_raw == " Product A "
    assert result.raw_record.destination_raw == " Warehouse A "
    assert result.raw_record.unit_raw == " Each "
    assert result.destination_type == WAREHOUSE


def test_inputs_are_not_mutated_and_results_are_deterministic():
    suppliers, products, units = candidates()
    destinations = [destination()]
    result_one = map_valid(suppliers=suppliers, products=products, units=units, destinations=destinations)
    result_two = map_valid(suppliers=suppliers, products=products, units=units, destinations=destinations)

    assert result_one == result_two
    assert suppliers == [MappingCandidate("Supplier A", 1)]
    assert products == [MappingCandidate("Product A", 2)]
    assert units == [MappingCandidate("Each", 3)]
    assert destinations == [destination()]
    assert result_one.destination_type == result_two.destination_type == WAREHOUSE


def test_mapping_module_has_no_database_dependency():
    source = open("app/services/mapping_engine.py").read()

    assert "sqlalchemy" not in source
    assert "Session" not in source
    assert "create_engine" not in source