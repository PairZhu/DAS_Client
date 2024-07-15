import os
import re
from datetime import datetime
import numpy as np
from tqdm import tqdm
import argparse

# 参数解析
parser = argparse.ArgumentParser(description="文件转换")
parser.add_argument(
    "source_dir",
    type=str,
    help="源文件夹路径",
)
args = parser.parse_args()

SOURCE_DIR = args.source_dir
TARGET_DIR = os.path.join(SOURCE_DIR, "label")
FILE_PREFIX = "Raw"

TIME_INTERVAL = 1
SAMPLE_RATE = 5000

FILE_TIME_INTERVAL = 30
OVERLAP = 0.5
DOWN_SAMPLE = 10

OVERWRITE = True

CHECK_ONLY = False
TOTAL_TOL = 1
SINGLE_TOL = 0.05


assert FILE_TIME_INTERVAL % TIME_INTERVAL == 0, "文件时间间隔不是处理时间间隔的整数倍"
assert 0 <= OVERLAP < 1, "重叠率不在[0, 1)范围内"
assert OVERLAP * FILE_TIME_INTERVAL % TIME_INTERVAL == 0, "重叠率不合理"

ORIGIN_FILES = [f for f in os.listdir(SOURCE_DIR) if f.endswith(".dat")]
assert ORIGIN_FILES, "源文件夹内无有效文件"
example_file = ORIGIN_FILES[0]
example_data = np.fromfile(
    os.path.join(SOURCE_DIR, example_file), dtype=np.dtype("<i2")
)
DATA_SHAPE = example_data.reshape(TIME_INTERVAL * SAMPLE_RATE, -1).shape


def storage_format_to_timestamp(file):
    match = re.search(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}.\d{3}", file)
    assert match, f"{file}不符合格式"
    date_str = match.group()
    date = datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S.%f")
    return int(date.timestamp() * 1000)


def label_format_to_timestamp(file):
    timestamps = re.findall(r"\d{13}", file)
    assert len(timestamps) == 2, f"{file}不符合格式"
    begin_timestamp, end_timestamp = [int(timestamp) for timestamp in timestamps]
    return begin_timestamp, end_timestamp


def timestamp_to_label_format(
    timestamp: int, file_time_interval: float = TIME_INTERVAL
):
    end_timestamp = timestamp
    begin_timestamp = end_timestamp - file_time_interval * 1000
    return f"{begin_timestamp}_{end_timestamp}_{DATA_SHAPE[1]}.dat"


def timestamp_to_storage_format(timestamp: int):
    date = datetime.fromtimestamp(timestamp / 1000)
    return f"{FILE_PREFIX}{date.strftime('%Y-%m-%d_%H-%M-%S.%f')[0:-3]}.dat"


def storage_format_to_label_format(files, file_time_interval: float = TIME_INTERVAL):
    next_file_names = []
    for file in files:
        assert file.startswith(FILE_PREFIX), f"{file}不符合格式"
        end_timestamp = storage_format_to_timestamp(file)
        format_file_name = timestamp_to_label_format(end_timestamp, file_time_interval)
        next_file_names.append(format_file_name)

    assert len(set(next_file_names)) == len(next_file_names), "文件名重复"
    return next_file_names


def label_format_to_storage_format(files):
    next_file_names = []
    for file in files:
        _, end_timestamp = label_format_to_timestamp(file)
        format_file_name = timestamp_to_storage_format(end_timestamp)
        next_file_names.append(format_file_name)

    assert len(set(next_file_names)) == len(next_file_names), "文件名重复"
    return next_file_names


def storage_combin_to_label(
    files,
    total_tol: float = TIME_INTERVAL / 2,
    single_tol: float = TIME_INTERVAL / 10,
    check_only: bool = False,
):
    combine_length = int(FILE_TIME_INTERVAL / TIME_INTERVAL)
    overlap_length = int(OVERLAP * combine_length)
    files = [file for file in files if file.startswith(FILE_PREFIX)]
    files = sorted(files)
    combine_files = []
    vaild_timestamp = storage_format_to_timestamp(files[0])
    max_single_error = 0
    max_total_error = 0
    last_timestamp = vaild_timestamp - TIME_INTERVAL * 1000
    file_params = []
    next_file_names = []
    for file in files:
        file_timestamp = storage_format_to_timestamp(file)
        single_error = abs(file_timestamp - last_timestamp - TIME_INTERVAL * 1000)
        assert (
            single_error <= single_tol * 1000
        ), f"{file}与上一个文件时间戳不连续，误差{single_error}ms"
        max_single_error = max(max_single_error, single_error)
        last_timestamp = file_timestamp
        total_error = abs(file_timestamp - vaild_timestamp)
        assert (
            total_error <= total_tol * 1000
        ), f"总体时间戳不连续，当前文件{file}，误差{total_error}ms"
        max_total_error = max(max_total_error, total_error)
        next_file_names.extend([timestamp_to_storage_format(vaild_timestamp)])
        vaild_timestamp += TIME_INTERVAL * 1000
        combine_files.append(file)
        if len(combine_files) != combine_length:
            continue
        file_params.append(
            {
                "name": timestamp_to_label_format(vaild_timestamp, FILE_TIME_INTERVAL),
                "files": [*combine_files],
            }
        )

        combine_files = combine_files[-overlap_length:]

    if check_only:
        return max_single_error, max_total_error

    os.makedirs(TARGET_DIR, exist_ok=True)

    for file_param in tqdm(file_params, desc="生成标注文件"):
        combine_data = []
        for combine_file in file_param["files"]:
            data = np.fromfile(
                os.path.join(SOURCE_DIR, combine_file), dtype=np.dtype("<i2")
            ).reshape(TIME_INTERVAL * SAMPLE_RATE, -1)
            # 使用RMS降采样
            # 计算区间数
            INTERVAL = int(len(data) / DOWN_SAMPLE)
            data = (
                data[: INTERVAL * DOWN_SAMPLE]
                .reshape(INTERVAL, DOWN_SAMPLE, -1)
                .astype(np.float32)
            )
            data = np.sqrt(np.mean(data**2, axis=1)).astype("<i2")
            combine_data.append(data)
        combine_data = np.concatenate(combine_data, axis=0)
        combine_data.tofile(os.path.join(TARGET_DIR, file_param["name"]))

    log_file = open(os.path.join(TARGET_DIR, "rename.log"), "+a", encoding="utf-8")
    for file, next_file_name in tqdm(
        zip(files, next_file_names), desc="重命名文件", total=len(files)
    ):
        if file != next_file_name:
            os.rename(
                os.path.join(SOURCE_DIR, file), os.path.join(SOURCE_DIR, next_file_name)
            )
            log_file.write(f"{file} -> {next_file_name}\n")

    return max_single_error, max_total_error


if __name__ == "__main__":
    if OVERWRITE and os.path.exists(TARGET_DIR):
        # 删除target文件夹下所有dat文件
        for file in os.listdir(TARGET_DIR):
            if file.endswith(".dat"):
                os.remove(os.path.join(TARGET_DIR, file))

    max_single_error, max_total_error = storage_combin_to_label(
        ORIGIN_FILES, total_tol=TOTAL_TOL, single_tol=SINGLE_TOL, check_only=CHECK_ONLY
    )
    print(f"最大单个文件时间戳误差：{max_single_error}ms")
    print(f"最大总体时间戳误差：{max_total_error}ms")
