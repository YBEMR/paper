"""Shared print style for the two thesis chapters."""
from pathlib import Path

import matplotlib as mpl
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BLUE = "#315D87"
TEAL = "#007F78"
ORANGE = "#C16A35"
RED = "#A34445"
INK = "#243746"
GRAY = "#647682"
GRID = "#DDE4E8"


def setup():
    for font_path in [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]:
        if font_path.is_file():
            font_manager.fontManager.addfont(str(font_path))
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "Noto Sans CJK JP",
                            "Source Han Sans SC", "SimHei", "DejaVu Sans"],
        "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 10.5,
        "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.titlepad": 9, "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": GRAY, "axes.labelcolor": INK, "axes.linewidth": 0.75,
        "xtick.color": INK, "ytick.color": INK, "xtick.labelsize": 8,
        "ytick.labelsize": 8, "text.color": INK, "legend.fontsize": 8,
        "legend.frameon": False, "grid.color": GRID, "grid.linewidth": 0.55,
        "axes.axisbelow": True, "pdf.fonttype": 42, "ps.fonttype": 42,
        "svg.fonttype": "none", "axes.unicode_minus": False,
        "figure.facecolor": "white", "savefig.facecolor": "white",
        "savefig.dpi": 300,
    })


def save(fig, stem):
    fig.savefig(ROOT / (stem + ".pdf"))
    fig.savefig(ROOT / (stem + ".png"), dpi=300)
