# coding=utf-8

import itertools
import functools
import time
import asyncio
import numpy as np
import math
import ctypes
from multiprocessing import Process, RawArray, Lock, Queue, Event
import multiprocessing.synchronize
from typing import TypedDict
import os
import atexit
from datetime import datetime, timedelta
from das_udp import ServerProtocol
from command import RecvCommand, SendCommand
from config import (
    DAS_CONFIG,
    REMOTE_ADDRESS,
    LOCAL_ADDRESS,
    PINGPONG_SIZE,
    FRAME_COUNTER,
    HANDLE_INTERVAL,
    SAVE_CONFIG,
    PLOT_CONFIG,
    STRICT_BEGIN_TARGET,
)
from data_handler import DataHandler
from utils import DataBuffer, log


class FrameCounter:
    def __init__(self):
        self._frames = 0
        self._totalFrames = 0
        self._totalBeginTime = time.time()
        self._beginTime = None
        self._interval = FRAME_COUNTER["interval"]
        self._theoSampleRate = DAS_CONFIG["targets"][FRAME_COUNTER["gist"]][
            "sampleRate"
        ]
        self._maxLossRate = 0

    def on_command(self, cmd: RecvCommand):
        if cmd.name != FRAME_COUNTER["gist"]:
            return
        if self._beginTime is None:
            self._beginTime = time.time()
            self._totalBeginTime = time.time()
        self._frames += 1
        self._totalFrames += 1

    def update(self):
        if self._beginTime is None:
            return
        theoFrame = round((time.time() - self._beginTime) * self._theoSampleRate)
        lossRate = max(1 - self._frames / theoFrame, 0)
        totalTheoFrame = round(
            (time.time() - self._totalBeginTime) * self._theoSampleRate
        )
        totalLossRate = max(1 - self._totalFrames / totalTheoFrame, 0)
        log.debug(
            f"丢帧数: {theoFrame - self._frames}, 丢帧率: {lossRate*100:.4f}%, 历史最大丢帧率: {self._maxLossRate*100:.4f}%, 全局丢帧数: {totalTheoFrame - self._totalFrames}, 全局丢帧率: {totalLossRate*100:.4f}%"
        )
        if time.time() - self._beginTime >= self._interval:
            log.info(
                f"丢帧数: {theoFrame - self._frames}, 丢帧率: {lossRate*100:.4f}%, 全局丢帧数: {totalTheoFrame - self._totalFrames}, 全局丢帧率: {totalLossRate*100:.4f}%"
            )
            self._maxLossRate = max(self._maxLossRate, lossRate)
            self._frames = 0
            self._beginTime = time.time()


def das_communicate(
    protocol: ServerProtocol, exit_event: multiprocessing.synchronize.Event
):
    async def inner():
        nonlocal protocol
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: protocol, local_addr=LOCAL_ADDRESS
        )
        transport.sendto(SendCommand("DAS配置", DAS_CONFIG).bytesData, REMOTE_ADDRESS)
        # 等待数据接收
        await asyncio.sleep(0.2)
        transport.sendto(SendCommand("高速数据开始发送").bytesData, REMOTE_ADDRESS)
        await asyncio.sleep(0.2)
        log.info("开始接收数据")
        frameCounter = FrameCounter()
        protocol.on("command", frameCounter.on_command)
        protocol.enable = True
        while not exit_event.is_set():
            await asyncio.sleep(1)
            frameCounter.update()

        log.info("停止接收数据")
        transport.sendto(SendCommand("高速数据停止发送").bytesData, REMOTE_ADDRESS)

    asyncio.run(inner())


class ErrorLogger:
    def __init__(self, minInterval=1):
        self._lastWarnTime = None
        self._interval = minInterval

    def on_error(self, e: Exception):
        if (
            self._lastWarnTime is None
            or time.time() - self._lastWarnTime >= self._interval
        ):
            log.error(f"无效命令: {e}")
            self._lastWarnTime = time.time()


