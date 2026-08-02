"""Generate the external overview PDF with a clean, non-overlapping diagram."""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.lib.units import mm

OUT = 'docs/VoiceTest-External-Overview.pdf'

doc = SimpleDocTemplate(
    OUT, pagesize=A4,
    rightMargin=16 * mm, leftMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
)

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='Body', parent=styles['BodyText'], fontSize=10, leading=14.5, textColor=colors.HexColor('#1f2937')))
styles.add(ParagraphStyle(name='TitleX', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor('#0f766e')))
styles.add(ParagraphStyle(name='H2X', parent=styles['Heading2'], fontSize=13, leading=17, spaceBefore=10, textColor=colors.HexColor('#0f172a')))
styles.add(ParagraphStyle(name='H3X', parent=styles['Heading3'], fontSize=11, leading=14, textColor=colors.HexColor('#334155')))
styles.add(ParagraphStyle(name='Muted', parent=styles['BodyText'], fontSize=9, leading=12, textColor=colors.HexColor('#64748b')))

story = []

story.append(Paragraph('VoiceTest: Multilingual AI Collections Assistant', styles['TitleX']))
story.append(Paragraph('External Product Brief (Shareable)', styles['Muted']))
story.append(Spacer(1, 8))

story.append(Paragraph('1) What This Solution Does', styles['H2X']))
story.append(Paragraph(
    'VoiceTest automates first-line overdue EMI collection conversations through an AI voice assistant that can '
    'listen, reason, respond, and trigger downstream actions. It supports multilingual borrower interaction, '
    'captures outcomes like promise-to-pay commitments, and updates CRM/workflows in near real-time.',
    styles['Body']))

story.append(Paragraph('2) Problems It Solves', styles['H2X']))
for b in [
    'Manual collections teams cannot sustainably cover the full overdue borrower base every day.',
    'Language mismatch and code-mixed conversations reduce call effectiveness and customer trust.',
    'Post-call operations are often delayed because CRM logging and follow-up planning are manual.',
    'Risk calls (disputes, distress, abuse) need immediate escalation, not batch triage.',
    'Leadership needs structured call intelligence (disposition + sentiment), not unstructured notes.',
]:
    story.append(Paragraph(f'&bull;&nbsp;&nbsp;{b}', styles['Body']))

story.append(Paragraph('3) Why It Is Better (Business Value)', styles['H2X']))
for b in [
    '<b>Cost efficiency:</b> AI-led first-touch interactions reduce cost per handled conversation vs. full human handling.',
    '<b>Scalable outreach:</b> More borrowers contacted consistently with standardized, compliance-safe messaging.',
    '<b>Operational speed:</b> Outcomes captured instantly; follow-ups and reminders auto-triggered via n8n.',
    '<b>Decision intelligence:</b> Structured sentiment/disposition signals support recovery strategy tuning.',
    '<b>Human focus:</b> High-risk or disputed cases escalate quickly so agents focus where expertise is needed.',
]:
    story.append(Paragraph(f'&bull;&nbsp;&nbsp;{b}', styles['Body']))

story.append(Paragraph('4) Core Capabilities', styles['H2X']))
cellA = ParagraphStyle('CellA', parent=styles['Body'], fontSize=9, leading=12, spaceAfter=0)
cap_data = [
    ['Capability', 'How it works', 'Outcome'],
    ['Multilingual interaction', Paragraph('Understands Hindi, Tamil, English and code-mix; adapts response language per turn.', cellA), Paragraph('Higher borrower engagement, lower friction.', cellA)],
    ['CRM connectivity', Paragraph('Disposition, sentiment and payment commitment written to CRM (in-memory + optional Sheets).', cellA), Paragraph('Near real-time operations visibility.', cellA)],
    ['Escalation mode', Paragraph('Dispute/distress/abuse patterns trigger escalation flags and workflow routing.', cellA), Paragraph('Risk calls moved to human queue quickly.', cellA)],
    ['Sentiment analysis', Paragraph('Each turn tagged positive/neutral/negative plus call disposition.', cellA), Paragraph('Quantifiable call quality and strategy insight.', cellA)],
]
cap = Table(cap_data, colWidths=[38 * mm, 84 * mm, 56 * mm])
cap.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2f5f2')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ('FONTSIZE', (0, 0), (-1, -1), 9),
    ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#cbd5e1')),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ('TOPPADDING', (0, 0), (-1, -1), 4),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(cap)

story.append(PageBreak())

