import ctypes
from datetime import datetime, timedelta
from multiprocessing import RawArray, Queue
import multiprocessing.synchronize
import os
from typing import TypedDict
import queue
import numpy as np
from config import (
    DAS_CONFIG,
    SAVE_CONFIG,
)
from utils import DataBuffer, log


class DataHandler:
    class _BufferDict(TypedDict):
        buffer: ctypes.Array[ctypes.c_byte]
        offset: int

    def __init__(self, pingpangBuffers: dict[str, list[DataBuffer]], taskQueue: Queue):
        self._pingpangBuffers = pingpangBuffers
        self._taskQueue = taskQueue

        self._saving = False
        self._saveCache: dict[str, DataHandler._BufferDict] = {}
        for name in SAVE_CONFIG["targets"]:
            self._saveCache[name] = {
                "buffer": RawArray(
                    ctypes.c_byte,
                    DAS_CONFIG["targets"][name]["sampleRate"]
                    * SAVE_CONFIG["targets"][name]["interval"]
                    * len(DAS_CONFIG["validPointRange"])
                    * DAS_CONFIG["dtype"].itemsize,
                ),
                "offset": 0,  # 缓存的偏移量"
            }

    def save_data(self, name: str, dataBuffer: DataBuffer, saveTime: datetime):
        if not name in SAVE_CONFIG["targets"]:
            return
        # saveTime为结束时间，保存的文件冗余一定的时间，确保所需的数据都能保存到文件中
        if not (
            SAVE_CONFIG["begin"]
            - timedelta(seconds=SAVE_CONFIG["targets"][name]["interval"])
            <= saveTime
            <= SAVE_CONFIG["end"]
            + timedelta(seconds=SAVE_CONFIG["targets"][name]["interval"])
        ):
            if self._saving:
                log.info("停止保存数据")
                self._saving = False
            return
        if not self._saving:
            self._saving = True
            log.info("开始保存数据")
        addr = (
            ctypes.addressof(self._saveCache[name]["buffer"])
            + self._saveCache[name]["offset"]
        )
        with dataBuffer["lock"]:
            ctypes.memmove(addr, dataBuffer["buffer"], len(dataBuffer["buffer"]))
        self._saveCache[name]["offset"] += len(dataBuffer["buffer"])
        # 还未满则先不保存
        if self._saveCache[name]["offset"] != len(self._saveCache[name]["buffer"]):
            return
        self._saveCache[name]["offset"] = 0
        filePath = f"{SAVE_CONFIG['path']}/{SAVE_CONFIG['targets'][name]['prefix']}{saveTime.strftime('%Y-%m-%d_%H-%M-%S.%f')[:-3]}.dat"
        if os.path.exists(filePath):
            log.warning(f"文件 {filePath} 已存在，将被覆盖")
            return
        with open(filePath, "wb") as f:
            os.write(f.fileno(), self._saveCache[name]["buffer"])

    def cal_test(self, name: str, dataBuffer: DataBuffer):
        if name != "振动解调数据":
            return
        with dataBuffer["lock"]:
            data = np.frombuffer(dataBuffer["buffer"], dtype=DAS_CONFIG["dtype"]).copy()
        # 时间轴上做FFT
        data = np.fft.fft(data.reshape(-1, len(DAS_CONFIG["validPointRange"])), axis=1)

    def on_command(self, exit_event: multiprocessing.synchronize.Event):
        while not exit_event.is_set():
            try:
                (name, pingpong, recordTime) = self._taskQueue.get(timeout=1)
                self.save_data(name, self._pingpangBuffers[name][pingpong], recordTime)
                self.cal_test(name, self._pingpangBuffers[name][pingpong])
            except queue.Empty:
                pass
