# 只读分析实现记录

首轮分析脚本在读取旧global_updates时遇到KeyError：旧字段是committed_at_s，而非received_at_s。错误发生在写输出前；仅改正分析投影字段，保留原归档字节，未调用生产方法、求解器或热评价器。不存在研究重跑。
