from io import BytesIO
from datetime import datetime, timedelta

from quart import Response
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill


async def generate_pdf_statement(account_summary: dict, trades: list):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, height - 72, "Trading Statement")
    c.setFont("Helvetica", 10)
    c.drawString(72, height - 90, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    # License Key
    if 'license_key' in account_summary:
        c.drawString(72, height - 105, f"License Key: {account_summary['license_key'][:16]}...")

    # Account Summary
    c.setFont("Helvetica-Bold", 14)
    y = height - 135
    c.drawString(72, y, "Account Summary")
    y -= 20
    c.setFont("Helvetica", 12)
    for k, v in account_summary.items():
        if k not in ['win_rate', 'drawdown', 'total_trades', 'license_key']:
            c.drawString(72, y, f"{k.replace('_', ' ').title()}: {v}")
            y -= 16

    # Performance Metrics
    y -= 10
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, "Performance Metrics (Last 30 Days)")
    y -= 20
    c.setFont("Helvetica", 12)
    c.drawString(72, y, f"Win Rate: {account_summary.get('win_rate', 0):.2f}%")
    y -= 16
    c.drawString(72, y, f"Max Drawdown: {account_summary.get('drawdown', 0):.2f}%")
    y -= 16
    c.drawString(72, y, f"Total Trades: {account_summary.get('total_trades', 0)}")
    y -= 30

    # Trades Section
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, "Recent Trades (Last 30 Days):")
    y -= 20
    c.setFont("Helvetica", 10)
    
    for t in trades[:40]:  # limit to avoid overflow
        trade_str = f"{t.get('pair', 'N/A')} | Lots: {t.get('lots', 0):.2f} | {t.get('direction', 'N/A')} | Result: ${t.get('result', 0):.2f} | Status: {t.get('status', 'N/A')}"
        if t.get('closed_at'):
            trade_str += f" | Closed: {t.get('closed_at')[:10]}"
        c.drawString(72, y, trade_str)
        y -= 12
        if y < 72:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 72

    c.showPage()
    c.save()
    buffer.seek(0)
    
    # Generate filename with license key
    license_key_prefix = account_summary.get('license_key', 'unknown')[:8]
    filename = f'statement_{license_key_prefix}_{datetime.utcnow().date()}.pdf'
    
    # Read the buffer content
    pdf_data = buffer.getvalue()
    
    # Return response with proper headers
    response = Response(pdf_data, mimetype='application/pdf')
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.headers['Content-Length'] = str(len(pdf_data))
    return response


async def generate_xls_statement(account_summary: dict, trades: list):
    wb = Workbook()
    ws = wb.active
    ws.title = "Statement"
    
    # Styling
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=12)
    title_font = Font(bold=True, size=14)
    
    # Title
    ws.append(["Trading Statement"])
    ws['A1'].font = Font(bold=True, size=16)
    ws.append([f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"])
    
    # License Key
    if 'license_key' in account_summary:
        ws.append([f"License Key: {account_summary['license_key']}"])
    
    ws.append([])
    
    # Account Summary Section
    ws.append(["Account Summary"])
    ws[f'A{ws.max_row}'].font = title_font
    ws.append(["Metric", "Value"])
    for cell in ['A' + str(ws.max_row), 'B' + str(ws.max_row)]:
        ws[cell].fill = header_fill
        ws[cell].font = header_font
    
    for k, v in account_summary.items():
        if k not in ['win_rate', 'drawdown', 'total_trades', 'license_key']:
            ws.append([k.replace('_', ' ').title(), v])
    
    ws.append([])
    
    # Performance Metrics Section
    ws.append(["Performance Metrics (Last 30 Days)"])
    ws[f'A{ws.max_row}'].font = title_font
    ws.append(["Metric", "Value"])
    for cell in ['A' + str(ws.max_row), 'B' + str(ws.max_row)]:
        ws[cell].fill = header_fill
        ws[cell].font = header_font
    
    ws.append(["Win Rate", f"{account_summary.get('win_rate', 0):.2f}%"])
    ws.append(["Max Drawdown", f"{account_summary.get('drawdown', 0):.2f}%"])
    ws.append(["Total Trades", account_summary.get('total_trades', 0)])
    
    ws.append([])
    
    # Trades Section
    ws.append(["Trade History (Last 30 Days)"])
    ws[f'A{ws.max_row}'].font = title_font
    ws.append(["Pair", "Lots", "Direction", "Result", "Status", "Opened", "Closed", "AI Confidence"])
    
    # Style header row
    header_row = ws.max_row
    for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
        cell = col + str(header_row)
        ws[cell].fill = header_fill
        ws[cell].font = header_font
        ws[cell].alignment = Alignment(horizontal='center')
    
    # Add trade data
    for t in trades:
        ws.append([
            t.get('pair', 'N/A'),
            t.get('lots', 0),
            t.get('direction', 'N/A'),
            t.get('result', 0),
            t.get('status', 'N/A'),
            t.get('opened_at', 'N/A'),
            t.get('closed_at', 'N/A'),
            t.get('ai_confidence', 'Unavailable')
        ])
    
    # Adjust column widths
    ws.column_dimensions['A'].width = 15
    ws.column_dimensions['B'].width = 10
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 12
    ws.column_dimensions['E'].width = 10
    ws.column_dimensions['F'].width = 20
    ws.column_dimensions['G'].width = 20
    ws.column_dimensions['H'].width = 15
    
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    
    # Generate filename with license key
    license_key_prefix = account_summary.get('license_key', 'unknown')[:8]
    filename = f'statement_{license_key_prefix}_{datetime.utcnow().date()}.xlsx'
    
    # Read the buffer content
    xlsx_data = bio.getvalue()
    
    # Return response with proper headers
    response = Response(xlsx_data, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.headers['Content-Length'] = str(len(xlsx_data))
    return response
