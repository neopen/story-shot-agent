"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: knowledge_base_viewer.py
@Description: 知识库可视化查看工具 - 支持提示词模板库和剧本知识库
@Author: NeoPen
@Time: 2026/4/27 22:18
"""

import json
from pathlib import Path


class KnowledgeBaseViewer:
    """知识库查看器 - 支持提示词模板库和剧本知识库"""

    def __init__(self, storage_dir: str):
        """
        初始化查看器

        Args:
            storage_dir: 知识库根目录（包含 prompt_vector_store.json 和 script_kb/）
        """
        self.storage_dir = Path(storage_dir)
        self.script_kb_dir = self.storage_dir / "script_kb"

    # ========== 提示词模板库相关 ==========

    def show_prompt_index_info(self):
        """显示提示词模板索引信息"""
        vector_store_path = self.storage_dir / "prompt_vector_store.json"

        print("\n" + "-" * 40)
        print("【提示词模板库】")
        print("-" * 40)

        if not vector_store_path.exists():
            print(f"  索引文件不存在: {vector_store_path}")
            print("  提示: 尚未添加任何提示词模板")
            return

        file_size = vector_store_path.stat().st_size
        print(f"  索引文件: {vector_store_path}")
        print(f"  文件大小: {file_size} bytes")

        # 解析向量存储内容
        try:
            with open(vector_store_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 统计向量数量
            vector_count = 0
            if isinstance(data, dict):
                if "embedding_dict" in data:
                    vector_count = len(data["embedding_dict"])
                elif "text_id_to_embeddings" in data:
                    vector_count = len(data["text_id_to_embeddings"])
                elif "text_id_to_doc_id" in data:
                    vector_count = len(data["text_id_to_doc_id"])

            print(f"  向量数量: {vector_count}")

        except Exception as e:
            print(f"  解析失败: {e}")

    def show_prompt_cache(self):
        """显示提示词模板缓存内容"""
        cache_path = self.storage_dir / "test/vector_store_cache.json"

        if not cache_path.exists():
            print("\n  缓存文件不存在")
            return

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            if not cache:
                print("\n  缓存为空")
                return

            print(f"\n  缓存内容 (共 {len(cache)} 条):")
            for i, item in enumerate(cache, 1):
                prompt = item.get('prompt', '')
                metadata = item.get('metadata', {})

                print(f"\n  [{i}]")
                print(f"      提示词: {prompt[:80]}..." if len(prompt) > 80 else f"      提示词: {prompt}")
                print(f"      元数据: {json.dumps(metadata, ensure_ascii=False, indent=6)}")

        except Exception as e:
            print(f"  读取缓存失败: {e}")

    # ========== 剧本知识库相关 ==========

    def show_script_index_info(self):
        """显示剧本知识库索引信息"""
        print("\n" + "-" * 40)
        print("【剧本知识库】")
        print("-" * 40)

        if not self.script_kb_dir.exists():
            print(f"  知识库目录不存在: {self.script_kb_dir}")
            print("  提示: 尚未添加任何剧本")
            return

        vector_store_path = self.script_kb_dir / "vector_store.json"

        if not vector_store_path.exists():
            print(f"  索引文件不存在: {vector_store_path}")
            return

        file_size = vector_store_path.stat().st_size
        print(f"  索引文件: {vector_store_path}")
        print(f"  文件大小: {file_size} bytes")

        # 解析向量存储内容
        try:
            with open(vector_store_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            vector_count = 0
            if isinstance(data, dict):
                if "embedding_dict" in data:
                    vector_count = len(data["embedding_dict"])
                elif "text_id_to_doc_id" in data:
                    vector_count = len(data["text_id_to_doc_id"])

            print(f"  向量数量: {vector_count}")

        except Exception as e:
            print(f"  解析失败: {e}")

    def show_parsed_results(self):
        """显示剧本解析结果"""
        parsed_dir = self.script_kb_dir / "parsed_results"

        if not parsed_dir.exists():
            print("\n  解析结果目录不存在")
            return

        json_files = list(parsed_dir.glob("*.json"))

        if not json_files:
            print("\n  无解析结果")
            return

        print(f"\n  解析结果 (共 {len(json_files)} 个剧本):")

        for file_path in json_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                stats = data.get('stats', {})
                metadata = data.get('metadata', {})
                title = data.get('title', file_path.stem)

                print(f"\n  📄 {file_path.name}")
                print(f"      标题: {title}")
                print(f"      场景数: {stats.get('scene_count', 0)}")
                print(f"      角色数: {stats.get('character_count', 0)}")
                print(f"      元素数: {stats.get('total_elements', 0)}")
                print(f"      总时长: {stats.get('total_duration', 0):.1f}秒")
                print(f"      完整性得分: {stats.get('completeness_score', 0):.1f}%")
                print(f"      解析时间: {metadata.get('parsed_at', '未知')}")

            except Exception as e:
                print(f"  ❌ 解析失败 {file_path.name}: {e}")

    def show_script_details(self, script_id: str = None):
        """显示剧本详细信息"""
        parsed_dir = self.script_kb_dir / "parsed_results"

        if not parsed_dir.exists():
            print("  解析结果目录不存在")
            return

        # 如果指定了 script_id，只显示该剧本
        if script_id:
            target_files = [parsed_dir / f"{script_id}.json"]
        else:
            target_files = list(parsed_dir.glob("*.json"))

        for file_path in target_files:
            if not file_path.exists():
                print(f"  剧本不存在: {script_id}")
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                print(f"\n{'=' * 60}")
                print(f"剧本详情: {file_path.name}")
                print(f"{'=' * 60}")

                # 角色列表
                characters = data.get('characters', [])
                if characters:
                    print(f"\n【角色列表】({len(characters)}个)")
                    for char in characters:
                        print(f"  - {char.get('name')} ({char.get('gender', '未知')}) - {char.get('role', '配角')}")

                # 场景列表
                scenes = data.get('scenes', [])
                if scenes:
                    print(f"\n【场景列表】({len(scenes)}个)")
                    for i, scene in enumerate(scenes, 1):
                        print(f"\n  场景 {i}: {scene.get('id')}")
                        print(f"      地点: {scene.get('location', '未知')}")
                        print(f"      时间: {scene.get('time_of_day', '未知')}")
                        print(f"      元素数: {len(scene.get('elements', []))}")

            except Exception as e:
                print(f"  ❌ 解析失败: {e}")

    # ========== 记忆层相关 ==========

    def show_memory_layer(self):
        """显示记忆层中的成功提示词模板"""
        print("\n" + "-" * 40)
        print("【记忆层 (LONG_TERM)】")
        print("-" * 40)

        try:
            from penshot.neopen.knowledge.memory.memory_manager import MemoryManager
            from penshot.neopen.knowledge.memory.memory_models import MemoryLevel

            # 创建临时记忆管理器（不需要 LLM）
            memory = MemoryManager(
                llm=None,
                script_id="viewer",
                config=None
            )

            successful_prompts = memory.get(
                "successful_prompt_patterns",
                level=MemoryLevel.LONG_TERM,
                default=[]
            )

            if not successful_prompts:
                print("\n  记忆层中没有成功提示词模板")
                return

            print(f"\n  成功提示词模板 (共 {len(successful_prompts)} 条):")
            for i, item in enumerate(successful_prompts, 1):
                if isinstance(item, dict):
                    prompt = item.get("prompt", "")[:80]
                    metadata = item.get("metadata", {})
                    print(f"\n  [{i}]")
                    print(f"      提示词: {prompt}..." if len(item.get("prompt", "")) > 80 else f"      提示词: {prompt}")
                    print(f"      元数据: {metadata}")
                else:
                    print(f"\n  [{i}] {str(item)[:100]}")

        except ImportError as e:
            print(f"  无法导入记忆模块: {e}")
        except Exception as e:
            print(f"  读取记忆层失败: {e}")

    # ========== 统计和综合分析 ==========

    def show_statistics(self):
        """显示综合统计信息"""
        print("\n" + "=" * 60)
        print("知识库综合统计")
        print("=" * 60)

        # 统计提示词模板库
        vector_store_path = self.storage_dir / "prompt_vector_store.json"
        if vector_store_path.exists():
            try:
                with open(vector_store_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict) and "embedding_dict" in data:
                    prompt_count = len(data["embedding_dict"])
                else:
                    prompt_count = "未知"
            except:
                prompt_count = "未知"
        else:
            prompt_count = 0

        # 统计剧本知识库
        script_count = 0
        scene_count = 0
        character_count = 0

        parsed_dir = self.script_kb_dir / "parsed_results"
        if parsed_dir.exists():
            for file_path in parsed_dir.glob("*.json"):
                script_count += 1
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    scene_count += data.get('stats', {}).get('scene_count', 0)
                    character_count += data.get('stats', {}).get('character_count', 0)
                except:
                    pass

        print(f"\n  提示词模板库:")
        print(f"    模板数量: {prompt_count}")

        print(f"\n  剧本知识库:")
        print(f"    剧本数量: {script_count}")
        print(f"    总场景数: {scene_count}")
        print(f"    总角色数: {character_count}")

        # 存储路径
        print(f"\n  存储路径:")
        print(f"    根目录: {self.storage_dir}")
        print(f"    剧本目录: {self.script_kb_dir}")

    # ========== 综合显示 ==========

    def show_all(self, show_details: bool = False):
        """
        显示所有信息

        Args:
            show_details: 是否显示详细信息（场景、角色列表）
        """
        print("\n" + "=" * 60)
        print("知识库状态查看器")
        print("=" * 60)
        print(f"存储目录: {self.storage_dir}")

        # 综合统计
        self.show_statistics()

        # 提示词模板库
        self.show_prompt_index_info()
        self.show_prompt_cache()

        # 剧本知识库
        self.show_script_index_info()
        self.show_parsed_results()

        # 记忆层
        self.show_memory_layer()

        # 详细信息（可选）
        if show_details:
            self.show_script_details()

    def show_quick(self):
        """快速查看（只显示关键信息）"""
        print("\n" + "-" * 40)

        # 统计数量
        prompt_count = 0
        vector_store_path = self.storage_dir / "prompt_vector_store.json"
        if vector_store_path.exists():
            try:
                with open(vector_store_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict) and "embedding_dict" in data:
                    prompt_count = len(data["embedding_dict"])
            except:
                pass

        script_count = 0
        parsed_dir = self.script_kb_dir / "parsed_results"
        if parsed_dir.exists():
            script_count = len(list(parsed_dir.glob("*.json")))

        print(f"📝 提示词模板: {prompt_count} 条")
        print(f"📖 剧本: {script_count} 个")

        if script_count > 0:
            # 显示最后一个剧本的信息
            latest_script = None
            latest_time = None
            for file_path in parsed_dir.glob("*.json"):
                mtime = file_path.stat().st_mtime
                if latest_time is None or mtime > latest_time:
                    latest_time = mtime
                    latest_script = file_path

            if latest_script:
                try:
                    with open(latest_script, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    stats = data.get('stats', {})
                    print(f"  最新剧本: {latest_script.name}")
                    print(f"    场景: {stats.get('scene_count', 0)} | 角色: {stats.get('character_count', 0)}")
                except:
                    pass


# ========== 命令行接口 ==========

def view_knowledge_base(storage_dir: str = None, quick: bool = False, details: bool = False):
    """
    命令行查看知识库

    Args:
        storage_dir: 知识库存储目录
        quick: 快速查看模式
        details: 显示详细信息
    """
    if storage_dir is None:
        # 尝试从配置获取
        try:
            from penshot.config.config import settings
            storage_dir = settings.get_data_paths.get('knowledge_base', './data/knowledge_base')
        except:
            storage_dir = './data/knowledge_base'

    viewer = KnowledgeBaseViewer(storage_dir)

    if quick:
        viewer.show_quick()
    else:
        viewer.show_all(show_details=details)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="知识库查看工具")
    parser.add_argument("--dir", "-d", type=str, default="./data",
                        help="知识库存储目录")
    parser.add_argument("--quick", "-q", action="store_true",
                        help="快速查看模式")
    parser.add_argument("--details", "--detail", action="store_true",
                        help="显示详细信息")
    parser.add_argument("--script", "-s", type=str, default=None,
                        help="查看特定剧本的详情")

    args = parser.parse_args()

    if args.script:
        # 查看特定剧本
        viewer = KnowledgeBaseViewer(args.dir or './data/knowledge_base')
        viewer.show_script_details(args.script)
    else:
        view_knowledge_base(args.dir, quick=args.quick, details=args.details)


if __name__ == "__main__":
    main()
