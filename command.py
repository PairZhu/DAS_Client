from typing import TypedDict
from config import DAS_CONFIG
from utils import bytes_to_hex

DAS_TYPE = bytes([0x0C, 0x00, 0x00, 0x00])
SEND_START = bytes([0xCC, 0x55])
RECV_START = bytes([0x33, 0x55])
SEND_END = bytes([0xCC, 0xAA])
RECV_END = bytes([0x33, 0xAA])


class _CommandTypeBase(TypedDict):
    head0: bytes
    head1: bytes
    bodyIncluded: bool


class CommandType(_CommandTypeBase, total=False):
    head2: bytes
    bodyLength: int


# 自定义异常类，表示数据尚未接收完成
class DataNotReceived(Exception):
    pass


class Command:
    FRAME_START_LEN = 2
    DEVICE_TYPE_CODE_LEN = 4
    HEAD_0_LEN = 1
    HEAD_1_LEN = 1
    HEAD_2_LEN = 1
    BODY_INCLUDED_LEN = 1
    BODY_INCLUDED_TRUE = bytes([0xDA])
    BODY_INCLUDED_FALSE = bytes([0x00])
    BODY_LENGTH_LEN = 4
    FRAME_END_LEN = 2
    COMMAND_TYPE_DICT: dict[str, CommandType]
    MAX_BODY_LENGTH = 5000

    def __init__(self, bytesData: bytes):
        pos = 0

        def read_bytes(n: int):
            nonlocal pos
            pos += n
            if pos > len(bytesData):
                raise DataNotReceived()
            return bytesData[pos - n : pos]

        self.frameStart: bytes = read_bytes(Command.FRAME_START_LEN)
        self.deviceTypeCode: bytes = read_bytes(Command.DEVICE_TYPE_CODE_LEN)
        self.head0: bytes = read_bytes(Command.HEAD_0_LEN)
        self.head1: bytes = read_bytes(Command.HEAD_1_LEN)
        self.head2: bytes = read_bytes(Command.HEAD_2_LEN)
        bodyIncluded: bytes = read_bytes(Command.BODY_INCLUDED_LEN)
        if bodyIncluded not in [
            Command.BODY_INCLUDED_TRUE,
            Command.BODY_INCLUDED_FALSE,
        ]:
            raise ValueError(f"Invalid bodyIncluded value {bytes_to_hex(bodyIncluded)}")
        self.bodyIncluded: bool = bodyIncluded == Command.BODY_INCLUDED_TRUE
        self.bodyLength: int = (
            int.from_bytes(read_bytes(Command.BODY_LENGTH_LEN), "little", signed=False)
            if self.bodyIncluded
            else 0
        )
        if self.bodyLength > Command.MAX_BODY_LENGTH:
            raise ValueError(f"Body length {self.bodyLength} is too long")
        self.body: bytes = read_bytes(self.bodyLength) if self.bodyIncluded else b""
        self.frameEnd: bytes = read_bytes(Command.FRAME_END_LEN)
        self.bytesData: bytes = bytesData[:pos]
        self.name: str = self.get_type()

    def get_type(self):
        for name, cmdType in self.COMMAND_TYPE_DICT.items():
            if self.head0 != cmdType["head0"] or self.head1 != cmdType["head1"]:
                continue
            if self.head2 != cmdType.get("head2", self.head2):
                continue
            if self.bodyIncluded != cmdType["bodyIncluded"]:
                raise ValueError(
                    f"Command {name} got wrong bodyIncluded value: {self.bodyIncluded}"
                )
            if self.bodyLength != cmdType.get("bodyLength", self.bodyLength):
                raise ValueError(
                    f"Command {name} got wrong bodyLength value: {self.bodyLength}"
                )
            return name

        raise ValueError(
            f"Unknown command {bytes_to_hex(self.head0 + self.head1 + self.head2)}"
        )