story.append(Paragraph('5) Architecture and Orchestration Flow', styles['H2X']))
story.append(Paragraph(
    'Real-time conversation runs left to right (top lane). Each completed turn produces structured intelligence '
    '(middle lane) that drives CRM updates, n8n automation and escalation (bottom lane).', styles['Body']))
story.append(Spacer(1, 6))

# ---------------------------------------------------------------- diagram ---
W, H = 178 * mm, 120 * mm
d = Drawing(W, H)

INK = colors.HexColor('#0f172a')
SUB = colors.HexColor('#475569')
EDGE = colors.HexColor('#334155')
ARROW = colors.HexColor('#0f766e')
LANE_EDGE = colors.HexColor('#cbd5e1')

LANE_H = 34 * mm
GAP = 5 * mm
lane_y = [H - LANE_H, H - 2 * LANE_H - GAP, H - 3 * LANE_H - 2 * GAP]
lane_titles = [
    'A · LIVE CONVERSATION PIPELINE',
    'B · INTELLIGENCE & DECISION LAYER',
    'C · OPERATIONS & WORKFLOW AUTOMATION (n8n)',
]
lane_fills = ['#f0fdfa', '#f8fafc', '#fffbeb']

for y, title, fill in zip(lane_y, lane_titles, lane_fills):
    d.add(Rect(0, y, W, LANE_H, strokeColor=LANE_EDGE, fillColor=colors.HexColor(fill), rx=6, ry=6))
    d.add(String(4 * mm, y + LANE_H - 5.5 * mm, title, fontSize=8, fillColor=colors.HexColor('#0f766e'), fontName='Helvetica-Bold'))

BOX_H = 17 * mm

def box(cx, y, w, title, sub, fill='#ffffff'):
    """Draw a box centered at cx; title and subtitle centered, no overlap."""
    x = cx - w / 2
    d.add(Rect(x, y, w, BOX_H, strokeColor=EDGE, fillColor=colors.HexColor(fill), rx=3.5, ry=3.5, strokeWidth=1))
    d.add(String(cx, y + BOX_H - 6.2 * mm, title, fontSize=8.4, fillColor=INK, fontName='Helvetica-Bold', textAnchor='middle'))
    lines = sub.split('|')
    ly = y + BOX_H - 10.5 * mm
    for ln in lines:
        d.add(String(cx, ly, ln.strip(), fontSize=7, fillColor=SUB, textAnchor='middle'))
        ly -= 3.2 * mm
    return x, y, w

def harrow(x1, x2, y):
    s = 1 if x2 >= x1 else -1
    d.add(Line(x1, y, x2 - s * 2.2, y, strokeColor=ARROW, strokeWidth=1.3))
    d.add(Polygon(points=[x2, y, x2 - s * 3.2, y + 1.7, x2 - s * 3.2, y - 1.7], fillColor=ARROW, strokeColor=ARROW))

def varrow(x, y1, y2):
    d.add(Line(x, y1, x, y2 + 2.2, strokeColor=ARROW, strokeWidth=1.3))
    d.add(Polygon(points=[x, y2, x - 1.7, y2 + 3.2, x + 1.7, y2 + 3.2], fillColor=ARROW, strokeColor=ARROW))

# Lane A: 5 boxes evenly spaced
ay = lane_y[0] + 5 * mm
a_w = 30 * mm
a_cx = [19 * mm, 54 * mm, 89 * mm, 124 * mm, 159 * mm]
box(a_cx[0], ay, a_w, 'Borrower Voice', 'Mic input | any language', '#ecfeff')
box(a_cx[1], ay, a_w, 'Speech-to-Text', 'Sarvam Saaras v3', '#f0fdf4')
box(a_cx[2], ay, a_w, 'LLM Reasoning', 'Sarvam-105B | collections brain', '#fefce8')
box(a_cx[3], ay, a_w, 'Text-to-Speech', 'Sarvam Bulbul v3', '#f0f9ff')
box(a_cx[4], ay, a_w, 'Voice Playback', 'Browser audio out', '#eef2ff')
mid_a = ay + BOX_H / 2
for i in range(4):
    harrow(a_cx[i] + a_w / 2, a_cx[i + 1] - a_w / 2, mid_a)

