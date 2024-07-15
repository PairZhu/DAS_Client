import asyncio
from command import RecvCommand, RECV_START, RECV_END, DataNotReceived
from config import REMOTE_ADDRESS


class ServerProtocol(asyncio.DatagramProtocol):
    MAX_FRAME_SIZE = 5000

    def __init__(self):
        self.enable = False
        self.dataCache = bytearray()
        self.cmdListener = []
        self.errorListener = []

    def on(self, name, callback):
        if name == "command":
            self.cmdListener.append(callback)
        elif name == "error":
            self.errorListener.append(callback)
        else:
            raise ValueError(f"Unknown event name {name}")

    def off(self, name, callback):
        if name == "command":
            self.cmdListener.remove(callback)
        elif name == "error":
            self.errorListener.remove(callback)
        else:
            raise ValueError(f"Unknown event name {name}")

    def datagram_received(self, data, addr):
        if addr != REMOTE_ADDRESS or not self.enable:
            return
        self.dataCache.extend(data)
        # 一次数据可能有多个命令
        while True:
            cmdFront = self.dataCache.find(RECV_START)
            cmdRear = self.dataCache.rfind(RECV_END)
            if cmdFront == -1:
                if len(self.dataCache) > len(RECV_START):
                    del self.dataCache[: -len(RECV_START)]
                break
            if cmdRear <= cmdFront:
                del self.dataCache[:cmdFront]
                if len(self.dataCache) > self.MAX_FRAME_SIZE:
                    del self.dataCache[: -self.MAX_FRAME_SIZE]
                break
            cmdBytes = self.dataCache[cmdFront : cmdRear + len(RECV_END)]
            try:
                cmd = RecvCommand(cmdBytes)
            except (ValueError, DataNotReceived) as e:
                if isinstance(e, DataNotReceived):
                    break
                else:
                    for callback in self.errorListener:
                        callback(e)
                    del self.dataCache[: cmdFront + 1]
                    continue
            del self.dataCache[: cmdFront + len(cmd.bytesData)]
            for callback in self.cmdListener:
                callback(cmd)
