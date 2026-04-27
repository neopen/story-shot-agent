"""
@FileName: knowledge_base_viewer.py
@Description: 知识库可视化查看工具
@Author: HiPeng
@Time: 2026/4/27 22:18
"""
import json
import os


class KnowledgeBaseViewer:
    """知识库查看器"""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir

    def show_index_info(self):
        """显示索引信息"""
        vector_store_path = os.path.join(self.storage_dir, "prompt_vector_store.json")
        if os.path.exists(vector_store_path):
            print(f"向量索引文件: {vector_store_path}")
            print(f"文件大小: {os.path.getsize(vector_store_path)} bytes")
        else:
            print("向量索引文件不存在")

    def show_cache(self):
        """显示缓存内容"""
        cache_path = os.path.join(self.storage_dir, "cache.json")
        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"\n缓存内容 (共 {len(cache)} 条):")
            for i, item in enumerate(cache, 1):
                print(f"\n{i}. 提示词: {item.get('prompt', '')[:100]}...")
                print(f"   元数据: {item.get('metadata', {})}")
        else:
            print("缓存文件不存在")

    def show_parsed_results(self):
        """显示解析结果"""
        parsed_dir = os.path.join(self.storage_dir, "parsed_results")
        if os.path.exists(parsed_dir):
            files = os.listdir(parsed_dir)
            print(f"\n解析结果 (共 {len(files)} 个剧本):")
            for file in files:
                if file.endswith('.json'):
                    path = os.path.join(parsed_dir, file)
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    stats = data.get('stats', {})
                    print(f"\n   {file}:")
                    print(f"     场景数: {stats.get('scene_count', 0)}")
                    print(f"     角色数: {stats.get('character_count', 0)}")
                    print(f"     元素数: {stats.get('total_elements', 0)}")
        else:
            print("无解析结果")

    def show_all(self):
        """显示所有信息"""
        print("=" * 50)
        print("知识库状态")
        print("=" * 50)
        self.show_index_info()
        self.show_cache()
        self.show_parsed_results()


def view_knowledge_base(storage_dir: str = None):
    """命令行查看知识库"""
    from penshot.config.config import settings

    if storage_dir is None:
        storage_dir = settings.get_data_paths().get('data_template', './knowledge_cache')

    viewer = KnowledgeBaseViewer(storage_dir)
    viewer.show_all()


if __name__ == "__main__":
    import sys

    storage_dir = sys.argv[1] if len(sys.argv) > 1 else None
    view_knowledge_base(storage_dir)
