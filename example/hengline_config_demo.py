"""
@FileName: hengline_config_demo.py
@Description: 包含完整详细配置示例
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/2/10 19:52
"""
import asyncio

from pydantic.v1 import SecretStr

from hengshot.hengline import generate_storyboard
from hengshot.hengline.hengline_config import HengLineConfig


async def hengline_config_examples():
    """HengLineConfig 各种配置示例"""

    # ==================== 示例1: 基础配置 ====================
    print("=== 示例1: 基础配置 ===")
    config1 = HengLineConfig(
        # 模型配置
        model_name="gpt-4",  # 使用的LLM模型
        temperature=0.7,  # 温度参数，控制随机性
        max_tokens=2000,  # 最大token数

        # API配置
        api_key=SecretStr("your-api-key-here"),  # API密钥
        base_url="https://api.openai.com/v1",  # API基础URL

        # 重试策略
        max_retries=3,  # 最大重试次数
        retry_delay=1.0,  # 重试延迟(秒)

        # 超时设置
        timeout=30,  # 请求超时时间
    )

    result1 = await generate_storyboard(
        script_text="一个简单的测试场景",
        task_id="config_demo_1",
        config=config1
    )
    print(f"基础配置结果: {len(result1.get('shots', []))} 个分镜")

    # ==================== 示例2: 使用不同模型 ====================
    print("\n=== 示例2: 使用不同模型 ===")
    config2 = HengLineConfig(
        model_name="gpt-4-turbo-preview",
        temperature=0.3,  # 更低的温度，输出更确定性
        max_tokens=3000,

        # 函数调用配置（如果支持）
        function_call="auto",
    )

    # ==================== 示例3: 本地模型配置 ====================
    print("\n=== 示例3: 本地模型配置 ===")
    config3 = HengLineConfig(
        # 使用本地部署的模型
        model_name="qwen2.5:14b",  # 本地模型名称
        base_url="http://localhost:11434/v1",  # 本地API地址

        # 调整参数适应本地模型
        temperature=0.8,
        max_tokens=1000,
        timeout=60,  # 本地模型可能需要更长时间
    )

    # ==================== 示例4: 深度求索 DeepSeek 配置 ====================
    print("\n=== 示例4: DeepSeek 配置 ===")
    config4 = HengLineConfig(
        model_name="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key=SecretStr("your-deepseek-api-key"),

        # DeepSeek 特定参数
        temperature=0.6,
        max_tokens=4000,
    )

    # ==================== 示例5: 批处理优化配置 ====================
    print("\n=== 示例5: 批处理优化配置 ===")
    config5 = HengLineConfig(
        model_name="gpt-4",
        temperature=0.5,

        # 并行处理配置
        max_concurrent_requests=5,  # 最大并发请求数

        # 性能优化
        streaming=False,  # 关闭流式响应以加快批处理
        timeout=45,
    )

    # ==================== 示例6: 从环境变量加载配置 ====================
    print("\n=== 示例6: 从环境变量加载配置 ===")
    import os
    # 设置环境变量
    os.environ["HENGLINE_MODEL_NAME"] = "gpt-4"
    os.environ["HENGLINE_API_KEY"] = "your-api-key-from-env"
    os.environ["HENGLINE_MAX_TOKENS"] = "2500"

    # 使用默认构造函数，会自动读取环境变量
    config6 = HengLineConfig()  # 从环境变量加载配置

    # ==================== 示例7: 自定义提示词模板 ====================
    print("\n=== 示例7: 自定义配置（如果有相关参数） ===")
    config7 = HengLineConfig(
        model_name="gpt-4",

        # 假设 HengLineConfig 支持这些参数
        # 实际参数请查看 HengLineConfig 的源码定义
        max_shot_duration=10.0,

        # 输出格式控制
        response_format="json",
    )

    # ==================== 示例8: 混合配置 ====================
    print("\n=== 示例8: 混合配置 ===")

    # 先创建基础配置
    base_config = HengLineConfig()

    # 然后根据需要修改特定参数
    # 注意：根据 HengLineConfig 的实现方式，可能需要使用不同的方法
    # 这里假设 HengLineConfig 支持属性设置或提供了更新方法

    try:
        # 尝试直接设置属性
        base_config.model_name = "claude-3-opus"
        base_config.temperature = 0.4
        base_config.max_tokens = 1500
    except AttributeError:
        # 如果不能直接设置，可能需要创建新实例
        config8 = HengLineConfig(
            model_name="claude-3-opus",
            temperature=0.4,
            max_tokens=1500,
            # 其他参数保持不变
        )
    else:
        config8 = base_config

    # ==================== 示例9: 错误处理和回退配置 ====================
    print("\n=== 示例9: 错误处理和回退配置 ===")
    config9 = HengLineConfig(
        model_name="primary-model",

        # 备用模型配置
        fallback_model="gpt-3.5-turbo",
        fallback_on_error=True,

        # 降级策略
        degrade_on_rate_limit=True,
    )

    # ==================== 示例10: 完整使用示例 ====================
    print("\n=== 示例10: 完整使用示例 ===")

    # 创建一个详细的剧本
    detailed_script = """
    电影《追光者》开场：

    第一场：黄昏，海边
    时间：傍晚6点，日落时分
    地点：东海市沙滩
    人物：林浩（25岁，摄影师）、苏晴（23岁，画家）

    内容：
    1. 远景：夕阳下的海滩，海鸥飞过
    2. 中景：林浩架设三脚架，调整相机参数
    3. 近景：苏晴在画板前作画，画笔特写
    4. 双人镜头：两人偶然对视，微笑
    5. 特写：相机取景器中的夕阳

    视觉要求：
    - 暖色调，金色阳光
    - 慢镜头处理海浪
    - 逆光拍摄剪影效果

    音效：
    - 海浪声
    - 海鸥叫声
    - 轻柔的背景音乐
    """

    # 使用优化配置
    production_config = HengLineConfig(
        model_name="gpt-4",
        temperature=0.6,
        max_tokens=3500,

        # 质量相关
        top_p=0.9,
        frequency_penalty=0.1,
        presence_penalty=0.1,

        # 性能相关
        timeout=40,
        max_retries=5,
        retry_delay=2.0,
    )

    try:
        result = await generate_storyboard(
            script_text=detailed_script,
            task_id="movie_opening_001",
            config=production_config
        )

        print(f"分镜生成完成！")
        print(f"任务ID: {result.get('task_id')}")
        print(f"场景数: {result.get('scene_count', 0)}")
        print(f"总镜头数: {len(result.get('shots', []))}")

        # 显示前3个分镜
        shots = result.get('shots', [])
        for i, shot in enumerate(shots[:3], 1):
            print(f"\n分镜 {i}:")
            print(f"  描述: {shot.get('description', '')[:80]}...")
            print(f"  时长: {shot.get('duration', 'N/A')}")
            print(f"  景别: {shot.get('shot_type', 'N/A')}")

    except Exception as e:
        print(f"生成失败: {e}")

        # 尝试降级到更简单的配置
        print("尝试使用降级配置...")
        fallback_config = HengLineConfig(
            model_name="gpt-3.5-turbo",
            temperature=0.8,
            max_tokens=2000,
        )

        fallback_result = await generate_storyboard(
            script_text=detailed_script[:500],  # 截断剧本
            task_id="fallback_attempt",
            config=fallback_config
        )
        print(f"降级配置生成完成: {len(fallback_result.get('shots', []))} 个分镜")


# ==================== 配置工厂模式 ====================
class ConfigFactory:
    """配置工厂，方便创建不同用途的配置"""

    @staticmethod
    def create_fast_config():
        """快速但简略的配置"""
        return HengLineConfig(
            model_name="gpt-3.5-turbo",
            temperature=0.9,
            max_tokens=1000,
            timeout=15,
        )

    @staticmethod
    def create_quality_config():
        """高质量详细配置"""
        return HengLineConfig(
            model_name="gpt-4",
            temperature=0.4,
            max_tokens=5000,
            top_p=0.95,
            timeout=60,
        )

    @staticmethod
    def create_local_config(base_url: str = "http://localhost:11434/v1"):
        """本地模型配置"""
        return HengLineConfig(
            model_name="qwen2.5:14b",
            base_url=base_url,
            temperature=0.7,
            max_tokens=3000,
            timeout=120,
        )


async def factory_demo():
    """使用配置工厂的示例"""
    print("\n=== 配置工厂示例 ===")

    # 创建快速配置
    fast_config = ConfigFactory.create_fast_config()
    fast_result = await generate_storyboard(
        script_text="一个简短的测试场景",
        config=fast_config
    )
    print(f"快速配置: {len(fast_result.get('shots', []))} 个分镜")

    # 创建高质量配置
    quality_config = ConfigFactory.create_quality_config()
    # quality_result = await generate_storyboard(...)

    return fast_result


# ==================== 配置验证和测试 ====================
async def test_config(config: HengLineConfig):
    """测试配置的有效性"""
    test_script = "测试场景：一个人在房间里看书"

    try:
        result = await generate_storyboard(
            script_text=test_script,
            task_id="config_test",
            config=config
        )

        if result and 'shots' in result:
            print(f"配置测试通过: {len(result['shots'])} 个分镜")
            return True
        else:
            print("配置测试失败: 返回结果格式异常")
            return False

    except Exception as e:
        print(f"配置测试失败: {e}")
        return False


async def main():
    """主函数"""

    # 运行配置示例
    result = await hengline_config_examples()

    # 运行工厂示例
    # factory_result = await factory_demo()

    # 测试配置
    print("\n=== 配置验证测试 ===")
    test_config_instance = HengLineConfig(
        model_name="gpt-3.5-turbo",
        temperature=0.7,
        max_tokens=500
    )
    await test_config(test_config_instance)


if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())
