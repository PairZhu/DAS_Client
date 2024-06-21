import re
import numpy as np
import matplotlib.pyplot as plt

# 中文支持
plt.rcParams["font.sans-serif"] = ["SimHei"]

PRECISION = 0.0001

with open("output.log", "r", encoding="utf-8") as f:
    log = f.read()

pattern = re.compile(
    r"\d{4}-\d{2}-\d{2} (?P<time>\d{2}:\d{2}:\d{2}) - INFO - 丢帧数: -?\d+, 丢帧率: (?P<drop_rate>[\d\.]+)%, 全局丢帧率: (?P<global_drop_rate>[\d\.]+)%"
)

matches = pattern.findall(log)

time_stamps = [match[0] for match in matches]
frame_drop_rates = np.array([float(match[1]) for match in matches])
global_frame_drop_rates = np.array([float(match[2]) for match in matches])


# 绘制短时丢帧率变化
avg_frame_drop_rate = np.mean(frame_drop_rates)
mid_frame_drop_rate = np.median(frame_drop_rates)
max_frame_drop_rate = np.max(frame_drop_rates)

max_rate = max_frame_drop_rate / 0.8

plt.plot(frame_drop_rates, label="frame drop rate")
plt.axhline(
    avg_frame_drop_rate,  # type: ignore
    color="r",
    linestyle="--",
    label=f"均值 = {avg_frame_drop_rate:.4f}%",
)
plt.axhline(
    mid_frame_drop_rate,  # type: ignore
    color="g",
    linestyle="--",
    label=f"中位数 = {mid_frame_drop_rate:.4f}%",
)
plt.axhline(
    max_frame_drop_rate,
    color="b",
    linestyle="--",
    label=f"最大值 = {max_frame_drop_rate:.4f}%",
)
plt.legend()
plt.title("丢帧率变化")
# 修改y坐标刻度标签
yticks = np.arange(0, max_rate, 0.01)
plt.yticks(yticks, [f"{i:.2f}%" for i in yticks])
# 修改x坐标刻度标签
xticks = np.arange(0, len(frame_drop_rates), 20)
plt.xticks(xticks, [time_stamps[i] for i in xticks])
plt.show()

# 绘制全局丢帧率变化
max_global_frame_drop_rate = np.max(global_frame_drop_rates)
max_rate = max_global_frame_drop_rate / 0.8

plt.plot(global_frame_drop_rates, label="global frame drop rate")
plt.title("全局丢帧率变化")
# 修改y坐标刻度标签
yticks = np.arange(0, max_rate, 0.002)
plt.yticks(yticks, [f"{i:.3f}%" for i in yticks])
# 修改x坐标刻度标签
xticks = np.arange(0, len(global_frame_drop_rates), 20)
plt.xticks(xticks, [time_stamps[i] for i in xticks])
plt.show()


# 绘制分布直方图
plt.hist(frame_drop_rates, bins=int((max_rate) / PRECISION / 10))
plt.title("丢帧率分布直方图")
# 修改x坐标刻度标签
xticks = np.arange(0, max_rate + 0.02, 0.01)
plt.xticks(xticks, [f"{i:.2f}%" for i in xticks])
plt.show()
