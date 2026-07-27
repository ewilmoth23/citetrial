from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "sample_data" / "transit-evaluation-report.pdf"


def footer(canvas: Canvas, document: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D8DED9"))
    canvas.line(0.75 * inch, 0.58 * inch, 7.75 * inch, 0.58 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#5E6B63"))
    canvas.drawString(0.75 * inch, 0.38 * inch, "SYNTHETIC DATA - NORTHBRIDGE MOBILITY LAB")
    canvas.drawRightString(7.55 * inch, 0.38 * inch, f"Page {document.page}")
    canvas.restoreState()


def main() -> None:
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=29,
            textColor=colors.HexColor("#163F2B"),
            spaceAfter=16,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#1E7049"),
            spaceBefore=14,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Meta",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#5E6B63"),
        )
    )
    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.8 * inch,
        title="Harbor Loop Interim Evaluation",
        author="Northbridge Mobility Lab",
        subject="Synthetic municipal transit research data",
    )
    story = [
        Paragraph("Harbor Loop Interim Evaluation", styles["ReportTitle"]),
        Paragraph(
            "Fictional City of Northbridge | Reporting period: April-September 2032 | Published October 20, 2032",
            styles["Meta"],
        ),
        Spacer(1, 20),
        Paragraph("Executive summary", styles["Section"]),
        Paragraph(
            "The Harbor Loop pilot began on April 3, 2032. Automatic passenger counter records show average weekday boardings increased from 6,800 in March to 8,240 in September. This descriptive comparison does not establish that the pilot caused the entire increase.",
            styles["BodyText"],
        ),
        Paragraph("Service delivered", styles["Section"]),
        Paragraph(
            "The pilot added six battery-electric buses and service every twelve minutes between 6 a.m. and 10 p.m. Scheduled trips operated at 91 percent on-time performance during the reporting period.",
            styles["BodyText"],
        ),
        Spacer(1, 12),
        Table(
            [
                ["Measure", "March baseline", "September"],
                ["Average weekday boardings", "6,800", "8,240"],
                ["Median wait time", "18 minutes", "11 minutes"],
            ],
            colWidths=[3.2 * inch, 1.7 * inch, 1.7 * inch],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#163F2B")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C7D0CA")),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F4F7F5")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        ),
        PageBreak(),
        Paragraph("Interpretation and limitations", styles["ReportTitle"]),
        Paragraph("Competing explanations", styles["Section"]),
        Paragraph(
            "Road construction near Central Station overlapped with the pilot. The evaluation cannot determine how many riders changed routes because of construction rather than the new service. A causal effect therefore remains unresolved.",
            styles["BodyText"],
        ),
        Paragraph("Data reconciliation", styles["Section"]),
        Paragraph(
            "The project dashboard counts transfer validations in its preliminary total. A separate community analysis reports 7,510 September weekday boardings after excluding possible duplicate transfers. The city has not yet published the row-level reconciliation needed to resolve the difference.",
            styles["BodyText"],
        ),
        Paragraph("Next decision", styles["Section"]),
        Paragraph(
            "The Mobility Lab recommends reconciling transfer rules, repeating the rider survey with a probability sample, and measuring winter reliability before a permanent funding decision.",
            styles["BodyText"],
        ),
        Spacer(1, 24),
        Paragraph(
            "This report is entirely synthetic and contains no real people, agencies, ridership records, or credentials.",
            styles["Meta"],
        ),
    ]
    document.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    main()
