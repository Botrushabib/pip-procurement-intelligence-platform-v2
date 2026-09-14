from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any, Iterable

from app.services.receiving_event_mapping_decision import (
    ReceivingDecisionStatus,
    ReceivingEventMappingDecision,
    ReceivingEventMappingDecisionEngine,
)
from app.services.receiving_event_mapping_result import (
    CompanyCandidate,
    CompanyMetadata,
    MasterDataMappingResult,
    ProductCandidate,
    ReceivingEventLineMappingResult,
    ReceivingEventMappingResult,
    ReceivingEventMappingSummary,
    ReceivingMappingMethod,
    ReceivingMappingStatus,
    SupplierCandidate,
    UnitCandidate,
    WarehouseCandidate,
)
from app.services.receiving_event_reader import ReceivingRowClassification, ReceivingSourceRow
from app.services.receiving_event_validation_result import ReceivingValidationResult


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.strip()).lower()


def _comparison_code(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _meaningful(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


class ReceivingEventMappingEngine:
    def map(
        self,
        validation_result: ReceivingValidationResult,
        *,
        company_metadata: CompanyMetadata,
        suppliers: Iterable[SupplierCandidate] = (),
        products: Iterable[ProductCandidate] = (),
        units: Iterable[UnitCandidate] = (),
        warehouses: Iterable[WarehouseCandidate] = (),
        companies: Iterable[CompanyCandidate] = (),
    ) -> ReceivingEventMappingResult:
        suppliers, products, units, warehouses, companies = (
            tuple(suppliers), tuple(products), tuple(units), tuple(warehouses), tuple(companies)
        )
        eligible_rows = set(validation_result.eligible_detail_rows)
        validation_codes = self._validation_codes(validation_result)
        line_results: list[ReceivingEventLineMappingResult] = []
        decisions: list[ReceivingEventMappingDecision] = []
        decision_engine = ReceivingEventMappingDecisionEngine()

        for row in validation_result.rows:
            eligible = row in eligible_rows
            line_result = self._map_row(
                row,
                company_metadata=company_metadata,
                suppliers=suppliers,
                products=products,
                units=units,
                warehouses=warehouses,
                companies=companies,
                attempted=eligible,
            )
            line_results.append(line_result)
            decisions.append(
                decision_engine.decide(
                    line_result,
                    validation_blocked=(
                        row.row_classification is ReceivingRowClassification.DETAIL and not eligible
                    ),
                    non_detail=row.row_classification is not ReceivingRowClassification.DETAIL,
                    validation_reason_codes=validation_codes.get(row.source_row, ()),
                )
            )

        conflict_rows = self._document_conflict_rows(line_results, decisions)
        decisions = [
            decision_engine.decide(
                line_result,
                validation_blocked=(
                    line_result.row.row_classification is ReceivingRowClassification.DETAIL
                    and line_result.row not in eligible_rows
                ),
                non_detail=line_result.row.row_classification is not ReceivingRowClassification.DETAIL,
                validation_reason_codes=validation_codes.get(line_result.source_row, ()),
                grouping_conflict=line_result.source_row in conflict_rows,
            )
            for line_result in line_results
        ]
        summary = ReceivingEventMappingSummary(
            total_row_count=len(line_results),
            eligible_detail_row_count=len(validation_result.eligible_detail_rows),
            ready_count=sum(d.decision_status is ReceivingDecisionStatus.READY for d in decisions),
            review_count=sum(d.decision_status is ReceivingDecisionStatus.REVIEW for d in decisions),
            rejected_count=sum(d.decision_status is ReceivingDecisionStatus.REJECTED for d in decisions),
        )
        return ReceivingEventMappingResult(
            line_results=tuple(line_results),
            decisions=tuple(decisions),
            preserved_rows=tuple(row for row in validation_result.rows if row not in eligible_rows),
            summary=summary,
        )

    def _map_row(self, row: ReceivingSourceRow, *, company_metadata: CompanyMetadata, suppliers: tuple[SupplierCandidate, ...], products: tuple[ProductCandidate, ...], units: tuple[UnitCandidate, ...], warehouses: tuple[WarehouseCandidate, ...], companies: tuple[CompanyCandidate, ...], attempted: bool) -> ReceivingEventLineMappingResult:
        if not attempted:
            not_attempted = self._not_attempted()
            return ReceivingEventLineMappingResult(row, company_metadata, not_attempted, not_attempted, not_attempted, not_attempted, not_attempted, None, None, "Mapping was not attempted because Stage 2 did not make this row eligible", row.raw_reference, None)
        company = self._map_field(company_metadata.company_code, companies, "code", ReceivingMappingMethod.COMPANY_CODE_EXACT, "company_metadata.company_code", "Company")
        supplier = self._map_field(row.raw_supplier, suppliers, "name", ReceivingMappingMethod.SUPPLIER_NAME_EXACT, "raw_supplier", "Supplier")
        product = self._map_product(row, products)
        unit = self._map_field(row.raw_unit, units, "name", ReceivingMappingMethod.UNIT_NAME_EXACT, "raw_unit", "Unit")
        warehouse = self._map_field(row.raw_destination, warehouses, "name", ReceivingMappingMethod.WAREHOUSE_NAME_EXACT, "raw_destination", "Warehouse")
        event_date, event_date_method, event_date_reason = self._map_event_date(row.event_date_candidate)
        grouping_key = None
        if all(item.normalized_id is not None for item in (company, supplier, warehouse)) and event_date is not None and _meaningful(row.raw_reference):
            grouping_key = (company.normalized_id, supplier.normalized_id, warehouse.normalized_id, event_date, str(row.raw_reference))
        return ReceivingEventLineMappingResult(row, company_metadata, company, supplier, product, unit, warehouse, event_date, event_date_method, event_date_reason, row.raw_reference, grouping_key)

    @staticmethod
    def _not_attempted() -> MasterDataMappingResult:
        return MasterDataMappingResult(ReceivingMappingStatus.NOT_ATTEMPTED, None, None, None, None, (), (), "Mapping was not attempted")

    def _map_product(self, row: ReceivingSourceRow, products: tuple[ProductCandidate, ...]) -> MasterDataMappingResult:
        if not _meaningful(row.product_code):
            return MasterDataMappingResult(ReceivingMappingStatus.UNMAPPED, None, None, "product_code", row.product_code, (), (), "Product code is missing or invalid; no fallback is permitted")
        return self._map_field(row.product_code, products, "code", ReceivingMappingMethod.PRODUCT_CODE_EXACT, "product_code", "Product", code_comparison=True)

    def _map_field(self, raw_value: Any, candidates: Iterable[Any], attribute: str, method: ReceivingMappingMethod, source_field: str, label: str, *, code_comparison: bool = False) -> MasterDataMappingResult:
        if not _meaningful(raw_value):
            return MasterDataMappingResult(ReceivingMappingStatus.UNMAPPED, None, None, source_field, raw_value, (), (), f"{label} source value is missing")
        compare = _comparison_code if code_comparison else _normalize_text
        matches = [candidate for candidate in candidates if getattr(candidate, attribute) is not None and compare(getattr(candidate, attribute)) == compare(raw_value)]
        matches = sorted(matches, key=lambda candidate: candidate.id)
        ids = tuple(candidate.id for candidate in matches)
        names = tuple(getattr(candidate, attribute) for candidate in matches)
        if len(matches) == 1:
            return MasterDataMappingResult(ReceivingMappingStatus.MAPPED, matches[0].id, method, source_field, raw_value, ids, names, f"Exact {label} match")
        if len(matches) > 1:
            return MasterDataMappingResult(ReceivingMappingStatus.AMBIGUOUS, None, None, source_field, raw_value, ids, names, f"Multiple {label} candidates match exactly")
        return MasterDataMappingResult(ReceivingMappingStatus.UNMAPPED, None, None, source_field, raw_value, (), (), f"No {label} candidate matches exactly")

    @staticmethod
    def _map_event_date(value: Any) -> tuple[date | None, ReceivingMappingMethod | None, str]:
        if isinstance(value, datetime):
            return value.date(), ReceivingMappingMethod.EVENT_DATE_APPROVED_DATE_COLUMN, "Mapped from approved Date column"
        if isinstance(value, date):
            return value, ReceivingMappingMethod.EVENT_DATE_APPROVED_DATE_COLUMN, "Mapped from approved Date column"
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip()), ReceivingMappingMethod.EVENT_DATE_APPROVED_DATE_COLUMN, "Mapped from approved Date column"
            except ValueError:
                pass
        return None, None, "Approved Date column is missing or invalid"

    @staticmethod
    def _validation_codes(validation_result: ReceivingValidationResult) -> dict[int, tuple[str, ...]]:
        result: dict[int, list[str]] = {}
        for issue in validation_result.issues:
            result.setdefault(issue.source_row, []).append(issue.code)
        return {source_row: tuple(codes) for source_row, codes in result.items()}

    @staticmethod
    def _document_conflict_rows(line_results: list[ReceivingEventLineMappingResult], decisions: list[ReceivingEventMappingDecision]) -> set[int]:
        groups: dict[tuple[str, str, str], list[ReceivingEventLineMappingResult]] = {}
        for line_result, decision in zip(line_results, decisions):
            if (
                decision.decision_status is ReceivingDecisionStatus.REJECTED
                or line_result.event_grouping_key is None
            ):
                continue
            key = (line_result.source_file, line_result.source_sheet, str(line_result.receiving_reference))
            groups.setdefault(key, []).append(line_result)
        conflicts: set[int] = set()
        for rows in groups.values():
            signatures = {
                (row.company.normalized_id, row.supplier.normalized_id, row.warehouse.normalized_id, row.event_date)
                for row in rows
            }
            if len(signatures) > 1:
                conflicts.update(row.source_row for row in rows)
        return conflicts


map_receiving_events = ReceivingEventMappingEngine().map

__all__ = ["ReceivingEventMappingEngine", "map_receiving_events"]