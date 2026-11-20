"""Draw the chapter 3 physical model and chapter 4 search flows from the archived protocols."""
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from figure_style import BLUE, GRAY, INK, ORANGE, TEAL, save, setup


BLUE_FILL = "#EDF3F8"
TEAL_FILL = "#E8F5F2"
NEUTRAL_FILL = "#F5F7F8"
WARM_FILL = "#FCF2E9"


def canvas(height):
    width = 7.6
    figure = plt.figure(figsize=(width, height), facecolor="white")
    axes = figure.add_axes([0, 0, 1, 1])
    axes.set(xlim=(0, width), ylim=(height, 0))
    axes.axis("off")
    return figure, axes


def box(axes, x, y, width, height, edge=GRAY, fill="white", linewidth=0.95):
    axes.add_patch(FancyBboxPatch(
        (x, y), width, height, boxstyle="round,pad=0,rounding_size=0.055",
        facecolor=fill, edgecolor=edge, linewidth=linewidth, zorder=2))


def label(axes, x, y, value, size=10, color=INK, bold=False, align="center"):
    axes.text(x, y, value, ha=align, va="center", fontsize=size, color=color,
              fontweight="bold" if bold else "normal", linespacing=1.37, zorder=4)


def card(axes, x, y, width, height, title, content, color=BLUE, fill=BLUE_FILL):
    box(axes, x, y, width, height, color, fill)
    title_fraction = 0.30 if "\n" in content else 0.32
    body_fraction = 0.69 if "\n" in content else 0.71
    label(axes, x + width / 2, y + height * title_fraction, title, 10.5, color, True)
    label(axes, x + width / 2, y + height * body_fraction, content, 9.1)


def path_arrow(axes, points, color=GRAY, linewidth=1.05):
    if len(points) > 2:
        axes.plot(*zip(*points[:-1]), color=color, lw=linewidth, zorder=1,
                  solid_joinstyle="round", solid_capstyle="round")
    axes.add_patch(FancyArrowPatch(
        points[-2], points[-1], arrowstyle="-|>", mutation_scale=9.8,
        color=color, lw=linewidth, shrinkA=0, shrinkB=0.3, zorder=3))


def physical_model():
    fig, ax = canvas(4.70)
    card(ax, 0.17, 0.12, 3.36, 0.72, "给定任务与平台",
         "请求到达、场景顺序及驻留、异构资源", GRAY, NEUTRAL_FILL)
    card(ax, 3.77, 0.12, 3.66, 0.72, "候选联合决策",
         "全窗常驻部署 × 四段 CPU/GPU/DLA 频档")
    ax.plot([1.85, 1.85, 5.60, 5.60], [0.84, 0.98, 0.98, 0.84],
            color=GRAY, lw=1.05)
    path_arrow(ax, [(3.80, 0.98), (3.80, 1.15)])
    card(ax, 0.17, 1.15, 7.26, 0.65, "按请求与资源竞争生成执行事件",
         "计算、传输与空闲事件给出请求的完成时刻，并确定各节点的分段活动功率")
    path_arrow(ax, [(1.10, 1.80), (1.10, 2.11)])
    path_arrow(ax, [(4.93, 1.80), (4.93, 2.11)])
    box(ax, 0.17, 2.11, 1.90, 1.45, GRAY, NEUTRAL_FILL)
    label(ax, 1.12, 2.43, "逐请求检查期限", 10.4, INK, True)
    label(ax, 1.12, 2.97, "全部请求均完成\n完成时刻 ≤ 绝对期限", 9.2)
    box(ax, 2.30, 2.11, 5.13, 1.45, TEAL, TEAL_FILL)
    label(ax, 4.865, 2.37, "四节点连续热模型与温度相关漏电", 10.6, TEAL, True)
    start = 2.48
    for index in range(4):
        x = start + index * 1.27
        box(ax, x, 2.66, 0.92, 0.35, TEAL, "white", 0.75)
        label(ax, x + 0.46, 2.835, f"场景段 {index + 1}", 8.8)
        if index < 3:
            path_arrow(ax, [(x + 0.93, 2.835), (x + 1.25, 2.835)], TEAL)
    label(ax, 4.865, 3.29, "从 30 °C 起逐段传递四节点末温，累计整板能耗", 9.15)
    ax.plot([1.12, 1.12, 4.865, 4.865], [3.56, 3.73, 3.73, 3.56],
            color=GRAY, lw=1.05)
    path_arrow(ax, [(3.80, 3.73), (3.80, 3.89)])
    card(ax, 0.17, 3.89, 7.26, 0.68, "在满足期限与连续温限的候选中选择最低整板能耗",
         "四节点全窗峰温上界均 ≤ 80 °C，计能覆盖 10 s 服务与 40 ms 尾窗",
         TEAL, TEAL_FILL)
    save(fig, "fig01_joint")
    plt.close(fig)


