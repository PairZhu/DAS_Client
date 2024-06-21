import shutil
from datetime import datetime
import logging
from logging.handlers import QueueHandler, QueueListener
import os
import re
import queue


class RollingStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            # 根据日志级别选择格式化输出
            if record.levelno == logging.DEBUG:
                msg = record.getMessage()
            else:
                msg = self.format(record)

            stream = self.stream
            # 清空当前行
            logStr = "\r" + " " * (shutil.get_terminal_size().columns - 2) + "\r"
            # 滚动输出消息
            logStr += msg
            if record.levelno != logging.DEBUG:
                logStr += "\n"
            stream.write(logStr)
            if record.levelno == logging.DEBUG:
                stream.flush()
        except Exception:
            self.handleError(record)


def getThreadLogger(name: str | None = None) -> tuple[logging.Logger, QueueListener]:
    logQueue = queue.Queue()
    queueHandler = QueueHandler(logQueue)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    streamHandler = RollingStreamHandler()
    streamHandler.setLevel(logging.DEBUG)
    streamHandler.setFormatter(formatter)

    fileHandler = logging.FileHandler("output.log", encoding="utf-8")
    fileHandler.setLevel(logging.INFO)
    fileHandler.setFormatter(formatter)

    listener = QueueListener(
        logQueue, streamHandler, fileHandler, respect_handler_level=True
    )
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(queueHandler)

    return logger, listener


def bytes_to_hex(bytesData: bytes) -> str:
    return " ".join(f"0x{b:02X}" for b in bytesData)


def extract_timestamp(filename):
    # 可能为路径，也可能为文件名，取出文件名
    filename = os.path.basename(filename)
    match = re.search(
        r"(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.(\d{3})", filename
    )
    if not match:
        raise ValueError(f"Invalid filename format: {filename}")
    year, month, day, hour, minute, second, millisecond = match.groups()
    dt = datetime(
        int(year),
        int(month),
        int(day),
        int(hour),
        int(minute),
        int(second),
        int(millisecond) * 1000,
    )
    return dt, dt.timestamp()
