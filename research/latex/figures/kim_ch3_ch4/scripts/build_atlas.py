"""Assemble the numbered figures as a bookmarked, vector PDF."""
import csv
from io import BytesIO
from pathlib import Path
import re

from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
FONT = "AtlasCJK"
WIDTH = 595.28
MARGIN = 32
BODY = WIDTH - 2 * MARGIN
DARK, MUTED, ACCENT, LINE = "#233746", "#586D79", "#00796F", "#CFDCDD"

# Order follows the chapter blueprint, which assigns two numbers to the pressure figure.
FIGURES = [
    ("3-1", "fig01_joint", "跨场景连续热耦合与联合决策机制",
     "3.3　联合评价模型",
     "每个候选固定全窗部署，为四个场景段分别选择 CPU、GPU 和共享 DLA 频档。上一段的四节点末温作为下一段的入口温度，温度相关漏电计入整板能耗。",
     "本例的 500 个请求各有 40 ms 相对期限。热约束覆盖 10 s 服务窗和 40 ms 尾窗，四节点的连续峰温认证上界均须不高于 80 °C。"),
    ("3-2", "fig02_power", "三类频域的频档与模型功耗",
     "3.6.1　平台参数",
     "横轴给出各频域的低、中、高三个离散工作点及对应频率。活动增量按频率与电压平方的乘积缩放。CPU 前、后处理均按单核给出。",
     "静态曲线取节点温度 30 °C，合并 25 °C 基准静态功耗和温度相关漏电增量。各面板使用合成模型参数，纵轴量程随频域变化。"),
    ("3-3", "fig04_temperature", "同一最高频方案在两种热评价下的全窗温度",
     "3.6.2（1）　连续热耦合",
     "25 °C、正序原驻留，固定部署 C，四段均取 HHH。独立评价在每个场景入口将四节点重置到 30 °C。GPU 的独立峰温上界为 77.5527 °C，连续评价的峰温下界已达 80.7730 °C，超过 80 °C 温限。",
     "折线连接原始采样点，安全判定取连续评价的认证界。另列同工况 D001（编码 448）的连续安全参照，归档记录 500/500 个请求完成，能耗 44.6793 J。"),
    ("3-4", "fig03_baselines", "常规工况的最低安全能耗与独立热评价误接纳",
     "3.6.2（1）—（2）　机理与常规能效",
     "在 25 °C、逆序原驻留的完整 81 部署库中，联合调度较最高频安全基线节能 31.73%，较静态调频节能 10.42%。81 个最高频候选中，58 个安全，23 个超温。",
     "在 25 °C、正序原驻留的 A/C 域中，场景调频的节能率为 10.18%。连续复核在独立评价接纳的 118,098 个序列中检出 4,707 个超温序列。该域静态最低峰温方案与静态最低能耗方案重合，完整动态域缺逐候选峰温。"),
    ("3-5", "fig05a_pressure_classes", "压力工况下期限合法频率序列的热分类",
     "3.6.2（3）　压力工况联合可行性",
     "27.5 °C 下考察三组场景顺序与驻留组合。每根柱的母集是该工况、该部署下全部按期完成的序列。十二个分类单元的热判定均已决。",
     "每种工况下，A、C 分别有 59,049 个期限合法序列，均超温。D001 和 D015 分别有 18,225 和 6,561 个期限合法序列，均通过连续热检查。"),
    ("3-6", "fig05b_pressure_margins", "压力工况下安全代表的能耗与约束裕量",
     "3.6.2（3）　能耗与裕量权衡",
     "在每种工况内，分别取 D001、D015 的最低安全能耗序列。D001 在三个工况下均略省电，D015 的峰温上界更低、最小期限裕量更大。",
     "热裕量等于 80 °C 减去全窗四节点峰温认证上界。最小期限裕量取全部请求的截止时刻与完成时刻之差的最小值，单位为 ms。三项指标分别读轴。"),
    ("4-1", "fig06_search", "连续能耗松弛认证与场景热核复用流程",
     "4.5　求解流程",
     "M0 直接搜索带温限的原问题。M1 与 M2 先移去温限，保留期限与连续能耗评价，再完整复核松弛最低候选。全域最低候选复核安全时可据此认证最优安全能耗；超温或未决则回退原约束搜索。",
     "M2 复用期限拒绝记录或入口温度无关的场景算子，每次调用仍传入当前前缀的实际入口温度。限时搜索按实际完成范围报告已复核安全解、下界与状态。"),
    ("4-2", "fig08_budget", "120 s 预算下的部署覆盖与全库认证耗时",
     "4.6.2（2）—（3）　开发与留出工况",
     "每个工况含 81 个部署。四个开发工况各运行一次，M2 均完成全库认证，用时 49.41–56.49 s。M0、M1 在预算内只完成部分部署。",
     "H1、H2 各列两次有效观测，M2 的全库认证时刻为 47.37–61.96 s。星号所示的 H2 第二次 M1 取有效补跑的 40 个部署。原中断记录曾到达 41 个；第三轮未执行。"),
    ("4-3", "fig07_fixed", "固定四部署的场景核构建次数与墙钟耗时",
     "4.6.2（4）　固定工作量开销",
     "25 °C、正序原驻留，M1 和 M2 各运行一次，按相同顺序处理 A、C、D000、D001。引入复用后，场景核构建由 280 次降至 199 次，含冷启动的总墙钟由 21.06 s 降至 18.53 s。",
     "右图各分项互斥。两法得到相同的四部署最优安全能耗 43.110757928 J。首次安全解时刻分别为 13.88 s 和 14.03 s。"),
    ("4-4", "fig09_progress", "四个开发工况下的搜索覆盖进度",
     "4.6.2（4）　搜索进度",
     "横轴为自冷启动起的实际墙钟，阶梯在一个部署完成时上升。四个工况分别以 81 个部署为目标，共使用 12 次开发运行的 581 个主搜索部署完成事件。",
     "菱形表示 M2 的全库证书事件。取得证书的曲线止于该时刻，触及预算的曲线保持末次完成数至 120 s。各曲线终点可与图 4-2(a)(b) 逐项对照。"),
]