def search_methods():
    fig, ax = canvas(6.85)
    label(ax, 0.18, 0.17, "（a）求解与认证", 10.6, INK, True, "left")
    card(ax, 0.18, 0.38, 2.46, 0.83, "M0   原温限约束搜索",
         "逐部署构建场景核\n并筛除超期动作", BLUE, BLUE_FILL)
    card(ax, 3.46, 0.38, 3.96, 0.83, "M1 / M2   连续能耗松弛搜索",
         "暂时移去温限，保留所有期限合法前缀\n传递真实入口温度并累计含漏电的能耗",
         TEAL, TEAL_FILL)
    path_arrow(ax, [(5.44, 1.21), (5.44, 1.48)], TEAL)
    card(ax, 3.46, 1.48, 3.96, 0.82, "已覆盖域最低候选变化时完整回放",
         "安全则更新已认证上界\n超温或未决则继续扫描其余部署",
         TEAL, TEAL_FILL)
    path_arrow(ax, [(5.44, 2.30), (5.44, 2.59)], TEAL)
    path_arrow(ax, [(1.41, 1.21), (1.41, 2.59)], BLUE)
    card(ax, 3.46, 2.59, 3.96, 0.76, "全域松弛最低候选是否安全？",
         "目标域扫描完成后，取完整回放的判定", ORANGE, WARM_FILL)
    card(ax, 0.18, 2.59, 2.46, 0.76, "原温限约束路径",
         "检查各前缀的峰温包络\n未能判定时用原热模型积分",
         BLUE, BLUE_FILL)
    path_arrow(ax, [(3.46, 3.00), (2.64, 3.00)], ORANGE)
    label(ax, 3.05, 2.83, "超温／未决", 7.9, ORANGE)
    label(ax, 3.05, 3.17, "从头回退", 7.9, ORANGE)
    path_arrow(ax, [(1.41, 3.35), (1.41, 3.76)], BLUE)
    path_arrow(ax, [(5.44, 3.35), (5.44, 3.76)], TEAL)
    label(ax, 5.72, 3.57, "安全", 8.7, TEAL)
    box(ax, 0.18, 3.76, 7.24, 0.57, TEAL, TEAL_FILL)
    label(ax, 3.80, 4.045, "完成全域搜索并闭合判据后，认证域内最低安全能耗或确认域内无可行解",
          10.1, TEAL, True)
    label(ax, 3.8, 4.57, "同一预算截止时若尚未闭合，报告完成范围、现有界及已复核的安全方案。", 9.1)

    ax.plot([0.18, 7.42], [4.82, 4.82], color="#D5DFE3", lw=0.8)
    label(ax, 0.18, 5.08, "（b）M2 的场景核复用", 10.6, INK, True, "left")
    box(ax, 0.18, 5.42, 2.15, 1.10, BLUE, BLUE_FILL)
    label(ax, 1.255, 5.68, "同工况、同进程查键", 10.0, BLUE, True)
    label(ax, 1.255, 6.10, "冻结哈希、场景索引、频档\n及活跃网络的物理阶段元组", 8.65)
    box(ax, 2.71, 5.36, 2.08, 0.48, GRAY, NEUTRAL_FILL)
    label(ax, 3.75, 5.60, "命中时取已有记录", 9.35)
    box(ax, 2.71, 6.07, 2.08, 0.65, GRAY, NEUTRAL_FILL)
    label(ax, 3.75, 6.39, "未命中时先调度判期限\n合法则编译，再写入记录", 8.95)
    for center in (5.60, 6.395):
        path_arrow(ax, [(2.33, 5.97), (2.51, 5.97), (2.51, center), (2.71, center)])
        path_arrow(ax, [(4.79, center), (4.98, center), (4.98, 5.97), (5.17, 5.97)])
    box(ax, 5.17, 5.42, 2.25, 1.10, TEAL, TEAL_FILL)
    label(ax, 6.295, 5.68, "取期限拒绝标记或场景算子", 9.55, TEAL, True)
    label(ax, 6.295, 6.10, "合法时，将当前前缀的\n实际入口温度传入算子", 9.05)
    save(fig, "fig06_search")
    plt.close(fig)


if __name__ == "__main__":
    setup()
    physical_model()
    search_methods()
