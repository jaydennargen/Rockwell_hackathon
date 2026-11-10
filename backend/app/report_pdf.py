"""Repair report in the layout of the SAP "Remanufacturing/Repair Report" (reference PDF in the repo root).

`report_sections(report)` turns a ROLE-FILTERED report into the reference report's sections, and
`render_pdf(report)` draws them. Every section carries a provenance tag:

    FROM ORDER       data submitted with the repair order
    PREDICTION       inferred by the AI, not yet confirmed by inspection
    VERIFIED         confirmed or corrected by a repair specialist
    PENDING          completed by the technician after the repair (never filled in here)

This is a pre-repair document, so As Received, Cleaning, Updates, Parts Replaced, and Testing are
always PENDING (ARCHITECTURE.md §9). The frontend's RepairReport.jsx mirrors these sections.
"""
from __future__ import annotations

import io
import re
import textwrap
from datetime import date, datetime

from app import config

NA = "Not provided"
PENDING_TEXT = "Pending: to be completed by the technician after repair."

CAUSE_SAP = {  # cause_category -> SAP Probable Cause Code wording
    "component_failure": "Component Failure",
    "wear_out": "Worn / End of Life",
    "contamination": "Contamination / Environmental",
    "physical_damage": "Physical / Mechanical Damage",
    "configuration_error": "Configuration Error",
    "no_problem_found": "No Problem Found",
    "external_electrical": "Improper Voltage or Current",
}
AREA_FALLBACK = {
    "pcba_circuitry": "PCBA - Circuitry", "fan_cooling": "Component - Fan Assembly",
    "motor_mechanical": "Motors - Mechanical", "hmi_display": "Touchscreen / Display",
    "enclosure_wiring": "Component - Cover / Chassis / Cable", "other": "Other",
}
_SAP_FIELDS = re.compile(r"\s+(?=(?:Serial Number|Ship/End Customer PO|PO#|RAAMP BARCODE|CAT#)\s*[:=])", re.I)


def fmt_date(v) -> str:
    if not v:
        return ""
    d = v if isinstance(v, (date, datetime)) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d.strftime("%m/%d/%Y")


def comment_lines(raw: str) -> list[str]:
    """SAP comments put each field on its own line; restore those breaks for single-line input."""
    lines = []
    for ln in (raw or "").splitlines():
        lines += [p for p in _SAP_FIELDS.split(ln.strip()) if p]
    return lines


def _prediction_tag(report: dict) -> tuple[str, str | None]:
    review = report.get("review") or {}
    if report["status"] in ("APPROVED", "EDITED") and review:
        who = f"{review.get('reviewer', 'specialist')}, {fmt_date(review.get('reviewed_at'))}"
        return "VERIFIED", f"Confirmed by specialist review ({who})."
    return "PREDICTION", None


