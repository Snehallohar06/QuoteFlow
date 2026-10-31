"""Quotation PDF rendering with ReportLab.

Produces a one-or-more page A4 document: company header, both party blocks, the
line table, the totals block, terms, and the verification footer. Rendering is
synchronous and CPU-bound, so callers run it in a worker thread.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from app.models.quotation import Quotation
from app.utils.money import money, rate

# Palette: a single accent plus neutral greys, so the document reads as a
# business form rather than a brochure.
ACCENT = colors.HexColor("#1e3a5f")
ACCENT_LIGHT = colors.HexColor("#eef2f7")
BORDER = colors.HexColor("#c9d2dd")
MUTED = colors.HexColor("#5b6b7f")

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN = 16 * mm
_CONTENT_WIDTH = _PAGE_WIDTH - 2 * _MARGIN


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "QFTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=ACCENT,
            alignment=TA_RIGHT,
            spaceAfter=0,
        ),
        "company": ParagraphStyle(
            "QFCompany",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=ACCENT,
        ),
        "small": ParagraphStyle(
            "QFSmall",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
        ),
        "body": ParagraphStyle(
            "QFBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
        ),
        "label": ParagraphStyle(
            "QFLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
        "cell": ParagraphStyle(
            "QFCell", parent=base["Normal"], fontName="Helvetica", fontSize=9, leading=12
        ),
        "cellRight": ParagraphStyle(
            "QFCellRight",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            alignment=TA_RIGHT,
        ),
        "code": ParagraphStyle(
            "QFCode",
            parent=base["Normal"],
            fontName="Courier-Bold",
            fontSize=12,
            leading=15,
            textColor=ACCENT,
            alignment=TA_CENTER,
        ),
        "footer": ParagraphStyle(
            "QFFooter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
    }


def _fmt(amount: Decimal | str | int, symbol: str = "") -> str:
    """Format a monetary amount with thousands separators."""
    value = money(amount)
    text = f"{value:,.2f}"
    return f"{symbol} {text}".strip() if symbol else text


def _date(value) -> str:
    return value.strftime("%d %b %Y") if value else "-"


def _header(quotation: Quotation, style: dict) -> Table:
    seller = quotation.seller
    left = [Paragraph(seller.name, style["company"])]
    for line in seller.address_lines:
        left.append(Paragraph(line, style["small"]))
    contact = " | ".join(filter(None, [seller.email, seller.phone]))
    if contact:
        left.append(Paragraph(contact, style["small"]))
    if seller.tax_id:
        left.append(Paragraph(f"Tax ID: {seller.tax_id}", style["small"]))

    right = [
        Paragraph("QUOTATION", style["title"]),
        Spacer(1, 4),
        Paragraph(
            f"<b>{quotation.quotation_number}</b>",
            ParagraphStyle(
                "QFNum", parent=style["body"], alignment=TA_RIGHT, fontSize=11
            ),
        ),
        Paragraph(
            f"Issued {_date(quotation.issued_at)}<br/>"
            f"Valid until {_date(quotation.valid_until)}<br/>"
            f"Ref. request {quotation.request_number}",
            ParagraphStyle("QFMeta", parent=style["small"], alignment=TA_RIGHT),
        ),
    ]

    table = Table(
        [[left, right]],
        colWidths=[_CONTENT_WIDTH * 0.55, _CONTENT_WIDTH * 0.45],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _parties(quotation: Quotation, style: dict) -> Table:
    buyer = quotation.buyer
    buyer_cell = [Paragraph("QUOTATION FOR", style["label"]), Spacer(1, 3)]
    buyer_cell.append(
        Paragraph(f"<b>{buyer.name}</b>", style["body"])
    )
    if buyer.code:
        buyer_cell.append(Paragraph(f"Customer code: {buyer.code}", style["small"]))
    if buyer.contact_name:
        buyer_cell.append(Paragraph(f"Attn: {buyer.contact_name}", style["small"]))
    for line in buyer.address_lines:
        buyer_cell.append(Paragraph(line, style["small"]))
    contact = " | ".join(filter(None, [buyer.email, buyer.phone]))
    if contact:
        buyer_cell.append(Paragraph(contact, style["small"]))
    if buyer.tax_id:
        buyer_cell.append(Paragraph(f"Tax ID: {buyer.tax_id}", style["small"]))

    approval_lines = [Paragraph("AUTHORISATION", style["label"]), Spacer(1, 3)]
    if quotation.auto_approved:
        approval_lines.append(
            Paragraph(
                "Approved automatically: all discounts and totals fell within "
                "company policy limits.",
                style["small"],
            )
        )
    else:
        approval_lines.append(
            Paragraph(
                f"<b>{quotation.approved_by_name or 'Sales Manager'}</b>",
                style["body"],
            )
        )
        approval_lines.append(Paragraph("Sales Manager", style["small"]))
        approval_lines.append(
            Paragraph("Reviewed and approved for issue.", style["small"])
        )
    approval_lines.append(
        Paragraph(f"Status: {quotation.status}", style["small"])
    )

    table = Table(
        [[buyer_cell, approval_lines]],
        colWidths=[_CONTENT_WIDTH * 0.55, _CONTENT_WIDTH * 0.45],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), ACCENT_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _items_table(quotation: Quotation, style: dict) -> Table:
    symbol = ""
    header = [
        Paragraph("<b>#</b>", style["cell"]),
        Paragraph("<b>Item</b>", style["cell"]),
        Paragraph("<b>Qty</b>", style["cellRight"]),
        Paragraph("<b>Unit price</b>", style["cellRight"]),
        Paragraph("<b>Disc. %</b>", style["cellRight"]),
        Paragraph("<b>Discount</b>", style["cellRight"]),
        Paragraph("<b>Taxable</b>", style["cellRight"]),
        Paragraph("<b>Tax</b>", style["cellRight"]),
        Paragraph("<b>Line total</b>", style["cellRight"]),
    ]
    rows = [header]

    for index, item in enumerate(quotation.items, start=1):
        description = f"<b>{item.name}</b><br/><font size=7.5 color='#5b6b7f'>SKU {item.sku}</font>"
        rows.append(
            [
                Paragraph(str(index), style["cell"]),
                Paragraph(description, style["cell"]),
                Paragraph(f"{item.quantity} {item.unit}", style["cellRight"]),
                Paragraph(_fmt(item.unit_price, symbol), style["cellRight"]),
                Paragraph(f"{rate(item.applied_discount_percent)}", style["cellRight"]),
                Paragraph(_fmt(item.line_discount_amount, symbol), style["cellRight"]),
                Paragraph(_fmt(item.line_taxable_amount, symbol), style["cellRight"]),
                Paragraph(_fmt(item.line_tax_amount, symbol), style["cellRight"]),
                Paragraph(
                    f"<b>{_fmt(item.line_total, symbol)}</b>", style["cellRight"]
                ),
            ]
        )

    widths = [
        _CONTENT_WIDTH * ratio
        for ratio in (0.035, 0.265, 0.085, 0.105, 0.07, 0.105, 0.11, 0.095, 0.13)
    ]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ACCENT_LIGHT]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _totals_table(quotation: Quotation, style: dict) -> Table:
    pricing = quotation.pricing
    symbol = ""
    currency = pricing.currency

    rows = [
        ["Subtotal", _fmt(pricing.subtotal, symbol)],
        [
            f"Discount ({rate(pricing.effective_discount_percent)}%)",
            f"-{_fmt(pricing.total_discount, symbol)}",
        ],
        ["Taxable amount", _fmt(pricing.taxable_amount, symbol)],
        [f"{pricing.tax_label}", _fmt(pricing.total_tax, symbol)],
        [f"Total ({currency})", _fmt(pricing.final_amount, symbol)],
    ]
    data = [
        [
            Paragraph(label, style["cellRight"] if index < 4 else style["cell"]),
            Paragraph(value, style["cellRight"]),
        ]
        for index, (label, value) in enumerate(rows)
    ]
    data[-1] = [
        Paragraph(f"<b>{rows[-1][0]}</b>", style["cell"]),
        Paragraph(f"<b>{rows[-1][1]}</b>", style["cellRight"]),
    ]

    table = Table(data, colWidths=[_CONTENT_WIDTH * 0.22, _CONTENT_WIDTH * 0.18])
    table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, BORDER),
                ("LINEABOVE", (0, -1), (-1, -1), 1, ACCENT),
                ("BACKGROUND", (0, -1), (-1, -1), ACCENT_LIGHT),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    wrapper = Table(
        [[" ", table]], colWidths=[_CONTENT_WIDTH * 0.6, _CONTENT_WIDTH * 0.4]
    )
    wrapper.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return wrapper


def _verification_block(quotation: Quotation, style: dict) -> KeepTogether:
    body = [
        Paragraph("DOCUMENT VERIFICATION", style["label"]),
        Spacer(1, 4),
        Paragraph(quotation.verification_code, style["code"]),
        Spacer(1, 4),
        Paragraph(
            "Confirm this quotation against the issuing system by entering the code "
            "above at the verification endpoint. The integrity digest below is "
            "derived from the quoted amounts; any change to them invalidates it.",
            style["small"],
        ),
        Spacer(1, 3),
        Paragraph(
            f"<font face='Courier' size=6.5>SHA-256 HMAC: "
            f"{quotation.integrity_hash}</font>",
            style["small"],
        ),
    ]
    table = Table([[body]], colWidths=[_CONTENT_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("BACKGROUND", (0, 0), (-1, -1), ACCENT_LIGHT),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return KeepTogether([table])


def _page_furniture(canvas, document) -> None:
    """Footer drawn on every page: page numbers and the issuing system."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(
        _PAGE_WIDTH / 2,
        10 * mm,
        f"Page {canvas.getPageNumber()}  -  Generated by QuoteFlow  -  "
        f"This quotation is computer generated from an approved request.",
    )
    canvas.restoreState()


