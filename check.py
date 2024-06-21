import os
from datetime import datetime
from config import SAVE_CONFIG
from utils import extract_timestamp
import pandas as pd

PRECISION = 1
INTERVAL = SAVE_CONFIG["targets"]["振动解调数据"]["interval"]
PATH = SAVE_CONFIG["path"]
BEGIN_TIME = SAVE_CONFIG["begin"]
END_TIME = SAVE_CONFIG["end"]


def main():
    files = os.listdir(PATH)
    fileDict = {}

    for file in files:
        _, timestamp = extract_timestamp(file)
        timestamp = int(timestamp // PRECISION) * PRECISION
        fileDict[timestamp] = file

    for dt in pd.date_range(BEGIN_TIME, END_TIME, freq=f"{INTERVAL}s"):
        timestamp = dt.to_pydatetime().timestamp()
        if timestamp not in fileDict:
            print(f"{dt} not found")
            return

    confirm = input("文件检查无误，是否重命名？(y/n)")
    if confirm != "y":
        return

    for timestamp, file in fileDict.items():
        dateStr = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d_%H-%M-%S.%f")[
            :-3
        ]
        # os.rename(file, f"Raw{dateStr}.dat")
        os.rename(os.path.join(PATH, file), os.path.join(PATH, f"Raw{dateStr}.dat"))


if __name__ == "__main__":
    main()