class DataRecorder:
    class _BufferDict(TypedDict):
        data: list[DataBuffer]
        offset: int
        pingpong: int

    def __init__(self, dataBuffers: dict[str, list[DataBuffer]], taskQueue):
        self._bufferDicts: dict[str, DataRecorder._BufferDict] = {}
        for name, dataBuffer in dataBuffers.items():
            self._bufferDicts[name] = {
                "data": dataBuffer,
                "offset": 0,
                "pingpong": 0,
            }
            dataBuffer[0]["lock"].acquire()
        self._taskQueue = taskQueue

    def on_command(self, cmd: RecvCommand):
        if STRICT_BEGIN_TARGET and datetime.now() < SAVE_CONFIG["begin"] - timedelta(
            seconds=SAVE_CONFIG["targets"][STRICT_BEGIN_TARGET]["interval"]
        ):
            return
        if not cmd.name in DAS_CONFIG["targets"]:
            return
        if len(cmd.body) != DAS_CONFIG["dataSize"] * DAS_CONFIG["dtype"].itemsize:
            log.error(f"无效的数据尺寸: {len(cmd.body)}")
            return
        bufferDict = self._bufferDicts[cmd.name]
        addr = (
            ctypes.addressof(bufferDict["data"][bufferDict["pingpong"]]["buffer"])
            + bufferDict["offset"]
        )
        BYTE_SIZE = len(DAS_CONFIG["validPointRange"]) * DAS_CONFIG["dtype"].itemsize
        ctypes.memmove(addr, cmd.body, BYTE_SIZE)
        bufferDict["offset"] += BYTE_SIZE
        if bufferDict["offset"] == len(
            bufferDict["data"][bufferDict["pingpong"]]["buffer"]
        ):
            bufferDict["data"][bufferDict["pingpong"]]["lock"].release()
            self._taskQueue.put((cmd.name, bufferDict["pingpong"], datetime.now()))
            bufferDict["offset"] = 0
            bufferDict["pingpong"] = (bufferDict["pingpong"] + 1) % PINGPONG_SIZE
            bufferDict["data"][bufferDict["pingpong"]]["lock"].acquire()


class PlotData:
    def __init__(self, dataBuffers: dict[str, DataBuffer]):
        self._dataBuffers = dataBuffers

    def on_command(self, cmd: RecvCommand):
        if not cmd.name in self._dataBuffers:
            return

        if not self._dataBuffers[cmd.name]["lock"].acquire(block=False):
            return
        addr = (
            ctypes.addressof(self._dataBuffers[cmd.name]["buffer"])
            + DAS_CONFIG["validPointRange"].start
        )
        ctypes.memmove(addr, cmd.body, len(self._dataBuffers[cmd.name]["buffer"]))
        self._dataBuffers[cmd.name]["lock"].release()


