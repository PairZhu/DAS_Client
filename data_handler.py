import ctypes
from datetime import datetime, timedelta
from multiprocessing import RawArray, Queue
import multiprocessing.synchronize
import os
from typing import TypedDict
import queue
import numpy as np
from config import DAS_CONFIG, SAVE_CONFIG, SOUND_CONFIG, HANDLE_INTERVAL
from utils import DataBuffer, log, butter_bandpass_filter
import sounddevice as sd


class DataHandler:
    class _BufferDict(TypedDict):
        buffer: ctypes.Array[ctypes.c_byte]
        offset: int

    def __init__(self, pingpangBuffers: dict[str, list[DataBuffer]], taskQueue: Queue):
        self._pingpangBuffers = pingpangBuffers
        self._taskQueue = taskQueue

        if SAVE_CONFIG["enable"]:
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
        if SOUND_CONFIG["enable"]:
            self.stream = None

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

    def play_sound(self, name: str, dataBuffer: DataBuffer):
        if name != SOUND_CONFIG["target"]:
            return
        with dataBuffer["lock"]:
            data = (
                np.frombuffer(dataBuffer["buffer"], dtype=DAS_CONFIG["dtype"])
                .reshape(-1, len(DAS_CONFIG["validPointRange"]))[
                    :, SOUND_CONFIG["point"]
                ]
                .astype(np.float32)
            )

        sampleRate = DAS_CONFIG["targets"][name]["sampleRate"]
        data = butter_bandpass_filter(
            data,
            SOUND_CONFIG["lowcut"],
            SOUND_CONFIG["highcut"],
            sampleRate,
            order=SOUND_CONFIG["order"],
        )
        assert data is np.ndarray
        # 绝对值大于最大值的数据置零
        data[np.abs(data) > SOUND_CONFIG["max"]] = 0
        # 数据缩放到[-1, 1]之间
        data = data / SOUND_CONFIG["max"]
        if self.stream is None:
            self.stream = sd.OutputStream(
                samplerate=sampleRate,
                channels=1,
                dtype=np.float32,
                blocksize=sampleRate * HANDLE_INTERVAL,
            )
            self.stream.start()
        self.stream.write(data[: self.stream.write_available])

    def on_command(self, exit_event: multiprocessing.synchronize.Event):
        while not exit_event.is_set():
            try:
                (name, pingpong, recordTime) = self._taskQueue.get(timeout=1)
                if SAVE_CONFIG["enable"]:
                    self.save_data(
                        name, self._pingpangBuffers[name][pingpong], recordTime
                    )
                if SOUND_CONFIG["enable"]:
                    self.play_sound(name, self._pingpangBuffers[name][pingpong])

            except queue.Empty:
                pass
