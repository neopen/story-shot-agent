"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: download_reranker.py
@Description: 自动下载 BAAI/bge-reranker-large 模型
            需要安装 pip install sentence-transformers  或 pip install modelscope
@Author: NeoPen
@Time: 2026/5/20 22:30
"""

import os
import sys

from tqdm.asyncio import tqdm

# (可选) 国内用户开启镜像加速
os.environ['HF_ENDPOINT'] = "https://hf-mirror.com"

# 1. 定义项目根目录（根据你的实际结构调整）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 2. 设置模型的本地保存路径 (项目根目录下的 data/models)
local_model_path = os.path.join(project_root, "data", "models", "bge-reranker-large")

# 3. 确保目录存在
os.makedirs(local_model_path, exist_ok=True)

print(f"模型将下载到: {local_model_path}")

# 4. 下载并保存模型
model_name = "BAAI/bge-reranker-large"

def download_model_by_snapshot():
    from huggingface_hub import snapshot_download
    # pip install modelscope

    try:
        # 执行下载，这里显式设置了 tqdm_class，确保能看到进度条
        local_path = snapshot_download(
            repo_id=model_name,
            local_dir=local_model_path,
            ignore_patterns=["*.h5", "*.ot", "*.msgpack"],  # 忽略大文件，节省时间
            tqdm_class=tqdm,  # 显示进度条
            max_workers=4  # 限制并发数，避免网络拥塞
        )

        print("\n" + "=" * 50)
        print(f"🎉 下载完成！")
        print(f"模型已成功保存到: {local_path}")
        print("=" * 50)

        # 简单验证一下关键文件是否存在
        safetensors_path = os.path.join(local_path, "model.safetensors")
        config_path = os.path.join(local_path, "config.json")

        if os.path.exists(safetensors_path):
            file_size = os.path.getsize(safetensors_path) / (1024 ** 3)
            print(f"✅ 验证成功: model.safetensors 存在 (大小: {file_size:.2f} GB)")
        else:
            print(f"⚠️ 警告: model.safetensors 未在预期位置找到，请检查文件夹。")

        if os.path.exists(config_path):
            print(f"✅ 验证成功: config.json 存在")
        else:
            print(f"⚠️ 警告: config.json 未在预期位置找到。")

    except Exception as e:
        print(f"\n❌ 下载过程中发生错误: {e}")
        print("\n可能的解决思路:")
        print("1. 网络问题: 请尝试使用国内镜像")
        print("2. 空间不足: 请确保目标磁盘有至少 4GB 的可用空间")
        print("3. 权限问题: 请确保你对当前目录有写入权限")
        sys.exit(1)



def download_model_by_sentence():
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(model_name)
    model.save_pretrained(local_model_path)

    print(f" 模型已成功下载并保存到: {local_model_path}")


if __name__ == '__main__':
    download_model_by_snapshot()