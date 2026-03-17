"""
@FileName: generate_agent.py
@Description: 
@Author: Haeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10/23 15:51
"""
import uuid
from typing import Dict, Optional

from penshot.neopen.agent import MultiAgentPipeline
from penshot.neopen.language_manage import Language, set_language
from penshot.neopen.shot_config import ShotConfig


# 对外暴露的主函数，供 LangGraph 或 A2A 调用
async def generate_storyboard(
        script_text: str,
        task_id: Optional[str] = str(uuid.uuid4().hex),
        language: Language = Language.ZH,
        config: Optional[ShotConfig] = ShotConfig()
) -> Dict:
    """
    剧本分镜生成主接口（可嵌入 LangGraph 或 A2A 调用）

    Args:
        script_text: 用户输入的中文剧本（自然语言）
        task_id: 任务ID，用于关联多次调用。 同一个剧本任务ID应该一致
        config: 可选的LLM实例，如果不提供，将自动初始化（需要配置env参数）

    Returns:
        包含分镜列表的完整结果
    """
    # 创建并运行多智能体管道
    set_language(language.value)
    workflow = MultiAgentPipeline(config=config, task_id=task_id)
    return await  workflow.run_process(
        raw_script=script_text,
        config=config
    )