class RecvCommand(Command):
    COMMAND_TYPE_DICT: dict[str, CommandType] = {
        "差分解调数据": {
            "head0": bytes([0x80]),
            "head1": bytes([0x01]),
            "bodyIncluded": True,
            "bodyLength": DAS_CONFIG["dataSize"] * 2,
        },
        "振动解调数据": {
            "head0": bytes([0x80]),
            "head1": bytes([0x11]),
            "bodyIncluded": True,
            "bodyLength": DAS_CONFIG["dataSize"] * 2,
        },
        "光强数据": {
            "head0": bytes([0x80]),
            "head1": bytes([0x19]),
            "bodyIncluded": True,
            "bodyLength": DAS_CONFIG["dataSize"] * 2,
        },
        "振动RMS数据": {
            "head0": bytes([0x80]),
            "head1": bytes([0x1A]),
            "bodyIncluded": True,
            "bodyLength": DAS_CONFIG["dataSize"] * 2,
        },
        "心跳包": {
            "head0": bytes([0xA0]),
            "head1": bytes([0x01]),
            "head2": bytes([0x00]),
            "bodyIncluded": True,
            "bodyLength": 32,
        },
        "拆机警报": {
            "head0": bytes([0x90]),
            "head1": bytes([0x03]),
            "head2": bytes([0x00]),
            "bodyIncluded": True,
            "bodyLength": 32,
        },
    }

    def __init__(self, cmdBytes: bytes):
        super().__init__(cmdBytes)
        if self.frameStart != RECV_START:
            raise ValueError(
                f"Invalid frameStart value {bytes_to_hex(self.frameStart)}"
            )
        if self.frameEnd != RECV_END:
            raise ValueError(f"Invalid frameEnd value {bytes_to_hex(self.frameEnd)}")
        if self.deviceTypeCode != DAS_TYPE:
            raise ValueError(
                f"Invalid deviceTypeCode value {bytes_to_hex(self.deviceTypeCode)}"
            )


class SendCommand(Command):
    class SendCommandType(CommandType):
        head2: bytes

    COMMAND_TYPE_DICT: dict[str, SendCommandType] = {
        "DAS配置": {
            "head0": bytes([0x30]),
            "head1": bytes([0x01]),
            "head2": bytes([0x00]),
            "bodyIncluded": True,
            "bodyLength": 32,
        },
        "EDFA配置": {
            "head0": bytes([0x30]),
            "head1": bytes([0x02]),
            "head2": bytes([0x00]),
            "bodyIncluded": True,
            "bodyLength": 2,
        },
        "Raman配置": {
            "head0": bytes([0x30]),
            "head1": bytes([0x03]),
            "head2": bytes([0x00]),
            "bodyIncluded": True,
            "bodyLength": 2,
        },
        "高速数据开始发送": {
            "head0": bytes([0x10]),
            "head1": bytes([0x01]),
            "head2": bytes([0x00]),
            "bodyIncluded": False,
        },
        "高速数据停止发送": {
            "head0": bytes([0x10]),
            "head1": bytes([0x01]),
            "head2": bytes([0xFF]),
            "bodyIncluded": False,
        },
    }

    def __init__(self, name: str, data={}):
        bytesData = SEND_START + DAS_TYPE
        if name not in self.COMMAND_TYPE_DICT:
            raise ValueError(f"Invalid command name {name}")
        cmdType = self.COMMAND_TYPE_DICT[name]
        bytesData += cmdType["head0"] + cmdType["head1"] + cmdType["head2"]
        if cmdType["bodyIncluded"]:
            bytesData += Command.BODY_INCLUDED_TRUE
        else:
            bytesData += Command.BODY_INCLUDED_FALSE

        body = b""
        if name == "DAS配置":
            pulseWidth = data["pulseWidth"] // 4
            body += pulseWidth.to_bytes(4, "little", signed=False)
            DATA_TYPE = ["光强数据", "振动RMS数据", "振动解调数据", "差分解调数据"]
            sendFlag = [False] * len(DATA_TYPE) * 2
            for name, params in data["targets"].items():
                if params["channel"] not in [0, 1]:
                    raise ValueError(f"Invalid channel value {params['channel']}")
                if name not in DATA_TYPE:
                    raise ValueError(f"Invalid targetData value {name}")
                sendFlag[len(DATA_TYPE) * params["channel"] + DATA_TYPE.index(name)] = (
                    True
                )
            bitFlag = 0
            for i, flag in enumerate(sendFlag):
                bitFlag |= flag << i
            body += bitFlag.to_bytes(4, "little", signed=False)
            opticalSwitchFlag = data["opticalSwitchFlag"]
            bitFlag = 0
            for i, flag in enumerate(opticalSwitchFlag):
                bitFlag |= flag << i
            body += bitFlag.to_bytes(4, "little", signed=False)
            body += data["opticalSwitchCounterThreshold"].to_bytes(
                4, "little", signed=False
            )
            body += b"\x00" * 16
        elif name == "EDFA配置":
            body += data["pumpCurrent"].to_bytes(2, "little", signed=False)
        elif name == "Raman配置":
            body += data["current"].to_bytes(2, "little", signed=False)
        elif name == "高速数据开始发送":
            pass
        elif name == "高速数据停止发送":
            pass
        else:
            raise NotImplementedError
        if cmdType["bodyIncluded"]:
            bytesData += len(body).to_bytes(4, "little", signed=False) + body
        bytesData += SEND_END
        super().__init__(bytesData)