def report_sections(r: dict) -> list[dict]:
    """[{title, tag, lines}] in the reference report's order."""
    name = config.PRODUCT_NAME
    ci = r.get("customer_input") or {}
    pred = r.get("predicted")
    tag, verified = _prediction_tag(r)

    distributor = ["Comments:"] + (comment_lines(ci.get("raw") or ci.get("text") or "") or ["None provided."])
    if ci.get("additional_info"):
        distributor += ["", "Additional Information:"] + comment_lines(ci["additional_info"])

    def unreleased(what: str) -> list[str]:
        if r["status"] == "PROCESSING":
            return [f"{name} is still triaging this order."]
        if r["status"] == "FAILED":
            return [f"{name} couldn't process this order, so no {what} is available."]
        if r["status"] == "REJECTED":
            return [f"Not released. See the specialist notes below."]
        return ["Pending specialist review. A repair specialist is checking this order",
                f"before any {what} is released."]

    if pred:
        areas = [a.get("detail") if a.get("detail") and a["detail"] != "From product history"
                 else AREA_FALLBACK.get(a["category"], a["category"]) for a in pred["areas"]]
        intro = ([verified] if verified else
                 [f"Predicted by {name} from the distributor input and this product's repair history.",
                  "Not yet confirmed by inspection or testing. The following areas are likely affected:"])
        affected = (intro + [f"* {a}" for a in dict.fromkeys(areas)]) if areas else intro + ["* None identified"]
        cause_intro = ([verified] if verified else
                       [f"{name} offers this estimate of probable cause based on information accompanying",
                        "the returned unit and this product's repair history:"])
        causes = cause_intro + ([f"* {CAUSE_SAP.get(c, c)}" for c in pred["causes"]] or ["* Not determined"])
    else:
        tag = "PENDING"
        affected = unreleased("prediction")
        causes = unreleased("probable cause")

    sections = [
        {"title": "Distributor Input", "tag": "FROM ORDER", "lines": distributor},
        {"title": "As Received", "tag": "PENDING", "lines": [PENDING_TEXT]},
        {"title": "Cleaning", "tag": "PENDING", "lines": [PENDING_TEXT]},
        {"title": "Updates", "tag": "PENDING", "lines": [PENDING_TEXT]},
        {"title": "Affected Areas", "tag": tag, "lines": affected},
        {"title": "Parts Replaced", "tag": "PENDING", "lines": [PENDING_TEXT]},
        {"title": "Testing", "tag": "PENDING", "lines": [PENDING_TEXT]},
        {"title": "Probable Cause Code", "tag": tag, "lines": causes},
    ]
    review = r.get("review") or {}
    if review.get("notes"):
        sections.append({"title": "Specialist Notes", "tag": "VERIFIED",
                         "lines": [f"{review.get('reviewer', '')}, {fmt_date(review.get('reviewed_at'))}:",
                                   review["notes"]]})
    return sections


def header_cells(r: dict) -> dict:
    h = r["header"]
    return {
        "sold_to": [f"Sold To Party: {NA}", f"Name: {h.get('sold_to') or NA}", f"Address: {NA}"],
        "end_customer": [f"End Customer: {NA}", f"Name: {NA}", f"Address: {NA}"],
        "row1": [("Part Number", h.get("catalog") or ""), ("Serial Number", h.get("serial") or ""),
                 ("Description", h.get("description") or ""), ("Repair Order No", h.get("order_number") or ""),
                 ("Repair Item", str(h.get("item") or ""))],
        "row2": [("Purchase Order No", h.get("purchase_order") or NA),
                 ("Date Received", fmt_date(h.get("received_date"))),
                 ("Date Shipped", "Not shipped"), ("Date of Manufacture", "")],
    }


# ---------- drawing ----------
PAGE_W, PAGE_H = 612, 792            # US Letter, like the reference
L, R = 14, 599                       # content box
MAROON = (0.5, 0, 0)
GRAY = (0.75, 0.75, 0.75)
YELLOW = (1, 1, 0.67)
TAG_COLOR = {"FROM ORDER": (0.25, 0.25, 0.25), "PREDICTION": (0.1, 0.3, 0.75),
             "VERIFIED": (0.1, 0.45, 0.2), "PENDING": (0.45, 0.45, 0.45)}
TAG_TEXT = {"FROM ORDER": "FROM ORDER", "PREDICTION": "AI PREDICTION - NOT VERIFIED",
            "VERIFIED": "VERIFIED BY SPECIALIST", "PENDING": "PENDING - TECHNICIAN"}
BODY, LEAD, BOTTOM = 9, 13, 44