def show_plot(dataBuffers: dict[str, DataBuffer]):
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    import matplotlib.colors as mcolors

    plt.rcParams["font.family"] = "SimHei"
    plt.rcParams["axes.unicode_minus"] = False

    H_WHITESPACE = 0.05
    V_WHITESPACE = 0.05

    def log_trans(x):
        return np.log10(np.abs(x) + 1e-6)

    def update_plot(name, datasets, _):
        nonlocal dataBuffers
        for i, chart in enumerate(charts):
            with dataBuffers[name]["lock"]:
                data = (
                    np.frombuffer(
                        dataBuffers[name]["buffer"],
                        dtype=DAS_CONFIG["dtype"],
                    )
                    / 255
                    * np.pi
                )
            if chart["type"] == "heat":
                heatData = np.roll(datasets[i].get_array(), -1, axis=0)
                heatData[-1, :] = log_trans(data)
                datasets[i].set_data(heatData)
            elif chart["type"] == "space":
                datasets[i].set_ydata(data)
            elif chart["type"] == "time":
                timeData = np.roll(datasets[i].get_ydata(), -1)
                timeData[-1] = data[chart["point"]]
                datasets[i].set_ydata(timeData)
            else:
                raise ValueError(f"无效的图表类型: {chart['type']}")
        return datasets

    # 保持对动画的引用，防止被回收
    anis = []

    for name, target in PLOT_CONFIG["targets"].items():
        charts = target["charts"]
        nrows = math.ceil(len(charts) ** 0.5)
        ncols = math.ceil(len(charts) / nrows)
        fig, axes = plt.subplots(nrows=nrows, ncols=ncols)
        axes = axes.flatten()
        plt.subplots_adjust(
            left=H_WHITESPACE,
            right=1 - H_WHITESPACE,
            bottom=V_WHITESPACE,
            top=1 - V_WHITESPACE,
            wspace=0.15,
            hspace=0.25,
        )
        fig.canvas.manager.set_window_title(name)  # type: ignore
        datasets = []
        for i, chart in enumerate(charts):
            if chart["type"] == "heat":
                data = axes[i].imshow(
                    log_trans(
                        np.zeros((chart["size"], len(DAS_CONFIG["validPointRange"])))
                    ),
                    aspect="auto",
                    norm=mcolors.Normalize(
                        vmin=log_trans(0),
                        vmax=log_trans(max(-target["min"], target["max"])),
                    ),
                )
                datasets.append(data)
                axes[i].set_title("热力图")
            elif chart["type"] == "space":
                (data,) = axes[i].plot(np.zeros(len(DAS_CONFIG["validPointRange"])))
                datasets.append(data)
                axes[i].set_xlim(
                    DAS_CONFIG["validPointRange"].start,
                    DAS_CONFIG["validPointRange"].stop - 1,
                )
                axes[i].set_ylim(target["min"], target["max"])
                axes[i].set_title("空间波形")
            elif chart["type"] == "time":
                (data,) = axes[i].plot(np.zeros(chart["size"]))
                datasets.append(data)
                axes[i].set_xlim(0, chart["size"] - 1)
                axes[i].set_ylim(target["min"], target["max"])
                axes[i].set_title(f"时间波形(点位:{chart['point']})")
            else:
                raise ValueError(f"无效的图表类型: {chart['type']}")

        # 删除多余的图表
        for i in range(len(charts), len(axes)):
            fig.delaxes(axes[i])

        anis.append(
            animation.FuncAnimation(
                fig,
                functools.partial(update_plot, name, datasets),
                interval=PLOT_CONFIG["interval"],
                blit=True,
                frames=itertools.cycle([None]),  # type: ignore
                save_count=0,
            )
        )

    plt.show()


def main():
    if not os.path.exists(SAVE_CONFIG["path"]):
        os.mkdir(SAVE_CONFIG["path"])

    protocol = ServerProtocol()
    protocol.on("error", ErrorLogger().on_error)

    pingpangBuffers: dict[str, list[DataBuffer]] = {}
    for name, params in DAS_CONFIG["targets"].items():
        pingpangBuffers[name] = [
            {
                "buffer": RawArray(
                    ctypes.c_byte,
                    int(
                        params["sampleRate"]
                        * HANDLE_INTERVAL
                        * len(DAS_CONFIG["validPointRange"])
                        * DAS_CONFIG["dtype"].itemsize,
                    ),
                ),
                "lock": Lock(),
            }
            for _ in range(PINGPONG_SIZE)
        ]
    taskQueue = Queue()
    protocol.on("command", DataRecorder(pingpangBuffers, taskQueue).on_command)

    if PLOT_CONFIG["enable"]:
        currentBuffers: dict[str, DataBuffer] = {}
        for name in PLOT_CONFIG["targets"]:
            currentBuffers[name] = {
                "buffer": RawArray(
                    ctypes.c_byte,
                    len(DAS_CONFIG["validPointRange"]) * DAS_CONFIG["dtype"].itemsize,
                ),
                "lock": Lock(),
            }
        protocol.on("command", PlotData(currentBuffers).on_command)

    # 退出事件
    exit_event = Event()
    # 创建数据处理进程
    dataHandler = DataHandler(pingpangBuffers, taskQueue)
    handle = Process(target=dataHandler.on_command, args=(exit_event,), daemon=True)
    handle.start()
    # 创建数据接收进程
    communicator = Process(
        target=das_communicate,
        args=(
            protocol,
            exit_event,
        ),
        daemon=True,
    )
    communicator.start()

    def on_exit():
        exit_event.set()
        handle.join()
        communicator.join()

    atexit.register(on_exit)

    if PLOT_CONFIG["enable"]:
        show_plot(currentBuffers)
    else:
        try:
            communicator.join()
        except KeyboardInterrupt:
            raise


if __name__ == "__main__":
    main()