def render_quotation_pdf(quotation: Quotation, output_path: Path | None = None) -> Path:
    """Render the quotation and return the path of the written file."""
    style = _styles()
    target = output_path or (
        settings.pdf_storage_path / f"{quotation.quotation_number}.pdf"
    )
    target.parent.mkdir(parents=True, exist_ok=True)

    document = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN + 6 * mm,
        title=f"Quotation {quotation.quotation_number}",
        author=quotation.seller.name,
        subject=f"Quotation for {quotation.buyer.name}",
        creator="QuoteFlow",
    )

    story: list = [
        _header(quotation, style),
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceAfter=10),
        _parties(quotation, style),
        Spacer(1, 12),
        _items_table(quotation, style),
        Spacer(1, 10),
        _totals_table(quotation, style),
        Spacer(1, 14),
    ]

    if quotation.terms:
        terms_body = [Paragraph("TERMS AND CONDITIONS", style["label"]), Spacer(1, 4)]
        terms_body.extend(
            Paragraph(f"{index}. {term}", style["small"])
            for index, term in enumerate(quotation.terms, start=1)
        )
        story.append(KeepTogether(terms_body))
        story.append(Spacer(1, 12))

    story.append(_verification_block(quotation, style))

    document.build(story, onFirstPage=_page_furniture, onLaterPages=_page_furniture)
    return target