def register_font():
    paths = [Path("C:/Windows/Fonts/msyh.ttc"),
             Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
             Path("/System/Library/Fonts/Supplemental/Songti.ttc")]
    for path in paths:
        if path.is_file():
            pdfmetrics.registerFont(TTFont(FONT, str(path), subfontIndex=0))
            return
    raise RuntimeError("Install a Chinese TrueType font and add its path to register_font().")


def wrap(text, size):
    lines, line = [], ""
    for token in re.findall(r"[A-Za-z0-9.,%/°–-]+|.", text):
        if line and pdfmetrics.stringWidth(line + token, FONT, size) > BODY and token not in "，。；、）":
            lines.append(line.rstrip())
            line = ""
        line += token.lstrip() if not line else token
    return lines + [line.rstrip()]


def text_at(c, x, y, text, size, color):
    c.setFillColor(HexColor(color))
    c.setFont(FONT, size)
    c.drawString(x, y, text)


def safe_table(c, y):
    with (ROOT / "data/fig04_peak_certificates.csv").open(encoding="utf-8-sig") as f:
        peaks = {r["node"]: float(r["peak_upper_C"]) for r in csv.DictReader(f)
                 if r["deployment"] == "D001" and r["code"] == "448"}
    xs = [MARGIN + BODY * v for v in (0.02, .44, .58, .72, .87)]
    c.setFillColor(HexColor("#EDF5F4"))
    c.rect(MARGIN, y - 6, BODY, 18, stroke=0, fill=1)
    for x, s in zip(xs, ["安全参照  D001 / 448", "CPU", "GPU", "DLA0", "DLA1"]):
        text_at(c, x, y, s, 9.3, DARK)
    for x, s in zip(xs, ["连续峰温认证上界（°C）"] + [f"{peaks[k]:.4f}" for k in ("cpu","gpu","dla0","dla1")]):
        text_at(c, x, y-19, s, 9.4, DARK)


def build():
    register_font()
    writer = PdfWriter()
    writer.add_metadata({"/Title": "第三、四章图册｜面向端侧推理的热感知高能效任务调度研究",
                         "/Subject": "冻结归档 b8187776 · 第一阶段制图"})
    for index, (number, stem, title, section, first, second) in enumerate(FIGURES, 1):
        figure = PdfReader(ROOT / (stem + ".pdf")).pages[0]
        scale = BODY / float(figure.mediabox.width)
        image_h = scale * float(figure.mediabox.height)
        paragraphs = [wrap(first, 10.7), wrap(second, 10.7)]
        extra_h = 49 if number == "3-3" else 0
        height = 122 + image_h + 16 * sum(map(len, paragraphs)) + 61 + extra_h
        layout = BytesIO()
        c = canvas.Canvas(layout, pagesize=(WIDTH, height))
        text_at(c, MARGIN, height-31, "第三章  /  联合调度" if number.startswith("3") else "第四章  /  联合搜索", 10, ACCENT)
        c.setFont(FONT, 9)
        c.setFillColor(HexColor(MUTED))
        c.drawRightString(WIDTH-MARGIN, height-31, section)
        text_at(c, MARGIN, height-67, "图 " + number + "　" + title, 17.4, DARK)
        c.setStrokeColor(HexColor(LINE))
        c.line(MARGIN, height-83, WIDTH-MARGIN, height-83)
        bottom = height - 96 - image_h
        y = bottom - 22
        for lines in paragraphs:
            for line in lines:
                text_at(c, MARGIN, y, line, 10.7, DARK)
                y -= 16
            y -= 5
        if extra_h:
            safe_table(c, y-7)
        c.line(MARGIN, 36, WIDTH-MARGIN, 36)
        text_at(c, MARGIN, 19, "面向端侧推理的热感知高能效任务调度研究", 8.5, MUTED)
        c.drawRightString(WIDTH-MARGIN, 19, f"{index} / {len(FIGURES)}")
        c.showPage()
        c.save()
        layout.seek(0)
        page = PdfReader(layout).pages[0]
        page.merge_transformed_page(figure, Transformation().scale(scale).translate(MARGIN, bottom))
        writer.add_page(page)
        writer.add_outline_item("图 " + number + "　" + title, index-1)
    with (ROOT / "thesis_figures.pdf").open("wb") as out:
        writer.write(out)


if __name__ == "__main__":
    build()
