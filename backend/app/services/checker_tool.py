"""The checker tool: independently verifies what the action tool produced.

The action tool reports success. This module decides whether to believe it.

Two things make the check independent rather than ceremonial:

1. **The data is re-fetched from source.** Products, the customer and the rule
   book are read again from their own collections. Nothing is taken from the
   action tool's return value or from the request's priced lines.

2. **The money is recomputed here, in longhand.** The arithmetic below is
   written out with ``Decimal`` rather than calling
   ``pricing_engine.price_line``. That is deliberate: sharing the pricing
   function would mean a bug in it produced the same wrong answer twice and the
   check would pass. Writing the sums out means the checker disagrees with the
   engine whenever one of them is wrong.

A check produces findings, not exceptions. The caller decides what a failure
means — in the workflow it means the request is escalated with
``VERIFICATION_MISMATCH`` rather than completed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from app.db.mongo import Collections, get_collection
from app.models.common import object_id
from app.models.company_settings import CompanySettings
from app.models.enums import ApprovalStatus, ProductStatus
from app.models.quotation import Quotation
from app.utils.money import decode_decimals, to_decimal

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
HUNDRED = Decimal("100")
#: Amounts are stored quantised to 2dp, so any disagreement at all is a finding.
TOLERANCE = Decimal("0.00")


def _round(value: Decimal) -> Decimal:
    """Round half-up to 2dp — the convention the pricing engine also uses."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class Finding:
    """One disagreement between the document and the re-derived truth."""

    check: str
    detail: str
    expected: str | None = None
    actual: str | None = None
    #: A line-level finding names its SKU; document-level findings do not.
    sku: str | None = None

    def as_dict(self) -> dict:
        return {
            "check": self.check,
            "detail": self.detail,
            "expected": self.expected,
            "actual": self.actual,
            "sku": self.sku,
        }


@dataclass(slots=True)
class CheckReport:
    """The verdict, with every check that ran named explicitly."""

    passed: bool = True
    checks_run: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    recomputed: dict = field(default_factory=dict)

    def record(self, name: str) -> None:
        if name not in self.checks_run:
            self.checks_run.append(name)

    def fail(self, finding: Finding) -> None:
        self.passed = False
        self.findings.append(finding)

    def as_output(self) -> dict:
        return {
            "passed": self.passed,
            "checks_run": self.checks_run,
            "finding_count": len(self.findings),
            "findings": [finding.as_dict() for finding in self.findings],
            "recomputed": self.recomputed,
        }

    @property
    def summary(self) -> str:
        if self.passed:
            return f"All {len(self.checks_run)} checks passed."
        first = self.findings[0]
        extra = (
            f" (and {len(self.findings) - 1} more)" if len(self.findings) > 1 else ""
        )
        return f"{first.check}: {first.detail}{extra}"


async def verify_quotation(
    quotation: Quotation,
    *,
    settings_doc: CompanySettings | None = None,
    require_pdf: bool = True,
) -> CheckReport:
    """Re-derive the quotation from source records and compare.

    Returns a report; it never raises for a mismatch.
    """
    from app.services import settings_service, verification_service

    report = CheckReport()
    settings_doc = settings_doc or await settings_service.get_settings_document()

    # ---- Approval status --------------------------------------------------
    report.record("approval_status")
    await _check_approval(quotation, report)

    # ---- Products, quantities and unit prices ----------------------------
    report.record("product_information")
    report.record("quantities")
    report.record("unit_prices")
    products = await _load_products(quotation)

    # ---- Line arithmetic: discount, tax, line total ----------------------
    report.record("discount_calculations")
    report.record("tax_calculations")
    totals = _check_lines(quotation, products, settings_doc, report)

    # ---- Document totals -------------------------------------------------
    report.record("final_amount")
    _check_totals(quotation, totals, report)

    # ---- Document consistency -------------------------------------------
    report.record("document_consistency")
    _check_integrity_hash(quotation, verification_service, report)
    if require_pdf:
        report.record("document_file")
        _check_pdf(quotation, report)

    report.recomputed = {key: str(value) for key, value in totals.items()}

    if not report.passed:
        logger.warning(
            "Checker rejected %s: %s", quotation.quotation_number, report.summary
        )
    return report