def render_pdf(r: dict) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Repair Report {r['header'].get('order_number', '')}")
    c.setAuthor(config.PRODUCT_NAME)
    page = [1]

    def footer():
        c.setFont("Courier", 7)
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.drawString(L, 24, f"Pre-repair triage draft generated by {config.PRODUCT_NAME}. AI predictions are not "
                            "inspection results. Not an official Rockwell Automation document.")
        c.drawRightString(R, 14, f"Order {r['order_id']}  |  Page {page[0]}")
        c.setFillColorRGB(0, 0, 0)

    # title band
    top = PAGE_H - 29
    c.setFillColorRGB(*MAROON)
    c.rect(L, top - 71, R - L, 71, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.rect(R - 46, top - 14, 46, 14, stroke=0, fill=1)
    c.setFillColorRGB(*MAROON)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(R - 23, top - 10, config.PRODUCT_NAME)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Times-Bold", 16)
    c.drawString(L + 7, top - 46, "Remanufacturing/Repair Report")
    c.setFont("Times-Bold", 10)
    c.drawString(L + 7, top - 58, fmt_date(datetime.now()))
    c.setFillColorRGB(0, 0, 0)
    c.setLineWidth(0.6)

    # sold to / end customer
    hc = header_cells(r)
    y = top - 71
    c.rect(L, y - 58, R - L, 58)
    c.line((L + R) / 2, y, (L + R) / 2, y - 58)
    c.setFont("Courier", 10)
    for col, lines in ((L + (R - L) / 4, hc["sold_to"]), (L + 3 * (R - L) / 4, hc["end_customer"])):
        for i, ln in enumerate(lines):
            c.drawCentredString(col, y - 14 - i * 12, ln)
    y -= 58
    c.line(L, y - 3, R, y - 3)
    y -= 12
    c.line(L, y, R, y)

    # order table
    def table_row(cols, xs, y, h_head, h_val):
        c.setFillColorRGB(*GRAY)
        c.rect(L, y - h_head, R - L, h_head, stroke=1, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.rect(L, y - h_head - h_val, R - L, h_val)
        for x in xs[1:-1]:
            c.line(x, y, x, y - h_head - h_val)
        for (label, value), x0, x1 in zip(cols, xs, xs[1:]):
            cx, chars = (x0 + x1) / 2, int((x1 - x0 - 6) / 6)
            c.setFont("Courier", 10)
            for i, ln in enumerate(textwrap.wrap(label, max(chars, 4))[:2]):
                c.drawCentredString(cx, y - 12 - i * 11, ln)
            for i, ln in enumerate(textwrap.wrap(value, max(chars, 4))[:3]):
                c.drawCentredString(cx, y - h_head - 13 - i * 11, ln)
        return y - h_head - h_val

    y = table_row(hc["row1"], [L, 158, 300, 443, 528, R], y, 29, 29)
    y = table_row(hc["row2"], [L, 158, 300, 443, R], y, 25, 32)

    # sections
    box_top = [y]

    def close_box(bottom):
        c.line(L, box_top[0], L, bottom)
        c.line(R, box_top[0], R, bottom)
        c.line(L, bottom, R, bottom)

    def new_page():
        nonlocal y
        close_box(y)
        footer()
        c.showPage()
        page[0] += 1
        c.setLineWidth(0.6)
        y = PAGE_H - 44
        box_top[0] = y
        c.line(L, y, R, y)

    chars = int((R - L - 12) / (BODY * 0.6))
    for s in report_sections(r):
        if y - 14 - 2 * LEAD < BOTTOM:
            new_page()
        c.setFillColorRGB(*YELLOW)
        c.rect(L, y - 14, R - L, 14, stroke=1, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Courier", BODY)
        c.drawString(L + 4, y - 10, s["title"])
        c.setFillColorRGB(*TAG_COLOR[s["tag"]])
        c.setFont("Courier-Bold", 7)
        c.drawRightString(R - 4, y - 10, TAG_TEXT[s["tag"]])
        c.setFillColorRGB(0, 0, 0)
        y -= 14 + 4
        c.setFont("Courier", BODY)
        for ln in s["lines"]:
            for part in (textwrap.wrap(ln, chars, subsequent_indent="  ") or [""]):
                if y - LEAD < BOTTOM:
                    new_page()
                    c.setFont("Courier", BODY)
                y -= LEAD
                c.drawString(L + 6, y + 3, part)
        y -= 8
        c.line(L, y, R, y)
    close_box(y)
    footer()
    c.save()
    return buf.getvalue()
