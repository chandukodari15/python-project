"""
WattWise Reporting Service
Handles CSV export, PDF report generation, and data transformations.
"""
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any
import pandas as pd
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from services.calculator import calculate_tariff, calculate_carbon_footprint


def generate_csv_report(rows: List[Dict[str, Any]]) -> BytesIO:
    """
    Exports reading records to a clean, UTF-8 encoded CSV with tariff and emission details.
    """
    column_names = [
        "Reading ID", "Consumer Name", "Consumer Type", "Region", "Meter Code",
        "Reading Date", "Cumulative Reading (kWh)", "Period Consumption (kWh)",
        "Estimated Bill (INR)", "Est. Carbon (kg CO2)", "Notes"
    ]
    if not rows:
        df = pd.DataFrame(columns=column_names)
        output = BytesIO()
        output.write(df.to_csv(index=False).encode("utf-8-sig"))
        output.seek(0)
        return output

    data = []
    for r in rows:
        consumption = float(r.get("consumption_kwh") or 0) if r.get("consumption_kwh") is not None else None
        tariff_info = calculate_tariff(consumption, r.get("consumer_type", "Residential")) if consumption is not None else {}
        carbon = calculate_carbon_footprint(consumption) if consumption is not None else None
        
        data.append({
            "Reading ID": r.get("reading_id"),
            "Consumer Name": r.get("consumer_name"),
            "Consumer Type": r.get("consumer_type"),
            "Region": r.get("region"),
            "Meter Code": r.get("meter_code"),
            "Reading Date": str(r.get("reading_date")),
            "Cumulative Reading (kWh)": float(r.get("cumulative_kwh") or 0),
            "Period Consumption (kWh)": round(consumption, 2) if consumption is not None else "Baseline",
            "Estimated Bill (INR)": tariff_info.get("total_bill", "—") if consumption is not None else "—",
            "Est. Carbon (kg CO2)": round(carbon, 2) if carbon is not None else "—",
            "Notes": r.get("notes") or ""
        })
    
    df = pd.DataFrame(data)
    output = BytesIO()
    output.write(df.to_csv(index=False).encode("utf-8-sig"))
    output.seek(0)
    return output


def generate_pdf_report(
    records: List[Dict[str, Any]],
    summary_stats: Dict[str, Any],
    report_title: str = "WattWise Electricity Consumption Analysis Report"
) -> BytesIO:
    """
    Generates a professional executive-ready PDF report using ReportLab.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1c1d35')
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#656986')
    )
    card_title_style = ParagraphStyle(
        'CardTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        textColor=colors.HexColor('#7b7f99')
    )
    card_value_style = ParagraphStyle(
        'CardValue',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        textColor=colors.HexColor('#4a44b8')
    )
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        textColor=colors.HexColor('#ffffff')
    )
    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#30324a')
    )
    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1c1d35')
    )

    elements = []

    # Title & Header
    elements.append(Paragraph("<b>WATTWISE</b> · Energy Intelligence System", subtitle_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(report_title, title_style))
    elements.append(Spacer(1, 4))
    gen_time = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    elements.append(Paragraph(f"Generated on {gen_time} · System Workspace Audit Report", subtitle_style))
    elements.append(Spacer(1, 14))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e4e5f0'), spaceAfter=14))

    # Summary KPI Cards
    total_kwh = summary_stats.get("total_kwh", 0)
    avg_kwh = summary_stats.get("avg_kwh", 0)
    peak_kwh = summary_stats.get("peak_kwh", 0)
    total_cost = summary_stats.get("total_cost", 0)

    summary_data = [
        [
            Paragraph("TOTAL MEASURED", card_title_style),
            Paragraph("PERIOD AVERAGE", card_title_style),
            Paragraph("OBSERVED PEAK", card_title_style),
            Paragraph("EST. EXPENDITURE", card_title_style)
        ],
        [
            Paragraph(f"{total_kwh:,.1f} kWh", card_value_style),
            Paragraph(f"{avg_kwh:,.1f} kWh", card_value_style),
            Paragraph(f"{peak_kwh:,.1f} kWh", card_value_style),
            Paragraph(f"Rs. {total_cost:,.2f}", card_value_style)
        ]
    ]
    summary_table = Table(summary_data, colWidths=[130, 130, 130, 130])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e2e4ef')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#eceef7')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 18))

    # Reading Records Section Heading
    elements.append(Paragraph(f"<b>Meter Reading Log & Energy Breakdown</b> (Showing {min(len(records), 80)} Records)", ParagraphStyle(
        'SectionHeading', fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#22243d')
    )))
    elements.append(Spacer(1, 8))

    # Records Table
    table_rows = [[
        Paragraph("DATE", table_header_style),
        Paragraph("CONSUMER", table_header_style),
        Paragraph("REGION", table_header_style),
        Paragraph("METER", table_header_style),
        Paragraph("CUMULATIVE", table_header_style),
        Paragraph("PERIOD USAGE", table_header_style),
        Paragraph("EST. BILL", table_header_style),
    ]]

    for r in records[:80]:
        kwh = r.get("consumption_kwh")
        usage_str = f"{float(kwh):,.1f} kWh" if kwh is not None else "Baseline"
        bill_str = f"Rs. {float(r.get('estimated_bill', 0)):,.2f}" if r.get('estimated_bill') else "—"

        table_rows.append([
            Paragraph(str(r.get("reading_date")), table_cell_style),
            Paragraph(str(r.get("consumer_name", ""))[:20], table_cell_bold),
            Paragraph(str(r.get("region", "")), table_cell_style),
            Paragraph(str(r.get("meter_code", "")), table_cell_style),
            Paragraph(f"{float(r.get('cumulative_kwh', 0)):,.1f}", table_cell_style),
            Paragraph(usage_str, table_cell_bold if kwh and float(kwh) >= 500 else table_cell_style),
            Paragraph(bill_str, table_cell_style),
        ])

    rec_table = Table(table_rows, colWidths=[65, 120, 75, 75, 65, 65, 55])
    rec_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4842d1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fbfbff')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e8e9f2')),
    ]))
    elements.append(rec_table)

    # Footer note
    elements.append(Spacer(1, 16))
    elements.append(Paragraph(
        "Confidential report generated by WattWise Electricity Consumption Analysis System. "
        "Calculated using progressive slab tariffs and certified standard carbon factors.",
        subtitle_style
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer
