"""
@FileName: direct_usage.py
@Description: 作为Python库直接使用
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/2/10 19:46
"""
import asyncio

from hengshot.hengline import generate_storyboard

"""
# 1. 下载安装依赖
https://github.com/HengLine/video-shot-agent/releases/download/v0.1.3-beta/hengshot-0.1.3-py3-none-any.whl
pip install hengshot-0.1.3-py3-none-any.whl  # 假设这是你的包名

# 2. 设置API密钥（如果需要LLM）
export OPENAI_API_KEY="your-api-key"  # 或其他LLM配置

"""

async def basic_usage():
    """基础用法示例"""
    script = """
    场景：现代办公室
    时间：下午3点
    人物：小李（程序员）
    动作：小李正在写代码，突然接到电话，表情惊讶
    """

    # 简单调用
    result = await generate_storyboard(script_text=script)
    print(f"生成完成，任务ID: {result.get('task_id')}")
    print(f"生成结果: {result.get('success', False)}")
    print(f"分镜片段: {result.get('data', {})}")

    return result


async def batch_processing():
    """批量处理示例"""
    scripts = [
        "一个男人在海边跑步，日出时分...",
        "两个孩子在游乐场玩耍，欢声笑语...",
        "老人在公园下棋，专注沉思..."
    ]

    tasks = []
    for idx, script in enumerate(scripts, 1):
        task_id = f"batch_task_{idx:03d}"
        task = generate_storyboard(
            script_text=script,
            task_id=task_id
        )
        tasks.append(task)

    # 并发执行
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"任务 {idx + 1} 失败: {result}")
        else:
            print(f"任务 {idx + 1} 成功，生成结果 {result.get('success', [])} ")

    return results


async def with_custom_config():
    """使用自定义配置"""
    from hengshot.hengline.hengline_config import HengLineConfig

    # 创建自定义配置
    custom_config = HengLineConfig(
        # 这里可以根据实际情况设置配置参数
        model_name="gpt-4",
        base_url="http://localhost:11434",  # 假设本地部署了 Ollama
        temperature=0.2
    )

    script = "科幻场景：太空站内部，宇航员发现异常信号..."

    # 使用自定义配置
    result = await generate_storyboard(
        script_text=script,
        task_id="custom_config_task",
        config=custom_config
    )

    return result


def main():
    """主函数演示各种用法"""

    # 基本用法
    print("=== 基本用法示例 ===")
    result = asyncio.run(basic_usage())

    # 批量处理
    print("\n=== 批量处理示例 ===")
    batch_results = asyncio.run(batch_processing())

    # 使用自定义配置（如果需要）
    # print("\n=== 自定义配置示例 ===")
    # custom_result = asyncio.run(with_custom_config())


if __name__ == "__main__":
    main()
