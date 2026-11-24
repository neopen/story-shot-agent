"""
Copyright 2025 neopen
SPDX-License-Identifier: Apache-2.0
Licensed under the Apache License, Version 2.0.
See the LICENSE and NOTICE files for details.

@FileName: conftest.py.py
@Description: pytest 全局配置：测试运行不写生产日志文件
@Author: neopen
@GitHub: https://github.com/neopen/story-shot-agent
@Time: 2026/4/28 16:19
"""

import os

# 测试大量实例化 Logger，若沿用默认配置会把 pytest 输出持续写入
# logs/penshot_<date>.log，淹没真实运行的诊断信息。
os.environ.setdefault("PENSHOT_LOG_TO_FILE", "0")
