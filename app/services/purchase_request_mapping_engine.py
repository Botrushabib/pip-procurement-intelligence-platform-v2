from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import re
from typing import Any, Iterable

from app.services.purchase_request_reader import QuantityClassification
from app.services.purchase_request_validation_engine import PurchaseRequestValidationResult


class MappingStatus(str, Enum):
    MAPPED = "MAPPED"
    UNMAPPED = "UNMAPPED"
    AMBIGUOUS = "AMBIGUOUS"


class MappingMethod(str, Enum):
    INTERNAL_REFERENCE_EXACT = "INTERNAL_REFERENCE_EXACT"
    NAME_EXACT = "NAME_EXACT"
    UNIT_NAME_EXACT = "UNIT_NAME_EXACT"


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
class ProductMappingResult:
    status: MappingStatus
    normalized_product_id: int | None
    mapping_method: MappingMethod | None
    mapping_source_field: str | None
    raw_internal_reference: Any
    raw_product: Any
    raw_item_description: Any
    candidate_ids: tuple[int, ...]
    candidate_names: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class UnitMappingResult:
    status: MappingStatus
    normalized_unit_id: int | None
    mapping_method: MappingMethod | None
    mapping_source_field: str | None
    raw_unit: Any
    candidate_ids: tuple[int, ...]
    candidate_names: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class PurchaseRequestMappingResult:
    source_file: str
    source_sheet: str
    source_row: int
    product: ProductMappingResult
    unit: UnitMappingResult
    quantity_classification: QuantityClassification
    quantity_value: Decimal | None
    quantity_token: str | None
    packaging_token: str | None


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.strip()).lower()