# Lane B: 3 boxes
by = lane_y[1] + 5 * mm
b_w = 46 * mm
b_cx = [34 * mm, 89 * mm, 144 * mm]
box(b_cx[0], by, b_w, 'Language Router', 'Per-turn detection | Translate API', '#ffffff')
box(b_cx[1], by, b_w, 'Sentiment & Disposition', 'PTP date, dispute, refusal', '#ffffff')
box(b_cx[2], by, b_w, 'Escalation Policy', 'Distress / abuse | human handoff', '#ffffff')

# Lane A -> Lane B: LLM drops to center box, which feeds the side boxes
varrow(a_cx[2], ay, by + BOX_H)
mid_b = by + BOX_H / 2
harrow(b_cx[1] - b_w / 2, b_cx[0] + b_w / 2, mid_b)        # center -> left
harrow(b_cx[1] + b_w / 2, b_cx[2] - b_w / 2, mid_b)        # center -> right

# Lane C: 4 boxes
cy = lane_y[2] + 5 * mm
c_w = 38 * mm
c_cx = [25 * mm, 68 * mm, 111 * mm, 154 * mm]
box(c_cx[0], cy, c_w, 'CRM Update', 'Outcome writeback | Sheets optional', '#ecfeff')
box(c_cx[1], cy, c_w, 'n8n Workflow', 'Webhook routing | automation', '#fef3c7')
box(c_cx[2], cy, c_w, 'Reminders / Follow-up', 'PTP scheduling', '#ecfccb')
box(c_cx[3], cy, c_w, 'Agent Queue', 'Escalated cases', '#fee2e2')

# Lane B -> Lane C
varrow(b_cx[0], by, cy + BOX_H)          # language router -> CRM
varrow(b_cx[1], by, cy + BOX_H)          # sentiment -> n8n (approx below)
varrow(b_cx[2], by, cy + BOX_H)          # escalation -> agent queue (approx below)

mid_c = cy + BOX_H / 2
harrow(c_cx[0] + c_w / 2, c_cx[1] - c_w / 2, mid_c)
harrow(c_cx[1] + c_w / 2, c_cx[2] - c_w / 2, mid_c)

story.append(d)
story.append(Spacer(1, 10))

story.append(Paragraph('6) Sarvam AI Components Used', styles['H2X']))
cell = ParagraphStyle('Cell', parent=styles['Body'], fontSize=9, leading=12, spaceAfter=0)
sv_data = [
    ['Sarvam component', 'Role', 'Purpose in this solution'],
    ['Saaras (saaras:v3)', 'Speech-to-Text', Paragraph('Converts borrower speech to text for turn understanding and intent capture.', cell)],
    ['Sarvam Chat (sarvam-105b)', 'Reasoning + response', Paragraph('Generates contextual collections replies and structured outcome JSON.', cell)],
    ['Bulbul (bulbul:v3)', 'Text-to-Speech', Paragraph('Produces the natural spoken reply to the borrower.', cell)],
    ['Translate API', 'Language control', Paragraph('Forces output language to match per-turn user language switching.', cell)],
]
sv = Table(sv_data, colWidths=[48 * mm, 40 * mm, 90 * mm])
sv.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2f5f2')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ('FONTSIZE', (0, 0), (-1, -1), 9),
    ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#cbd5e1')),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ('TOPPADDING', (0, 0), (-1, -1), 4),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(sv)

story.append(Paragraph('7) Tech Stack', styles['H2X']))
for b in [
    'Frontend: HTML, CSS, JavaScript voice client with live conversational UX.',
    'Backend: Python FastAPI service for conversation handling and business logic.',
    'AI Services: Sarvam STT + LLM + TTS + Translate APIs.',
    'Workflow: n8n for post-call routing, reminders, and escalation pipelines.',
    'CRM/Data: In-memory CRM with optional Google Sheets integration.',
]:
    story.append(Paragraph(f'&bull;&nbsp;&nbsp;{b}', styles['Body']))

story.append(Paragraph('GitHub Source', styles['H2X']))
story.append(Paragraph('<link href="https://github.com/sumitJha-Realm/VoiceTest/tree/main/src" color="blue">https://github.com/sumitJha-Realm/VoiceTest/tree/main/src</link>', styles['Body']))

story.append(Paragraph('Executive Summary', styles['H2X']))
story.append(Paragraph(
    'VoiceTest delivers a practical, multilingual, AI-first collections workflow that combines natural borrower '
    'interaction with immediate CRM writeback and n8n orchestration. It reduces operational cost, increases outreach '
    'throughput, and preserves human intervention for high-risk conversations through escalation and sentiment-aware routing.',
    styles['Body']))

doc.build(story)
print(OUT)
