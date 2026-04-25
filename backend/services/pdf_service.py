import io
import json
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Frame
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Map urgency levels to colors
URGENCY_COLORS = {
    "CRITICAL": colors.HexColor("#f85149"),
    "HIGH": colors.HexColor("#f0883e"),
    "MODERATE": colors.HexColor("#d29922"),
    "LOW": colors.HexColor("#3fb950")
}

def generate_brief_pdf(patient: dict, session: dict, brief: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Extract data
    patient_name = patient.get("name", "Unknown")
    age = patient.get("age", "N/A")
    gender = patient.get("gender", "N/A")
    
    urgency_level = session.get("urgency_level", "UNKNOWN").upper()
    urgency_score = session.get("urgency_score", 0)
    urgency_color = URGENCY_COLORS.get(urgency_level, colors.gray)
    
    try:
        brief_data = json.loads(brief.get("brief_text", "{}"))
    except:
        brief_data = {}
        
    brief_summary = brief_data.get("brief_summary", "No summary provided.")
    priority_flags = brief_data.get("priority_flags", [])
    history_context = brief_data.get("context_from_history", "None provided.")
    suggested_questions = brief_data.get("suggested_opening_questions", [])
    watch_for = brief_data.get("watch_for", "")
    
    # 1. Header bar (dark blue #0d1a2e)
    c.setFillColor(colors.HexColor("#0d1a2e"))
    c.rect(0, height - 60, width, 60, fill=True, stroke=False)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(30, height - 35, "PriorIQ")
    
    c.setFont("Helvetica", 14)
    c.drawRightString(width - 30, height - 30, "Pre-Visit Clinical Brief")
    
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#8b949e"))
    c.drawRightString(width - 30, height - 45, date_str)
    
    # 2. Patient block
    current_y = height - 90
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(30, current_y, f"{patient_name}  |  {age} y/o  |  {gender}")
    
    # Urgency Level badge
    c.setFillColor(urgency_color)
    c.roundRect(width - 130, current_y - 5, 100, 22, 4, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width - 80, current_y + 2, urgency_level)
    
    current_y -= 40
    
    # 3. Urgency score bar (visual 0-100 bar)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    c.drawString(30, current_y, f"Urgency Score: {urgency_score}/100")
    
    bar_width = width - 60
    c.setFillColor(colors.HexColor("#e6edf3"))
    c.rect(30, current_y - 15, bar_width, 10, fill=True, stroke=False)
    c.setFillColor(urgency_color)
    c.rect(30, current_y - 15, bar_width * (urgency_score / 100.0), 10, fill=True, stroke=False)
    
    current_y -= 45
    
    # Styles for text
    styles = getSampleStyleSheet()
    normal_style = styles["Normal"]
    normal_style.fontName = "Helvetica"
    normal_style.fontSize = 11
    normal_style.leading = 14
    
    bold_style = ParagraphStyle(
        'BoldStyle',
        parent=normal_style,
        fontName='Helvetica-Bold',
        fontSize=12,
        spaceAfter=6
    )
    
    italic_style = ParagraphStyle(
        'ItalicStyle',
        parent=normal_style,
        fontName='Helvetica-Oblique',
        textColor=colors.HexColor("#484f58")
    )
    
    def draw_text_block(title, text_content, y_pos, is_box=False, box_color=None):
        if not text_content:
            return y_pos
            
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.black)
        c.drawString(30, y_pos, title)
        y_pos -= 10
        
        p = Paragraph(text_content, normal_style)
        w, h = p.wrap(width - 60, height)
        
        if is_box:
            c.setStrokeColor(box_color or colors.HexColor("#d0d7de"))
            c.setLineWidth(1)
            c.roundRect(25, y_pos - h - 10, width - 50, h + 15, 4, fill=False, stroke=True)
            p.drawOn(c, 30, y_pos - h - 2)
            return y_pos - h - 30
        else:
            p.drawOn(c, 30, y_pos - h)
            return y_pos - h - 20

    # 4. Brief Summary section in a rounded box
    current_y = draw_text_block("Brief Summary", brief_summary, current_y, is_box=True)
    
    # 5. Priority Flags
    if priority_flags:
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.black)
        c.drawString(30, current_y, "Priority Flags")
        current_y -= 15
        
        for flag in priority_flags:
            c.setFillColor(urgency_color)
            c.circle(35, current_y + 4, 3, fill=True, stroke=False)
            c.setFillColor(colors.black)
            p = Paragraph(flag, normal_style)
            w, h = p.wrap(width - 70, height)
            p.drawOn(c, 45, current_y - h + 10)
            current_y -= h + 5
        current_y -= 10
        
    # 6. History Context
    if history_context:
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.black)
        c.drawString(30, current_y, "History Context")
        current_y -= 10
        
        p = Paragraph(history_context, italic_style)
        w, h = p.wrap(width - 60, height)
        p.drawOn(c, 30, current_y - h)
        current_y -= h + 20
        
    # 7. Suggested Opening Questions
    if suggested_questions:
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.black)
        c.drawString(30, current_y, "Suggested Opening Questions")
        current_y -= 15
        
        for i, q in enumerate(suggested_questions, 1):
            p = Paragraph(f"{i}. {q}", normal_style)
            w, h = p.wrap(width - 60, height)
            p.drawOn(c, 30, current_y - h + 10)
            current_y -= h + 5
        current_y -= 10
        
    # 8. Watch For
    if watch_for:
        box_col = colors.HexColor("#f85149") if urgency_level == "CRITICAL" else colors.HexColor("#8b949e")
        current_y = draw_text_block("Watch For", watch_for, current_y, is_box=True, box_color=box_col)

    # 10. Watermark
    c.saveState()
    c.setFillColor(colors.HexColor("#f0f0f0"))
    c.setFont("Helvetica-Bold", 60)
    c.translate(width/2, height/2)
    c.rotate(45)
    c.drawCentredString(0, 0, "CLINICAL USE ONLY")
    c.restoreState()
    
    # 9. Footer
    c.setFillColor(colors.HexColor("#8b949e"))
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, 30, "Generated by PriorIQ · Confidential · Not for diagnostic use")
    
    c.showPage()
    c.save()
    
    buffer.seek(0)
    return buffer
