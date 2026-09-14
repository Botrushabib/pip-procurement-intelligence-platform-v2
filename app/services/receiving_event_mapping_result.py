from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

from app.services.receiving_event_reader import ReceivingSourceRow


class ReceivingMappingStatus(str, Enum):
    MAPPED = "MAPPED"
    UNMAPPED = "UNMAPPED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


class ReceivingMappingMethod(str, Enum):
    SUPPLIER_NAME_EXACT = "SUPPLIER_NAME_EXACT"
    PRODUCT_CODE_EXACT = "PRODUCT_CODE_EXACT"
    UNIT_NAME_EXACT = "UNIT_NAME_EXACT"
    WAREHOUSE_NAME_EXACT = "WAREHOUSE_NAME_EXACT"
    COMPANY_CODE_EXACT = "COMPANY_CODE_EXACT"
    EVENT_DATE_APPROVED_DATE_COLUMN = "EVENT_DATE_APPROVED_DATE_COLUMN"


@dataclass(frozen=True)
class CompanyMetadata:
    company_code: Any = None


@dataclass(frozen=True)
class SupplierCandidate:
    id: int
    name: str | None = None


@dataclass(frozen=True)
class ProductCandidate:
    id: int
    code: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class UnitCandidate:
    id: int
    name: str | None = None


@dataclass(frozen=True)
class WarehouseCandidate:
    id: int
    name: str | None = None
    code: str | None = None


@dataclass(frozen=True)
class CompanyCandidate:
    id: int
    code: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class MasterDataMappingResult:
    status: ReceivingMappingStatus
    normalized_id: int | None
    mapping_method: ReceivingMappingMethod | None
    mapping_source_field: str | None
    raw_value: Any
    candidate_ids: tuple[int, ...]
    candidate_names: tuple[str | None, ...]
    reason: str


@dataclass(frozen=True)
class ReceivingEventLineMappingResult:
    row: ReceivingSourceRow
    company_metadata: CompanyMetadata
    company: MasterDataMappingResult
    supplier: MasterDataMappingResult
    product: MasterDataMappingResult
    unit: MasterDataMappingResult
    warehouse: MasterDataMappingResult
    event_date: date | None
    event_date_method: ReceivingMappingMethod | None
    event_date_reason: str
    receiving_reference: Any
    event_grouping_key: tuple[int, int, int, date, str] | None

    @property
    def source_file(self) -> str:
        return self.row.source_file

    @property
    def source_sheet(self) -> str:
        return self.row.source_sheet

    @property
    def source_row(self) -> int:
        return self.row.source_row


@dataclass(frozen=True)
class ReceivingEventMappingSummary:
    total_row_count: int
    eligible_detail_row_count: int
    ready_count: int
    review_count: int
    rejected_count: int


@dataclass(frozen=True)
class ReceivingEventMappingResult:
    line_results: tuple[ReceivingEventLineMappingResult, ...]
    decisions: tuple[Any, ...]
    preserved_rows: tuple[ReceivingSourceRow, ...]
    summary: ReceivingEventMappingSummary


__all__ = [
    "CompanyCandidate",
    "CompanyMetadata",
    "MasterDataMappingResult",
    "ProductCandidate",
    "ReceivingEventLineMappingResult",
    "ReceivingEventMappingResult",
    "ReceivingEventMappingSummary",
    "ReceivingMappingMethod",
    "ReceivingMappingStatus",
    "SupplierCandidate",
    "UnitCandidate",
    "WarehouseCandidate",
]