def _is_meaningful(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _comparison_key(value: Any) -> str:
    # Approved rule: compare Internal Reference against Product.code using
    # str(value).strip() only. Never parsed/cast numerically, never
    # normalized mathematically (leading zeros are preserved).
    return str(value).strip()


def _sorted_candidates(
    candidates: Iterable[Any],
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    ordered = sorted(candidates, key=lambda candidate: candidate.id)
    ids = tuple(candidate.id for candidate in ordered)
    names = tuple(
        candidate.name if candidate.name is not None else candidate.code
        for candidate in ordered
    )
    return ids, names


class PurchaseRequestMappingEngine:
    def map_product(
        self,
        *,
        raw_internal_reference: Any,
        raw_product: Any,
        raw_item_description: Any,
        products: Iterable[ProductCandidate] = (),
    ) -> ProductMappingResult:
        products = tuple(products)

        internal_reference_present = _is_meaningful(raw_internal_reference)
        name_present = _is_meaningful(raw_product)

        if not internal_reference_present and not name_present:
            return ProductMappingResult(
                status=MappingStatus.UNMAPPED,
                normalized_product_id=None,
                mapping_method=None,
                mapping_source_field=None,
                raw_internal_reference=raw_internal_reference,
                raw_product=raw_product,
                raw_item_description=raw_item_description,
                candidate_ids=(),
                candidate_names=(),
                reason="Neither Internal Reference nor Name is present",
            )

        if internal_reference_present:
            comparison_key = _comparison_key(raw_internal_reference)
            matches = [
                candidate
                for candidate in products
                if candidate.code is not None
                and _comparison_key(candidate.code) == comparison_key
            ]
            if len(matches) == 1:
                return ProductMappingResult(
                    status=MappingStatus.MAPPED,
                    normalized_product_id=matches[0].id,
                    mapping_method=MappingMethod.INTERNAL_REFERENCE_EXACT,
                    mapping_source_field="raw_internal_reference",
                    raw_internal_reference=raw_internal_reference,
                    raw_product=raw_product,
                    raw_item_description=raw_item_description,
                    candidate_ids=(matches[0].id,),
                    candidate_names=(matches[0].code,),
                    reason="Exact Internal Reference to Product.code match",
                )
            if len(matches) > 1:
                candidate_ids, candidate_names = _sorted_candidates(matches)
                return ProductMappingResult(
                    status=MappingStatus.AMBIGUOUS,
                    normalized_product_id=None,
                    mapping_method=None,
                    mapping_source_field="raw_internal_reference",
                    raw_internal_reference=raw_internal_reference,
                    raw_product=raw_product,
                    raw_item_description=raw_item_description,
                    candidate_ids=candidate_ids,
                    candidate_names=candidate_names,
                    reason="Multiple Product.code candidates match Internal Reference",
                )
            # Zero Internal Reference matches: continue to Name fallback.

        if name_present:
            normalized_name = _normalize_text(raw_product)
            matches = [
                candidate
                for candidate in products
                if candidate.name is not None and _normalize_text(candidate.name) == normalized_name
            ]
            if len(matches) == 1:
                return ProductMappingResult(
                    status=MappingStatus.MAPPED,
                    normalized_product_id=matches[0].id,
                    mapping_method=MappingMethod.NAME_EXACT,
                    mapping_source_field="raw_product",
                    raw_internal_reference=raw_internal_reference,
                    raw_product=raw_product,
                    raw_item_description=raw_item_description,
                    candidate_ids=(matches[0].id,),
                    candidate_names=(matches[0].name,),
                    reason="Exact Name to Product.name match",
                )
            if len(matches) > 1:
                candidate_ids, candidate_names = _sorted_candidates(matches)
                return ProductMappingResult(
                    status=MappingStatus.AMBIGUOUS,
                    normalized_product_id=None,
                    mapping_method=None,
                    mapping_source_field="raw_product",
                    raw_internal_reference=raw_internal_reference,
                    raw_product=raw_product,
                    raw_item_description=raw_item_description,
                    candidate_ids=candidate_ids,
                    candidate_names=candidate_names,
                    reason="Multiple Product.name candidates match Name",
                )

        return ProductMappingResult(
            status=MappingStatus.UNMAPPED,
            normalized_product_id=None,
            mapping_method=None,
            mapping_source_field=None,
            raw_internal_reference=raw_internal_reference,
            raw_product=raw_product,
            raw_item_description=raw_item_description,
            candidate_ids=(),
            candidate_names=(),
            reason="No candidate matched Internal Reference or Name",
        )

    def map_unit(
        self,
        *,
        raw_unit: Any,
        units: Iterable[UnitCandidate] = (),
    ) -> UnitMappingResult:
        units = tuple(units)

        if not _is_meaningful(raw_unit):
            return UnitMappingResult(
                status=MappingStatus.UNMAPPED,
                normalized_unit_id=None,
                mapping_method=None,
                mapping_source_field=None,
                raw_unit=raw_unit,
                candidate_ids=(),
                candidate_names=(),
                reason="Unit is not present",
            )

        normalized_unit = _normalize_text(raw_unit)
        matches = [
            candidate
            for candidate in units
            if candidate.name is not None and _normalize_text(candidate.name) == normalized_unit
        ]

        if len(matches) == 1:
            return UnitMappingResult(
                status=MappingStatus.MAPPED,
                normalized_unit_id=matches[0].id,
                mapping_method=MappingMethod.UNIT_NAME_EXACT,
                mapping_source_field="raw_unit",
                raw_unit=raw_unit,
                candidate_ids=(matches[0].id,),
                candidate_names=(matches[0].name,),
                reason="Exact Unit.name match",
            )
        if len(matches) > 1:
            candidate_ids, candidate_names = _sorted_candidates(matches)
            return UnitMappingResult(
                status=MappingStatus.AMBIGUOUS,
                normalized_unit_id=None,
                mapping_method=None,
                mapping_source_field="raw_unit",
                raw_unit=raw_unit,
                candidate_ids=candidate_ids,
                candidate_names=candidate_names,
                reason="Multiple Unit.name candidates match",
            )

        return UnitMappingResult(
            status=MappingStatus.UNMAPPED,
            normalized_unit_id=None,
            mapping_method=None,
            mapping_source_field=None,
            raw_unit=raw_unit,
            candidate_ids=(),
            candidate_names=(),
            reason="No candidate matched Unit",
        )

    def map(
        self,
        validation_result: PurchaseRequestValidationResult,
        *,
        products: Iterable[ProductCandidate] = (),
        units: Iterable[UnitCandidate] = (),
    ) -> PurchaseRequestMappingResult:
        product_result = self.map_product(
            raw_internal_reference=validation_result.raw_internal_reference,
            raw_product=validation_result.raw_product,
            raw_item_description=validation_result.raw_item_description,
            products=products,
        )
        unit_result = self.map_unit(raw_unit=validation_result.raw_unit, units=units)

        return PurchaseRequestMappingResult(
            source_file=validation_result.source_file,
            source_sheet=validation_result.source_sheet,
            source_row=validation_result.source_row,
            product=product_result,
            unit=unit_result,
            quantity_classification=validation_result.quantity_classification,
            quantity_value=validation_result.quantity_value,
            quantity_token=validation_result.quantity_token,
            packaging_token=validation_result.packaging_token,
        )
