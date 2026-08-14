from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Iterable

from app.services.excel_reader import RawPurchaseTransactionRecord
from app.services.validation_engine import ValidationResult


class MappingStatus(str, Enum):
    MAPPED = "MAPPED"
    UNMAPPED = "UNMAPPED"
    AMBIGUOUS = "AMBIGUOUS"


BRANCH = "BRANCH"
WAREHOUSE = "WAREHOUSE"
SUB_WAREHOUSE = "SUB_WAREHOUSE"


@dataclass(frozen=True)
class MappingCandidate:
    name: str
    id: int


@dataclass(frozen=True)
class DestinationCandidate:
    destination_name: str
    destination_type: str
    branch_id: int | None = None
    warehouse_id: int | None = None
    sub_warehouse_name: str | None = None


@dataclass(frozen=True)
class FieldMapping:
    status: MappingStatus
    resolved_id: int | None = None


@dataclass(frozen=True)
class DestinationMapping:
    status: MappingStatus
    branch_id: int | None = None
    warehouse_id: int | None = None
    sub_warehouse_name: str | None = None


@dataclass(frozen=True)
class MappedPurchaseTransaction:
    validation_result: ValidationResult
    raw_record: RawPurchaseTransactionRecord
    supplier: FieldMapping
    product: FieldMapping
    unit: FieldMapping
    destination: DestinationMapping
    status: MappingStatus

    @property
    def mapping_status(self) -> MappingStatus:
        return self.status

    @property
    def fully_mapped(self) -> bool:
        return self.status is MappingStatus.MAPPED

    @property
    def source_file(self) -> str:
        return self.raw_record.source_file

    @property
    def source_sheet(self) -> str:
        return self.raw_record.source_sheet

    @property
    def source_row(self) -> int:
        return self.raw_record.source_row


def _normalize(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.strip()).lower()


def _candidate_name(candidate: Any) -> Any:
    if isinstance(candidate, dict):
        return candidate.get("name", candidate.get("code"))
    return getattr(candidate, "name", getattr(candidate, "code", None))


def _candidate_id(candidate: Any) -> int | None:
    if isinstance(candidate, dict):
        return candidate.get("id")
    return getattr(candidate, "id", None)


def _field_mapping(raw_value: Any, candidates: Iterable[Any]) -> FieldMapping:
    matches = [
        candidate
        for candidate in candidates
        if _normalize(_candidate_name(candidate)) == _normalize(raw_value)
        and _candidate_id(candidate) is not None
    ]
    if len(matches) == 1:
        return FieldMapping(MappingStatus.MAPPED, _candidate_id(matches[0]))
    if len(matches) > 1:
        return FieldMapping(MappingStatus.AMBIGUOUS)
    return FieldMapping(MappingStatus.UNMAPPED)


def _destination_mapping(
    raw_value: Any,
    candidates: Iterable[DestinationCandidate],
) -> DestinationMapping:
    matches = [
        candidate
        for candidate in candidates
        if _normalize(candidate.destination_name) == _normalize(raw_value)
    ]
    valid_matches = []
    for candidate in matches:
        if candidate.destination_type == BRANCH and candidate.branch_id is not None:
            valid_matches.append(candidate)
        elif (
            candidate.destination_type == WAREHOUSE
            and candidate.warehouse_id is not None
        ):
            valid_matches.append(candidate)
        elif (
            candidate.destination_type == SUB_WAREHOUSE
            and candidate.warehouse_id is not None
            and _normalize(candidate.sub_warehouse_name)
        ):
            valid_matches.append(candidate)

    if len(valid_matches) != 1:
        status = MappingStatus.AMBIGUOUS if len(valid_matches) > 1 else MappingStatus.UNMAPPED
        return DestinationMapping(status)

    candidate = valid_matches[0]
    if candidate.destination_type == BRANCH:
        return DestinationMapping(MappingStatus.MAPPED, branch_id=candidate.branch_id)
    if candidate.destination_type == WAREHOUSE:
        return DestinationMapping(MappingStatus.MAPPED, warehouse_id=candidate.warehouse_id)
    if candidate.destination_type == SUB_WAREHOUSE:
        return DestinationMapping(
            MappingStatus.MAPPED,
            warehouse_id=candidate.warehouse_id,
            sub_warehouse_name=candidate.sub_warehouse_name,
        )
    return DestinationMapping(MappingStatus.UNMAPPED)


class MappingEngine:
    def map(
        self,
        validation_result: ValidationResult,
        *,
        suppliers: Iterable[Any] = (),
        products: Iterable[Any] = (),
        units: Iterable[Any] = (),
        destinations: Iterable[DestinationCandidate] = (),
    ) -> MappedPurchaseTransaction:
        raw_record = validation_result.raw_record
        if not validation_result.valid:
            unmapped = FieldMapping(MappingStatus.UNMAPPED)
            return MappedPurchaseTransaction(
                validation_result=validation_result,
                raw_record=raw_record,
                supplier=unmapped,
                product=unmapped,
                unit=unmapped,
                destination=DestinationMapping(MappingStatus.UNMAPPED),
                status=MappingStatus.UNMAPPED,
            )

        supplier_mapping = _field_mapping(raw_record.supplier_raw, suppliers)
        product_mapping = _field_mapping(raw_record.product_raw, products)
        unit_mapping = _field_mapping(raw_record.unit_raw, units)
        destination_mapping = _destination_mapping(raw_record.destination_raw, destinations)
        mappings = (
            supplier_mapping.status,
            product_mapping.status,
            unit_mapping.status,
            destination_mapping.status,
        )
        status = (
            MappingStatus.MAPPED
            if all(mapping is MappingStatus.MAPPED for mapping in mappings)
            else MappingStatus.AMBIGUOUS
            if any(mapping is MappingStatus.AMBIGUOUS for mapping in mappings)
            else MappingStatus.UNMAPPED
        )
        return MappedPurchaseTransaction(
            validation_result=validation_result,
            raw_record=raw_record,
            supplier=supplier_mapping,
            product=product_mapping,
            unit=unit_mapping,
            destination=destination_mapping,
            status=status,
        )

    map_transaction = map


def map_transaction(
    validation_result: ValidationResult,
    *,
    suppliers: Iterable[Any] = (),
    products: Iterable[Any] = (),
    units: Iterable[Any] = (),
    destinations: Iterable[DestinationCandidate] = (),
) -> MappedPurchaseTransaction:
    return MappingEngine().map(
        validation_result,
        suppliers=suppliers,
        products=products,
        units=units,
        destinations=destinations,
    )