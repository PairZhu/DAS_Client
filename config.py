from datetime import datetime
import numpy as np
import logging
from typing import Final

# 原始地址
REMOTE_ADDRESS: Final = ("192.168.1.240", 8007)
LOCAL_ADDRESS: Final = ("192.168.1.100", 8009)

# # 使用cpp程序转发后的地址
# REMOTE_ADDRESS = ("192.168.1.100", 8009)
# LOCAL_ADDRESS = ("192.168.1.100", 8010)

DAS_CONFIG: Final = {
    "dataSize": 1999,
    "validPointRange": range(0, 1999),  # 有效点位范围
    "pulseWidth": 100,  # 脉冲宽度, 单位: ns
    "opticalSwitchFlag": [False] * 16 * 2,  # 光开关开启标志
    "opticalSwitchCounterThreshold": 0,  # 光开关计数器阈值
    "targets": {
        "振动解调数据": {
            "sampleRate": 5000,
            "channel": 0,
        },
        "光强数据": {
            "sampleRate": 5000 // 50,
            "channel": 0,
        },
    },
    "dtype": np.dtype("<i2"),
}
# 配置校验
assert (
    0
    <= DAS_CONFIG["validPointRange"].start
    < DAS_CONFIG["validPointRange"].stop
    <= DAS_CONFIG["dataSize"]
), f"{DAS_CONFIG['validPointRange']}不在有效范围内"
assert (
    DAS_CONFIG["validPointRange"].step == 1
), f"{DAS_CONFIG['validPointRange']}步长不为1"

FRAME_COUNTER: Final = {
    "interval": 60,  # 统计间隔，单位: 秒
    "gist": "振动解调数据",  # 统计依据
}
# 配置校验
assert (
    FRAME_COUNTER["gist"] in DAS_CONFIG["targets"]
), f"{FRAME_COUNTER['gist']}未在DAS_CONFIG中定义"

# 处理数据的最小时间间隔，所有处理任务都必须是它的整数倍，单位: 秒
HANDLE_INTERVAL: Final = 1

# 如果不为空，则会强制校准该数据的处理开始时间，但在保存时段之前的所有数据均不会被处理
STRICT_BEGIN_TARGET: Final = "振动解调数据"
# 配置校验
assert (
    not STRICT_BEGIN_TARGET or STRICT_BEGIN_TARGET in DAS_CONFIG["targets"]
), f"{STRICT_BEGIN_TARGET}未在DAS_CONFIG中定义"

SAVE_CONFIG: Final = {
    "enable": False,  # 是否保存数据
    "begin": datetime.strptime("2024-05-29 15:32:00", "%Y-%m-%d %H:%M:%S"),
    "end": datetime.strptime("2024-05-29 19:21:00", "%Y-%m-%d %H:%M:%S"),
    "path": "data",  # 文件保存路径
    "targets": {
        "振动解调数据": {
            "prefix": "Raw",
            "interval": 1,
        },
        "光强数据": {
            "prefix": "Light",
            "interval": 10,
        },
    },
}
# 配置校验
for _, params in SAVE_CONFIG["targets"].items():
    assert (
        params["interval"] % HANDLE_INTERVAL == 0
    ), f"{params['interval']}不是{HANDLE_INTERVAL}的整数倍"
for target in SAVE_CONFIG["targets"]:
    assert target in DAS_CONFIG["targets"], f"{target}未在DAS_CONFIG中定义"

PLOT_CONFIG: Final = {
    "enable": True,  # 是否显示图表
    "interval": 20,  # 图表更新间隔，单位: ms
    "targets": {
        "振动解调数据": {
            "charts": [
                {"type": "heat", "size": 100},
                {"type": "space"},
                {"type": "time", "point": 500, "size": 100},
                {"type": "time", "point": 1000, "size": 100},
            ],
            "min": -20,
            "max": 20,
        },
        "光强数据": {
            "charts": [
                {"type": "heat", "size": 100},
                {"type": "space"},
            ],
            "min": -100,
            "max": 100,
        },
    },
}
PLOT_TYPES: Final = {
    "heat": ["size"],
    "space": [],
    "time": ["point", "size"],
}
# 配置校验
for name, target in PLOT_CONFIG["targets"].items():
    assert name in DAS_CONFIG["targets"], f"{name}未在DAS_CONFIG中定义"
    for chart in target["charts"]:
        assert chart["type"] in PLOT_TYPES, f"{chart['type']}不是有效的图表类型"
        for param in PLOT_TYPES[chart["type"]]:
            assert param in chart, f"{chart['type']}类型缺少{param}参数"
        if "size" in chart:
            assert (
                isinstance(chart["size"], int) and chart["size"] > 0
            ), f"{chart['size']} 不是正整数"
        if "point" in chart:
            assert (
                chart["point"] in DAS_CONFIG["validPointRange"]
            ), f"{chart['point']} 不在有效点位范围内"

# pingpong缓冲区大小
PINGPONG_SIZE: Final = 3
# 配置校验
assert PINGPONG_SIZE >= 2, f"PINGPONG_SIZE必须大于等于2"

# 声音播放配置
SOUND_CONFIG: Final = {
    "enable": True,  # 是否播放声音
    "target": "振动解调数据",  # 播放声音的数据
    "point": 1900,  # 播放声音的点位
    "max": 1000,  # 声音信号振幅的最大值
    "lowcut": 100,  # 低通滤波截止频率
    "highcut": 1000,  # 高通滤波截止频率
    "order": 5,  # 滤波器阶数
}
# 配置校验
assert (
    SOUND_CONFIG["target"] in DAS_CONFIG["targets"]
), f"{SOUND_CONFIG['target']}未在DAS_CONFIG中定义"
assert (
    SAVE_CONFIG["point"] in DAS_CONFIG["validPointRange"]
), f"{SAVE_CONFIG['point']}不在有效点位范围"

# 日志配置
LOG_CONFIG: Final = {
    "level": "DEBUG",  # 动态帧率显示仅在DEBUG等级下显示
    "path": "logs",  # 日志保存路径
    "backupCount": 7,  # 日志备份天数
}
# 配置校验
assert (
    LOG_CONFIG["level"] in logging._nameToLevel
), f"{LOG_CONFIG['level']}不是有效的日志级别"
