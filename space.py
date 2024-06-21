import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
import os
import pandas as pd
from datetime import timedelta
from utils import extract_timestamp
from config import SAVE_CONFIG, DAS_CONFIG


FS = DAS_CONFIG["targets"]["振动解调数据"]["sampleRate"]
SPACE_INTERVAL = 5
T = SAVE_CONFIG["targets"]["振动解调数据"]["interval"]

FILE_PATH = SAVE_CONFIG["path"]

BEGIN_TIME = SAVE_CONFIG["begin"]
END_TIME = SAVE_CONFIG["begin"] + timedelta(seconds=2 * 60)

DOWN_SAMPLE = 100

# 读取文件列表
fileDict = {}
for file in os.listdir(FILE_PATH):
    dt, _ = extract_timestamp(file)
    dt = dt.replace(microsecond=0)
    fileDict[dt] = file


# 读取数据
data = []
# 文件的时间代表结束时间，因此BEGIN_TIME需要加上T
timeRange = pd.date_range(BEGIN_TIME + pd.Timedelta(seconds=T), END_TIME, freq=f"{T}s")
for t in tqdm(timeRange, desc="Reading data"):
    filename = f"{FILE_PATH}/{fileDict[t.to_pydatetime()]}"
    # 读取数据
    fileData = (
        # 相邻的数据是空间上相邻的
        np.fromfile(filename, dtype="<i2").reshape(int(FS * T), -1)
        # 转置，使得第一个维度是空间维度
    ).T
    fileData = (
        # 对时间降采样
        fileData[:, ::DOWN_SAMPLE]
        # 转为相位值
        / 2**8
        * np.pi
    )
    fileData = np.abs(fileData)
    data.append(fileData)

# 在第二个维度上拼接（时间维度）
data = np.concatenate(data, axis=1)
data = np.log10(data + 1e-5)
# 绘制热力图
plt.imshow(data, aspect="auto", cmap="jet")
# 设置映射范围
plt.clim(-5, 2)
# 设置横坐标刻度和标签
x_label_freq = (END_TIME - BEGIN_TIME).total_seconds() / 10
# [1,2,5,10,15,30] (秒，分，时为单位)
FREQ_RULE = [1, 2, 5, 10, 15, 30]
FREQ_UNIT = [1, 60, 3600]
for unit in FREQ_UNIT:
    for rule in FREQ_RULE:
        if x_label_freq / unit <= rule:
            x_label_freq = rule * unit
            break
    if x_label_freq / unit <= rule:
        break
else:
    x_label_freq = int(x_label_freq // unit) * unit
deltaTime = pd.to_timedelta(f"{x_label_freq}s")
timeFactor = deltaTime / (END_TIME - BEGIN_TIME)
x_labels = pd.date_range(BEGIN_TIME, END_TIME, freq=deltaTime).strftime("%H:%M:%S")
x_ticks = np.arange(0, data.shape[1] + 1, timeFactor * data.shape[1])
plt.xticks(x_ticks, x_labels)  # type: ignore
# 设置纵坐标刻度和标签
y_ticks = np.arange(0, data.shape[0], 200)
y_labels = [f"{i*SPACE_INTERVAL}m" for i in y_ticks]
plt.yticks(y_ticks, y_labels)
# 添加颜色条
plt.colorbar(
    orientation="horizontal", label="log10(Amplitude+1e-5)", aspect=100, pad=0.05
)
plt.show()
