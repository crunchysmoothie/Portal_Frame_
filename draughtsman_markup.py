"""Generate a standalone draughtsman markup from a completed design report."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile


PAGE_W, PAGE_H = 1682, 1188


def even_positions(total_mm, maximum_spacing_mm):
    """Return evenly divided positions whose spacing does not exceed the maximum."""
    total = float(total_mm)
    maximum = float(maximum_spacing_mm)
    if total <= 0 or maximum <= 0:
        raise ValueError("Length and maximum spacing must both be greater than zero.")
    spaces = max(1, math.ceil(total / maximum))
    actual = total / spaces
    return [index * actual for index in range(spaces + 1)], actual


def _section(value, field):
    value = str(value or "").strip().lower().replace(" ", "")
    parts = value.split("x")
    if len(parts) != 4:
        raise ValueError(
            f"{field} must use depthxflangexlipxthickness format, "
            "for example 125x50x20x2.5."
        )
    try:
        if any(float(part) <= 0 for part in parts):
            raise ValueError
    except ValueError as exc:
        raise ValueError(
            f"{field} must use positive numbers in depthxflangexlipxthickness format."
        ) from exc
    return value


def _frame_positions(length, spacing):
    positions = [0.0]
    while positions[-1] < length - 1e-6:
        positions.append(min(length, positions[-1] + spacing))
    return positions


def _brace_pairs(count, interval, apex_index=None):
    interval = int(interval)
    if interval < 1:
        raise ValueError("roof_bracing_purlin_interval must be at least 1.")
    breaks = [0, count - 1] if apex_index is None else [0, apex_index, count - 1]
    pairs = []
    for first, last in zip(breaks, breaks[1:]):
        pairs.extend((start, min(start + interval, last)) for start in range(first, last, interval))
    return pairs


def _wall_view_geometry(length_mm, height_mm):
    """Fit a wall elevation using one common horizontal/vertical scale."""
    length = float(length_mm)
    height = float(height_mm)
    if length <= 0 or height <= 0:
        raise ValueError("Wall length and height must both be greater than zero.")
    left, right = 180.0, 1500.0
    top, bottom = 260.0, 850.0
    scale = min((right - left) / length, (bottom - top) / height)
    drawn_width = length * scale
    drawn_height = height * scale
    x0 = (left + right - drawn_width) / 2
    x1 = x0 + drawn_width
    yt = (top + bottom - drawn_height) / 2
    yb = yt + drawn_height
    return x0, x1, yt, yb, scale


class Svg:
    def __init__(self, title, sheet_no):
        self.title = title
        self.sheet_no = sheet_no
        self.items = []

    def line(self, x1, y1, x2, y2, cls="thin"):
        self.items.append(f'<line class="{cls}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')

    def poly(self, points, cls="primary"):
        value = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        self.items.append(f'<polyline class="{cls}" points="{value}"/>')

    def rect(self, x, y, w, h, cls="primary"):
        self.items.append(f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>')

    def circle(self, x, y, r, cls="gridbubble"):
        self.items.append(f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"/>')

    def text(self, x, y, value, cls="note", anchor="middle", rotate=None):
        transform = f' transform="rotate({rotate:.1f} {x:.1f} {y:.1f})"' if rotate is not None else ""
        self.items.append(f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}"{transform}>{html.escape(str(value))}</text>')

    def grid(self, x, y, value):
        self.circle(x, y, 22)
        self.text(x, y + 8, value, "gridtext")

    def dim_h(self, x1, x2, y, value):
        self.line(x1, y, x2, y, "dim")
        self.line(x1, y - 8, x1, y + 8, "dim")
        self.line(x2, y - 8, x2, y + 8, "dim")
        self.text((x1 + x2) / 2, y - 8, value, "dimtext")

    def dim_v(self, x, y1, y2, value):
        self.line(x, y1, x, y2, "dim")
        self.line(x - 8, y1, x + 8, y1, "dim")
        self.line(x - 8, y2, x + 8, y2, "dim")
        self.text(x - 12, (y1 + y2) / 2, value, "dimtext", rotate=-90)

    def render(self, subtitle):
        self.line(70, 1060, 1612, 1060, "primary")
        self.text(75, 1100, "DRAUGHTSMAN MARKUP - NOT FOR CONSTRUCTION", "warning", "start")
        self.text(75, 1134, subtitle, "small", "start")
        self.text(1470, 1100, f"SHEET {self.sheet_no} OF 4", "note", "end")
        self.text(1470, 1134, self.title, "sheettitle", "end")
        return f'<svg viewBox="0 0 {PAGE_W} {PAGE_H}" role="img" aria-label="{html.escape(self.title)}">{"".join(self.items)}</svg>'


def _context(data):
    project = data["project"]
    bracing = data.get("bracing_design", {})
    required = ("gable_width_mm", "eaves_height_mm", "apex_height_mm", "rafter_spacing_mm", "building_length_mm")
    missing = [key for key in required if float(project.get(key, 0) or 0) <= 0]
    if missing:
        raise ValueError(f"Completed report is missing: {', '.join(missing)}")
    purlin = _section(project.get("purlin_section"), "purlin_section")
    girt = _section(project.get("girt_section"), "girt_section")
    purlin_max = float(project.get("purlin_max_spacing_mm", 0) or 0)
    girt_max = float(project.get("girt_max_spacing_mm", 0) or 0)
    interval = int(project.get("roof_bracing_purlin_interval", 0) or 0)
    if purlin_max <= 0 or girt_max <= 0 or interval < 1:
        raise ValueError("Purlin/girt maximum spacings and roof bracing purlin interval are required.")
    members = {item["member_type"]: item for item in bracing.get("bracing_members", [])}
    return {
        "p": project, "b": bracing, "purlin": purlin, "girt": girt,
        "purlin_max": purlin_max, "girt_max": girt_max, "interval": interval,
        "roof_brace": members.get("Roof X-brace", {}).get("section", "TBC"),
        "wall_brace": members.get("Longitudinal side-wall brace", {}).get("section", "TBC"),
    }


def _plan_sheet(c):
    p, b = c["p"], c["b"]
    length, span, spacing = map(float, (p["building_length_mm"], p["gable_width_mm"], p["rafter_spacing_mm"]))
    frames = _frame_positions(length, spacing)
    s = Svg("COLUMN AND GRID LAYOUT PLAN", 1)
    x0, x1, y0, y1 = 180, 1500, 220, 870
    X = lambda v: x0 + (x1 - x0) * v / length
    Y = lambda v: y0 + (y1 - y0) * v / span
    s.rect(x0, y0, x1 - x0, y1 - y0)
    for index, position in enumerate(frames, 1):
        x = X(position); s.line(x, y0 - 45, x, y1 + 45, "gridline"); s.grid(x, y0 - 75, index)
        s.rect(x - 7, y0 - 7, 14, 14, "column"); s.rect(x - 7, y1 - 7, 14, 14, "column")
    for label, yy in (("A", y0), ("B", y1)):
        s.line(x0 - 45, yy, x1 + 45, yy, "gridline"); s.grid(x0 - 75, yy, label)
    for col in b.get("gable_layout", {}).get("columns", []):
        yy = Y(float(col["x_mm"]))
        for xx in (x0, x1): s.rect(xx - 6, yy - 6, 12, 12, "gablecolumn")
        s.text(x0 + 18, yy - 10, f'{col["name"]} {next((g.get("section","") for g in b.get("gable_columns",[]) if g["name"]==col["name"]),"")}', "small", "start")
    s.dim_h(x0, x1, 940, f"BUILDING LENGTH {length:,.0f} mm")
    s.dim_v(110, y0, y1, f"SPAN {span:,.0f} mm")
    s.text(840, 120, "PORTAL COLUMNS SHOWN SOLID; GABLE COLUMNS SHOWN RED", "viewtitle")
    s.text(840, 1010, f'PORTAL COLUMN: {p.get("column_section","")}; TYPICAL FRAME SPACING: {spacing:,.0f} mm', "note")
    return s


def _roof_sheet(c):
    p = c["p"]; length=float(p["building_length_mm"]); span=float(p["gable_width_mm"]); spacing=float(p["rafter_spacing_mm"])
    frames=_frame_positions(length, spacing); s=Svg("ROOF BRACING AND PURLIN PLAN",2)
    x0,x1,y0,y1=180,1500,210,900; X=lambda v:x0+(x1-x0)*v/length; Y=lambda v:y0+(y1-y0)*v/span
    s.rect(x0,y0,x1-x0,y1-y0)
    for i,v in enumerate(frames,1): x=X(v); s.line(x,y0-35,x,y1+35,"gridline"); s.grid(x,y0-70,i)
    half=span/2 if p.get("roof_type")=="Duo Pitched" else span
    rise=float(p["apex_height_mm"])-float(p["eaves_height_mm"]); slope=math.hypot(half,rise)
    along,actual=even_positions(slope,c["purlin_max"])
    left=[value*half/slope for value in along]
    rows=left + ([span-value*half/slope for value in reversed(along[:-1])] if p.get("roof_type")=="Duo Pitched" else [])
    for i,v in enumerate(rows,1): yy=Y(v); s.line(x0,yy,x1,yy,"secondary"); s.text(x1+12,yy+5,f"P{i}","small","start")
    apex_index=len(left)-1 if p.get("roof_type")=="Duo Pitched" else None
    pairs=_brace_pairs(len(rows),c["interval"],apex_index)
    bays=[(frames[0],frames[1]),(frames[-2],frames[-1])]
    for a,bay_end in bays:
        xa,xb=X(a),X(bay_end)
        for i,j in pairs:
            ya,yb=Y(rows[i]),Y(rows[j]); s.line(xa,ya,xb,yb,"brace"); s.line(xa,yb,xb,ya,"brace")
    s.grid(x0-70,y0,"A"); s.grid(x0-70,y1,"B")
    s.dim_h(x0,x1,970,f"BUILDING LENGTH {length:,.0f} mm"); s.dim_v(110,y0,y1,f"ROOF SPAN {span:,.0f} mm")
    s.text(840,115,"ROOF PLAN", "viewtitle")
    s.text(840,1015,f"PURLINS {c['purlin']} CFLC AT {actual:,.0f} mm ACTUAL (MAX {c['purlin_max']:,.0f} mm); ROOF X-BRACING {c['roof_brace']} EVERY {c['interval']} PURLIN SPACE(S)","note")
    return s


def _wall_sheet(c):
    p=c["p"]; length=float(p["building_length_mm"]); height=float(p["eaves_height_mm"]); spacing=float(p["rafter_spacing_mm"])
    frames=_frame_positions(length,spacing); girts,actual=even_positions(height,c["girt_max"]); s=Svg("LONGITUDINAL WALL BRACING ELEVATION",3)
    x0,x1,yt,yb,scale=_wall_view_geometry(length,height); X=lambda v:x0+scale*v; Y=lambda v:yb-scale*v
    for i,v in enumerate(frames,1): x=X(v); s.line(x,yb,x,yt,"primary"); s.grid(x,yt-70,i)
    for v in girts[1:]: s.line(x0,Y(v),x1,Y(v),"secondary")
    layout=c["b"].get("column_bracing_layout",{}); typ=str(layout.get("type",p.get("column_bracing_type","X")))
    panel_count=max(1,int(layout.get("panel_count",1)))
    levels=[height*index/panel_count for index in range(panel_count+1)]
    for a,b in ((frames[0],frames[1]),(frames[-2],frames[-1])):
        xa,xb=X(a),X(b)
        for level in levels: s.line(xa,Y(level),xb,Y(level),"secondary")
        for bottom,top in zip(levels,levels[1:]):
            y_bottom,y_top=Y(bottom),Y(top); y_middle=Y((bottom+top)/2)
            if typ=="K": seg=((xa,y_top,xb,y_middle),(xa,y_bottom,xb,y_middle))
            elif typ=="A": seg=((xa,y_bottom,(xa+xb)/2,y_top),(xb,y_bottom,(xa+xb)/2,y_top))
            else: seg=((xa,y_bottom,xb,y_top),(xa,y_top,xb,y_bottom))
            for q in seg: s.line(*q,"brace")
    dimension_y=min(970,yb+70)
    s.dim_h(x0,x1,dimension_y,f"BUILDING LENGTH {length:,.0f} mm"); s.dim_v(x0-70,yt,yb,f"EAVES {height:,.0f} mm")
    s.text(840,115,"TYPICAL SIDE-WALL ELEVATION", "viewtitle")
    s.text(840,155,"HORIZONTAL AND VERTICAL GEOMETRY SHOWN AT THE SAME SCALE", "small")
    s.text(840,1015,f"GIRTS {c['girt']} CFLC AT {actual:,.0f} mm ACTUAL (MAX {c['girt_max']:,.0f} mm); {typ}-BRACING {c['wall_brace']} IN {panel_count} VERTICAL PANELS", "note")
    return s


def _portal_sheet(c):
    p=c["p"]; span=float(p["gable_width_mm"]); eaves=float(p["eaves_height_mm"]); apex=float(p["apex_height_mm"])
    s=Svg("TYPICAL PORTAL FRAME AND GABLE COLUMN ELEVATION",4); x0,x1,yb=210,1470,520; X=lambda v:x0+(x1-x0)*v/span; Y=lambda v:yb-330*v/apex
    mid=span/2; roof=[(X(0),Y(eaves)),(X(mid),Y(apex)),(X(span),Y(eaves))] if p.get("roof_type")=="Duo Pitched" else [(X(0),Y(eaves)),(X(span),Y(apex))]
    s.line(X(0),yb,X(0),Y(eaves),"primary"); s.line(X(span),yb,X(span),Y(eaves if p.get("roof_type")=="Duo Pitched" else apex),"primary"); s.poly(roof,"primary")
    haunch=span/15; depth=float(str(p.get("rafter_section","0")).split("x")[0] or 0); dy=330*depth/apex
    left_end=(X(haunch),Y(eaves+(apex-eaves)*haunch/mid)); right_end=(X(span-haunch),left_end[1])
    s.poly([(X(0),Y(eaves)),left_end,(X(0),Y(eaves)+dy),(X(0),Y(eaves))],"haunch")
    if p.get("roof_type")=="Duo Pitched": s.poly([(X(span),Y(eaves)),right_end,(X(span),Y(eaves)+dy),(X(span),Y(eaves))],"haunch")
    s.text(330,410,f"HAUNCH L={haunch:,.0f} mm - CUT FROM {p.get('rafter_section','')} RAFTER","small","start")
    s.text(840,115,"TYPICAL PORTAL FRAME SECTION", "viewtitle"); s.dim_h(x0,x1,580,f"SPAN {span:,.0f} mm"); s.dim_v(145,Y(apex),yb,f"APEX {apex:,.0f} mm")
    s.text(840,620,f"COLUMNS {p.get('column_section','')}; RAFTERS {p.get('rafter_section','')}; PURLINS {c['purlin']} CFLC", "note")
    # Gable elevation below.
    gx0,gx1,gyb=250,1430,980; GX=lambda v:gx0+(gx1-gx0)*v/span; GY=lambda v:gyb-270*v/apex
    groof=[(GX(0),GY(eaves)),(GX(mid),GY(apex)),(GX(span),GY(eaves))] if p.get("roof_type")=="Duo Pitched" else [(GX(0),GY(eaves)),(GX(span),GY(apex))]
    s.poly(groof,"primary"); s.line(gx0,gyb,gx0,GY(eaves),"primary"); s.line(gx1,gyb,gx1,GY(eaves),"primary")
    gcols=c["b"].get("gable_columns",[])
    for col in gcols:
        xx=GX(float(col["x_mm"])); s.line(xx,gyb,xx,GY(float(col["height_mm"])),"gablecolumnline"); s.text(xx+10,(gyb+GY(float(col["height_mm"])))/2,f'{col["name"]} {col["section"]}',"small","start",-90)
    s.text(840,690,"GABLE COLUMN ELEVATION", "viewtitle")
    return s


def build_markup_html(data):
    c=_context(data); subtitle=f'{c["p"].get("roof_type","")} PORTAL FRAME - GENERATED FROM COMPLETED DESIGN REPORT'
    sheets=[_plan_sheet(c),_roof_sheet(c),_wall_sheet(c),_portal_sheet(c)]
    css="""@page{size:841mm 594mm;margin:0}*{box-sizing:border-box}html,body{margin:0;padding:0}body{background:#ddd;font-family:Arial,sans-serif}.sheet{width:841mm;height:594mm;margin:8mm auto;background:white;break-after:page;page-break-after:always;overflow:hidden}.sheet:last-child{break-after:auto;page-break-after:auto}svg{display:block;width:100%;height:100%}.thin,.primary,.secondary,.gridline,.brace,.dim,.column,.gablecolumn,.haunch,.gablecolumnline{fill:none;vector-effect:non-scaling-stroke}.thin{stroke:#555;stroke-width:1}.primary{stroke:#111;stroke-width:2}.secondary{stroke:#777;stroke-width:1;stroke-dasharray:7 5}.gridline{stroke:#999;stroke-width:1;stroke-dasharray:12 5 2 5}.brace{stroke:#a8202d;stroke-width:3}.haunch{stroke:#174f78;stroke-width:3}.column{stroke:#111;stroke-width:2;fill:#fff}.gablecolumn{stroke:#a8202d;stroke-width:2;fill:#fff}.gablecolumnline{stroke:#a8202d;stroke-width:2}.dim{stroke:#555;stroke-width:1}.gridbubble{fill:#fff;stroke:#777;stroke-width:1}.note{font-size:18px;fill:#111}.small{font-size:14px;fill:#222}.dimtext{font-size:14px;fill:#333}.gridtext{font-size:25px;fill:#111}.viewtitle{font-size:25px;font-weight:bold;text-decoration:underline}.warning{font-size:18px;font-weight:bold;fill:#a8202d}.sheettitle{font-size:18px;font-weight:bold}.sheettitle,.note,.small,.dimtext,.gridtext,.viewtitle,.warning{font-family:Arial,sans-serif}@media print{body{background:white}.sheet{margin:0}}"""
    pages="".join(f'<section class="sheet">{sheet.render(subtitle)}</section>' for sheet in sheets)
    return f'<!doctype html><html><head><meta charset="utf-8"><title>Draughtsman markup</title><style>{css}</style></head><body>{pages}</body></html>'


def write_markup(data, output_dir="output/markup", create_pdf=True):
    output=Path(output_dir); output.mkdir(parents=True,exist_ok=True)
    html_path=output/"portal_frame_draughtsman_markup.html"; html_path.write_text(build_markup_html(data),encoding="utf-8")
    pdf_path=None
    if create_pdf:
        browsers=[Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")]
        browser_path=shutil.which("chrome") or shutil.which("msedge")
        if browser_path: browsers.append(Path(browser_path))
        target=(output/"portal_frame_draughtsman_markup.pdf").resolve()
        for browser in dict.fromkeys(path for path in browsers if path.exists()):
            try:
                with tempfile.TemporaryDirectory(prefix="portal-markup-") as profile:
                    subprocess.run([
                        str(browser), "--headless=new", "--disable-gpu", "--no-sandbox",
                        "--no-pdf-header-footer", f"--user-data-dir={profile}",
                        f"--print-to-pdf={target}", html_path.resolve().as_uri(),
                    ], check=True, capture_output=True, text=True)
                pdf_path=target
                break
            except subprocess.CalledProcessError:
                continue
    return html_path.resolve(), pdf_path


def main():
    parser=argparse.ArgumentParser(description="Create an A1 draughtsman markup after the design report is complete.")
    parser.add_argument("--report-json",default="output/calculations/portal_frame_calculation_sheet.json")
    parser.add_argument("--output-dir",default="output/markup")
    parser.add_argument("--no-pdf",action="store_true")
    args=parser.parse_args(); data=json.loads(Path(args.report_json).read_text(encoding="utf-8"))
    html_path,pdf_path=write_markup(data,args.output_dir,not args.no_pdf); print(f"Markup HTML written to {html_path}")
    if pdf_path: print(f"Markup PDF written to {pdf_path}")
    elif not args.no_pdf: print("No browser PDF was created; print the generated HTML from Edge or Chrome.")


if __name__ == "__main__":
    main()
