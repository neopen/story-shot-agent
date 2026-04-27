"""
@FileName: test_knowledge_base.py
@Description: 测试知识库功能
@Author: HiPeng
@Time: 2026/4/27 22:09
"""

import asyncio

from penshot.neopen.client.client_factory import get_default_embedding, get_default_llm
from penshot.neopen.knowledge.llamaIndex.llama_index_knowledge import ScriptKnowledgeBase
from penshot.neopen.prompts.prompt_template_manager import PromptTemplateManager


async def test_prompt_template_manager():
    """测试提示词模板管理器"""
    print("\n" + "=" * 50)
    print("测试提示词模板管理器")
    print("=" * 50)

    # 初始化
    llm = get_default_llm()
    embeddings = get_default_embedding()

    manager = PromptTemplateManager(
        embedding_model=embeddings,
        storage_dir="./data"
    )

    # 1. 添加模板
    print("\n1. 添加测试模板...")
    manager.add_template(
        prompt_text="中景，特写镜头，人物表情丰富，背景虚化，电影级质感",
        metadata={
            "fragment_id": "test_001",
            "scene": "咖啡馆",
            "style": "电影感",
            "quality_score": 95
        }
    )

    manager.add_template(
        prompt_text="广角镜头，城市夜景，霓虹灯闪烁，车流如织，赛博朋克风格",
        metadata={
            "fragment_id": "test_002",
            "scene": "城市夜景",
            "style": "赛博朋克",
            "quality_score": 88
        }
    )

    # 2. 查看统计
    print("\n2. 知识库统计:")
    stats = manager.get_statistics()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    # 3. 搜索相似模板
    print("\n3. 搜索相似提示词...")
    query = "人物特写，表情"
    results = manager.search_similar(query, top_k=2)

    print(f"   查询: '{query}'")
    print(f"   找到 {len(results)} 个结果:")
    for i, r in enumerate(results, 1):
        print(f"\n   结果 {i}:")
        print(f"     提示词: {r['prompt'][:80]}...")
        print(f"     相似度: {r['score']:.4f}")
        print(f"     元数据: {r.get('metadata', {})}")

    # 4. 测试提示词增强
    print("\n4. 测试提示词增强:")
    original = "人物表情特写"
    enhanced = manager.enhance_prompt(original, enhancement_mode="append")
    print(f"   原始: {original}")
    print(f"   增强: {enhanced[:150]}...")

    # 5. 测试是否可用
    print(f"\n5. 知识库可用性: {manager.is_available()}")

    return manager


def test_script_knowledge_base():
    """测试剧本知识库"""
    print("\n" + "=" * 50)
    print("测试剧本知识库")
    print("=" * 50)

    embeddings = get_default_embedding()

    kb = ScriptKnowledgeBase(
        embeddings=embeddings,
        storage_dir="./data/script_kb"
    )

    # 1. 添加测试剧本
    print("\n1. 添加测试剧本...")
    test_script = """
    【场景1】咖啡厅 - 白天
    林然坐在窗边，手中捧着一杯咖啡，目光望向远方。
    李明推门而入，四处张望。
    林然（微笑）：这边。
    李明走过来坐下。
    """

    result = kb.add_script_text(test_script, script_id="test_script_001")
    print(f"   添加结果: {result}")

    # 2. 查看统计
    print("\n2. 知识库统计:")
    stats = kb.get_statistics()
    for key, value in stats.items():
        if key != "parsed_scripts":
            print(f"   {key}: {value}")

    # 3. 测试查询
    print("\n3. 测试查询...")
    query = "咖啡厅的场景"
    query_result = kb.query(query, similarity_top_k=2)

    print(f"   查询: '{query}'")
    print(f"   找到 {query_result['total_results']} 个结果:")
    for i, r in enumerate(query_result['results'], 1):
        print(f"\n   结果 {i}:")
        print(f"     内容: {r['text'][:100]}...")
        print(f"     相似度: {r['score']:.4f}")
        print(f"     元数据: script_id={r['metadata'].get('script_id', 'N/A')}")

    return kb


def test_memory_sync():
    """测试记忆层同步"""
    print("\n" + "=" * 50)
    print("测试记忆层同步")
    print("=" * 50)

    from penshot.neopen.knowledge.memory.memory_manager import MemoryManager
    from penshot.neopen.knowledge.memory.memory_models import MemoryConfig, MemoryLevel

    llm = get_default_llm()
    embeddings = get_default_embedding()

    memory = MemoryManager(
        llm=llm,
        script_id="test_memory",
        config=MemoryConfig(
            embeddings=embeddings,
            long_term_enabled=True
        )
    )

    manager = PromptTemplateManager(
        embedding_model=embeddings,
        memory_manager=memory,
        storage_dir="./data"
    )

    # 添加模板（会同步到记忆层）
    print("\n1. 添加模板（同步到记忆层）...")
    manager.add_template(
        prompt_text="测试同步模板",
        metadata={"test": True, "quality_score": 100}
    )

    # 从记忆层读取
    print("\n2. 从记忆层读取...")
    saved = memory.get("successful_prompt_patterns", level=MemoryLevel.LONG_TERM)
    print(f"   记忆层数据: {saved}")

    # 重新初始化管理器（测试加载）
    print("\n3. 重新初始化管理器（从记忆层加载）...")
    manager2 = PromptTemplateManager(
        embedding_model=embeddings,
        memory_manager=memory,
        storage_dir="./data"
    )
    print(f"   加载后模板数: {manager2.get_statistics()['template_count']}")

    return manager2


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("知识库功能验证测试")
    print("=" * 60)

    try:
        # 测试提示词模板管理器
        await test_prompt_template_manager()

        # 测试剧本知识库
        await test_script_knowledge_base()

        # 测试记忆层同步
        test_memory_sync()

        print("\n" + "=" * 60)
        print("所有测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())