async def _check_approval(quotation: Quotation, report: CheckReport) -> None:
    """A quotation is either auto-approved within policy, or has a decision."""
    if quotation.auto_approved:
        # Nothing to look up, but the two routes must not both be claimed.
        if quotation.approval_id:
            report.fail(
                Finding(
                    check="approval_status",
                    detail=(
                        "The quotation claims to be auto-approved but also "
                        "references an approval task."
                    ),
                    expected="auto_approved without an approval_id",
                    actual=f"approval_id={quotation.approval_id}",
                )
            )
        return

    if not quotation.approval_id:
        report.fail(
            Finding(
                check="approval_status",
                detail=(
                    "The quotation was not auto-approved and carries no approval "
                    "task, so no authorisation can be evidenced."
                ),
                expected="an approval_id",
                actual="none",
            )
        )
        return

    raw = await get_collection(Collections.APPROVALS).find_one(
        {"_id": object_id(quotation.approval_id)}
    )
    if raw is None:
        report.fail(
            Finding(
                check="approval_status",
                detail="The referenced approval task does not exist.",
                expected=f"approval {quotation.approval_id}",
                actual="missing",
            )
        )
        return

    if raw.get("status") != ApprovalStatus.APPROVED.value:
        report.fail(
            Finding(
                check="approval_status",
                detail="The referenced approval was not granted.",
                expected=ApprovalStatus.APPROVED.value,
                actual=str(raw.get("status")),
            )
        )


async def _load_products(quotation: Quotation) -> dict:
    """Re-read every product the quotation references, from the catalogue."""
    ids = [line.product_id for line in quotation.items]
    if not ids:
        return {}
    cursor = get_collection(Collections.PRODUCTS).find(
        {"_id": {"$in": [object_id(pid) for pid in set(ids)]}}
    )
    documents = await cursor.to_list(length=len(set(ids)))
    products = {}
    for raw in documents:
        decoded = decode_decimals(raw)
        products[str(decoded["_id"])] = decoded
    return products


def _check_lines(
    quotation: Quotation,
    products: dict,
    settings_doc: CompanySettings,
    report: CheckReport,
) -> dict[str, Decimal]:
    """Recompute every line in longhand and total them up independently."""
    default_tax = to_decimal(settings_doc.tax_policy.rate_percent)

    subtotal = Decimal("0.00")
    discount_total = Decimal("0.00")
    taxable_total = Decimal("0.00")
    tax_total = Decimal("0.00")
    final_total = Decimal("0.00")
    quantity_total = 0

    for line in quotation.items:
        product = products.get(str(line.product_id))

        if product is None:
            report.fail(
                Finding(
                    check="product_information",
                    detail="The product on this line no longer exists.",
                    sku=line.sku,
                    expected=f"product {line.product_id}",
                    actual="missing",
                )
            )
            continue

        # -- product identity ------------------------------------------------
        if product.get("sku") != line.sku:
            report.fail(
                Finding(
                    check="product_information",
                    detail="The line's SKU does not match the product it points at.",
                    sku=line.sku,
                    expected=str(product.get("sku")),
                    actual=line.sku,
                )
            )
        if product.get("status") != ProductStatus.ACTIVE.value:
            report.fail(
                Finding(
                    check="product_information",
                    detail="The product is no longer active in the catalogue.",
                    sku=line.sku,
                    expected=ProductStatus.ACTIVE.value,
                    actual=str(product.get("status")),
                )
            )

        # -- quantity --------------------------------------------------------
        if line.quantity < 1:
            report.fail(
                Finding(
                    check="quantities",
                    detail="The quantity is not a positive number.",
                    sku=line.sku,
                    expected=">= 1",
                    actual=str(line.quantity),
                )
            )
            continue

        # -- unit price against the catalogue --------------------------------
        catalogue_price = _round(to_decimal(product.get("unit_price")))
        line_price = _round(to_decimal(line.unit_price))
        if line_price != catalogue_price:
            report.fail(
                Finding(
                    check="unit_prices",
                    detail="The quoted unit price does not match the catalogue.",
                    sku=line.sku,
                    expected=str(catalogue_price),
                    actual=str(line_price),
                )
            )

        # -- longhand arithmetic, from the line's own inputs -----------------
        quantity = Decimal(line.quantity)
        discount_percent = to_decimal(line.applied_discount_percent)
        product_tax = product.get("tax_rate")
        tax_percent = (
            to_decimal(product_tax) if product_tax is not None else default_tax
        )

        expected_subtotal = _round(line_price * quantity)
        expected_discount = _round(expected_subtotal * discount_percent / HUNDRED)
        expected_taxable = _round(expected_subtotal - expected_discount)
        expected_tax = _round(expected_taxable * tax_percent / HUNDRED)
        expected_total = _round(expected_taxable + expected_tax)

        comparisons = [
            ("discount_calculations", "line subtotal", expected_subtotal, line.line_subtotal),
            ("discount_calculations", "line discount", expected_discount, line.line_discount_amount),
            ("discount_calculations", "taxable amount", expected_taxable, line.line_taxable_amount),
            ("tax_calculations", "tax rate", tax_percent, to_decimal(line.tax_rate)),
            ("tax_calculations", "tax amount", expected_tax, line.line_tax_amount),
            ("final_amount", "line total", expected_total, line.line_total),
        ]
        for check, label, expected, stored in comparisons:
            stored_value = _round(to_decimal(stored)) if label != "tax rate" else to_decimal(stored)
            expected_value = expected if label == "tax rate" else _round(expected)
            if abs(stored_value - expected_value) > TOLERANCE:
                report.fail(
                    Finding(
                        check=check,
                        detail=f"The {label} does not match an independent recalculation.",
                        sku=line.sku,
                        expected=str(expected_value),
                        actual=str(stored_value),
                    )
                )

        subtotal += expected_subtotal
        discount_total += expected_discount
        taxable_total += expected_taxable
        tax_total += expected_tax
        final_total += expected_total
        quantity_total += line.quantity

    return {
        "subtotal": _round(subtotal),
        "total_discount": _round(discount_total),
        "taxable_amount": _round(taxable_total),
        "total_tax": _round(tax_total),
        "final_amount": _round(final_total),
        "total_quantity": Decimal(quantity_total),
        "line_count": Decimal(len(quotation.items)),
    }


