from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, FancyArrowPatch

out = Path(__file__).parent / "output" / "truss_scenarios" / "25_35_25" / "prokon" / "BTB_80x80x6_PortalFrame_analysis.png"
out.parent.mkdir(parents=True, exist_ok=True)

fig, ax = plt.subplots(figsize=(9, 8), dpi=180)
ax.set_aspect("equal")

# Schematic pair: adjacent vertical legs face one another with a 10 mm clear gap.
scale = 4.0
t, h, gap = 6 * scale, 80 * scale, 10 * scale
cx = 0.0
left_inner, right_inner = -(gap / 2), gap / 2
left_outer, right_outer = left_inner - t, right_inner + t
y0 = -h / 2

left = [(left_outer - h + t, y0), (left_inner, y0), (left_inner, y0 + h),
        (left_outer, y0 + h), (left_outer, y0 + t),
        (left_outer - h + t, y0 + t)]
right = [(-x, y) for x, y in left]
ax.add_patch(Polygon(left, closed=True, facecolor="#4c78a8", edgecolor="#17365d", lw=2))
ax.add_patch(Polygon(right, closed=True, facecolor="#f58518", edgecolor="#7f3f00", lw=2))

# Built-up centroid and axes used by the composite section.
ax.plot(0, 0, "ko", ms=5)
ax.text(5, 5, "Built-up centroid", fontsize=10, weight="bold")
ax.add_patch(FancyArrowPatch((0, 0), (125, 0), arrowstyle="->", mutation_scale=15, color="black", lw=1.5))
ax.add_patch(FancyArrowPatch((0, 0), (0, 190), arrowstyle="->", mutation_scale=15, color="black", lw=1.5))
ax.text(128, -8, "x", fontsize=12, weight="bold")
ax.text(5, 193, "y", fontsize=12, weight="bold")

def dim(p1, p2, label, offset=(0, 0), color="#333333"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="<->", mutation_scale=12, color=color, lw=1.2))
    mx, my = (p1[0] + p2[0]) / 2 + offset[0], (p1[1] + p2[1]) / 2 + offset[1]
    ax.text(mx, my, label, ha="center", va="center", fontsize=10, color=color,
            bbox=dict(facecolor="white", edgecolor="none", pad=1.5))

dim((left_outer - 25, y0), (left_outer - 25, y0 + h), "80 mm", (-14, 0))
dim((left_outer, y0 - 25), (left_inner, y0 - 25), "6 mm", (0, -10))
dim((left_inner, y0 + h + 22), (left_inner + h, y0 + h + 22), "80 mm leg", (0, 10))
dim((left_inner, y0 + h / 2), (right_inner, y0 + h / 2), "10 mm clear gap", (0, 15), "#b22222")

ax.text(-180, 170, "PortalFrame BTB section model", fontsize=15, weight="bold")
ax.text(-180, 150, "2L 80×80×6 equal angles", fontsize=12)
ax.text(-180, 125,
        "A = 1,870 mm²     mass = 14.68 kg/m\n"
        "Ixx = 1.113×10⁶ mm⁴\n"
        "Iyy = 2.499×10⁶ mm⁴\n"
        "rx = 24.40 mm     ry = 36.56 mm\n"
        "10 mm fixed inter-leg gap; parallel-axis theorem",
        fontsize=10.5, va="top", linespacing=1.55,
        bbox=dict(facecolor="#f7f7f7", edgecolor="#aaaaaa", boxstyle="round,pad=0.5"))
ax.text(-180, -180, "The two angles are treated as one symmetric built-up member for axial buckling.", fontsize=9.5)
ax.set_xlim(-200, 200)
ax.set_ylim(-210, 210)
ax.axis("off")
fig.tight_layout()
fig.savefig(out, bbox_inches="tight")
print(out)
