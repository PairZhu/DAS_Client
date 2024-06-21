from datetime import datetime
import numpy as np

# 原始地址
REMOTE_ADDRESS = ("192.168.1.240", 8007)
LOCAL_ADDRESS = ("192.168.1.100", 8009)

# # 转发后的地址
# REMOTE_ADDRESS = ("192.168.1.100", 8009)
# LOCAL_ADDRESS = ("192.168.1.100", 8010)

DAS_CONFIG = {
    "dataSize": 1999,
    # 有效点位范围
    "validPointRange": range(0, 1999),
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
# 确保有效点位范围在数据尺寸内
assert (
    0
    <= DAS_CONFIG["validPointRange"].start
    < DAS_CONFIG["validPointRange"].stop
    <= DAS_CONFIG["dataSize"]
)
# 确保有效点位范围的步长为1
assert DAS_CONFIG["validPointRange"].step == 1

FRAME_COUNTER = {
    "interval": 60,  # 统计间隔，单位: 秒
    "gist": "振动解调数据",  # 统计依据
}
# 确保统计依据在目标字典
assert FRAME_COUNTER["gist"] in DAS_CONFIG["targets"]

# 处理数据的最小时间间隔，所有处理任务都必须是它的整数倍，单位: 秒
HANDLE_INTERVAL = 5
# 如果不为空，则会强制校准该数据的保存开始时间，但在保存时段之前的所有数据均不会被处理
STRICT_BEGIN_TARGET = "振动解调数据"
# 确保STRICT_BEGIN_TARGET在SAVE_CONFIG的目标字典中
assert not STRICT_BEGIN_TARGET or STRICT_BEGIN_TARGET in DAS_CONFIG["targets"]

# 时间范围设置在当前时间前则不会保存数据
SAVE_CONFIG = {
    "begin": datetime.strptime("2024-05-29 15:32:00", "%Y-%m-%d %H:%M:%S"),
    "end": datetime.strptime("2024-05-29 19:21:00", "%Y-%m-%d %H:%M:%S"),
    "path": "data",  # 文件保存路径
    "targets": {
        "振动解调数据": {
            "prefix": "Raw",
            "interval": 10,
        },
        "光强数据": {
            "prefix": "Light",
            "interval": 10,
        },
    },
}
# 确保保存间隔为处理间隔的整数倍
for _, params in SAVE_CONFIG["targets"].items():
    assert params["interval"] % HANDLE_INTERVAL == 0
# 确保保存的目标在目标字典
for target in SAVE_CONFIG["targets"]:
    assert target in DAS_CONFIG["targets"]

PLOT_CONFIG = {
    "enable": True,  # 是否显示图表
    "interval": 20,  # 图表更新间隔，单位: ms
    "target": "振动解调数据",  # 图表显示的数据
}
# 确保显示的目标在目标字典
assert PLOT_CONFIG["target"] in DAS_CONFIG["targets"]

# pingpong缓冲区大小
PINGPONG_SIZE = 3
# 确保缓冲区大小大于等于2
assert PINGPONG_SIZE >= 2

# 声音播放配置
SOUND_CONFIG = {
    "enable": True,  # 是否播放声音
    "target": "振动解调数据",  # 播放声音的数据
    "point": 1900,  # 播放声音的点位
    "max": 1000,  # 声音信号振幅的最大值
}
# 确保播放的目标在目标字典
assert SOUND_CONFIG["target"] in DAS_CONFIG["targets"]