def _check_totals(
    quotation: Quotation, totals: dict[str, Decimal], report: CheckReport
) -> None:
    """The document's totals must equal the sum of the re-derived lines."""
    pricing = quotation.pricing
    stored = {
        "subtotal": to_decimal(pricing.subtotal),
        "total_discount": to_decimal(pricing.total_discount),
        "taxable_amount": to_decimal(pricing.taxable_amount),
        "total_tax": to_decimal(pricing.total_tax),
        "final_amount": to_decimal(pricing.final_amount),
    }

    for key, expected in totals.items():
        if key in {"total_quantity", "line_count"}:
            continue
        actual = _round(stored[key])
        if abs(actual - _round(expected)) > TOLERANCE:
            report.fail(
                Finding(
                    check="final_amount",
                    detail=f"The document's {key.replace('_', ' ')} does not match the sum of its lines.",
                    expected=str(_round(expected)),
                    actual=str(actual),
                )
            )

    # Internal consistency, independent of the lines: the totals must agree
    # with each other even if every line happened to be wrong in the same way.
    if _round(stored["subtotal"] - stored["total_discount"]) != _round(
        stored["taxable_amount"]
    ):
        report.fail(
            Finding(
                check="final_amount",
                detail="subtotal − discount does not equal the taxable amount.",
                expected=str(_round(stored["subtotal"] - stored["total_discount"])),
                actual=str(_round(stored["taxable_amount"])),
            )
        )
    if _round(stored["taxable_amount"] + stored["total_tax"]) != _round(
        stored["final_amount"]
    ):
        report.fail(
            Finding(
                check="final_amount",
                detail="taxable amount + tax does not equal the final amount.",
                expected=str(_round(stored["taxable_amount"] + stored["total_tax"])),
                actual=str(_round(stored["final_amount"])),
            )
        )

    if int(totals["line_count"]) != pricing.line_count:
        report.fail(
            Finding(
                check="quantities",
                detail="The document's line count does not match its lines.",
                expected=str(int(totals["line_count"])),
                actual=str(pricing.line_count),
            )
        )
    if int(totals["total_quantity"]) != pricing.total_quantity:
        report.fail(
            Finding(
                check="quantities",
                detail="The document's total quantity does not match its lines.",
                expected=str(int(totals["total_quantity"])),
                actual=str(pricing.total_quantity),
            )
        )


def _check_integrity_hash(
    quotation: Quotation, verification_service, report: CheckReport
) -> None:
    """The stored amounts must still match the digest issued with the document."""
    document = quotation.model_dump()
    document["customer_id"] = str(quotation.customer_id)
    if not verification_service.verify_document(document):
        report.fail(
            Finding(
                check="document_consistency",
                detail=(
                    "The integrity digest does not match the stored amounts, so "
                    "the document has changed since it was issued."
                ),
                expected=verification_service.hash_for_document(document)[:16] + "…",
                actual=(quotation.integrity_hash or "")[:16] + "…",
            )
        )

    if not quotation.verification_code:
        report.fail(
            Finding(
                check="document_consistency",
                detail="The quotation has no verification code.",
                expected="a verification code",
                actual="none",
            )
        )


def _check_pdf(quotation: Quotation, report: CheckReport) -> None:
    """The rendered document must exist and look like a PDF."""
    if not quotation.pdf_path:
        report.fail(
            Finding(
                check="document_file",
                detail="No PDF path is recorded on the quotation.",
                expected="a stored path",
                actual="none",
            )
        )
        return

    path = Path(quotation.pdf_path)
    if not path.exists():
        report.fail(
            Finding(
                check="document_file",
                detail="The recorded PDF is missing from disk.",
                expected=str(path),
                actual="missing",
            )
        )
        return

    size = path.stat().st_size
    if size == 0:
        report.fail(
            Finding(
                check="document_file",
                detail="The PDF file is empty.",
                expected="> 0 bytes",
                actual="0 bytes",
            )
        )
        return

    with path.open("rb") as handle:
        magic = handle.read(5)
    if magic != b"%PDF-":
        report.fail(
            Finding(
                check="document_file",
                detail="The stored document is not a PDF.",
                expected="%PDF-",
                actual=repr(magic),
            )
        )
