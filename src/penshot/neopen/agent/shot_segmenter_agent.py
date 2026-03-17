"""
@FileName: shot_generator_agent.py
@Description: 分镜生成智能体
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10 - 2025/11
"""
from typing import Optional

from penshot.neopen.agent.base_models import AgentMode
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.estimator.estimator_enhancer import DurationEnhancer
from penshot.neopen.agent.shot_segmenter.estimator.estimator_factory import estimator_factory
from penshot.neopen.agent.shot_segmenter.shot_segmenter_factory import ShotSegmenterFactory
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import debug, info, error
from penshot.utils.log_utils import print_log_exception


class ShotSegmenterAgent:
    """分镜生成智能体"""

    def __init__(self, llm, config: ShotConfig):
        """
        初始化分镜生成智能体
        
        Args:
            llm: 语言模型实例
        """
        self.llm = llm
        self.config = config or {}

        if self.config.enable_llm:
            self.segmenter = ShotSegmenterFactory.create_segmenter(AgentMode.LLM, self.config, self.llm)
        else:
            self.segmenter = ShotSegmenterFactory.create_segmenter(AgentMode.RULE, self.config)

        # 时长增强器
        self.enhancer = DurationEnhancer() if self.config.enable_enhance else None

        # 配置
        self.llm_confidence = config.llm_confidence or 0.7
        self.always_enhance = config.always_enhance or True

    def shot_process(self, structured_script: ParsedScript) -> Optional[ShotSequence]:
        """
        规划剧本的时序分段并估算时长

        Args:
            structured_script: 结构化的剧本

        Returns:
            带时长估算的镜头序列
        """
        debug("开始拆分镜头并估算时长")

        try:
            # 1. 先生成分镜（LLM或规则）
            shot_sequence = self.segmenter.split(structured_script)

            if not shot_sequence:
                error("分镜生成失败")
                return None

            info(f"分镜生成完成: {len(shot_sequence.shots)}个镜头")

            # 2. 估算每个镜头的时长
            shot_sequence = estimator_factory.estimate_sequence(shot_sequence, structured_script)

            # 3. 如果启用增强，进行后处理优化
            if self.enhancer and (self.always_enhance or self.config.enable_llm):
                debug("应用时长增强优化")
                enhanced_sequence, corrections = self.enhancer.enhance(
                    shot_sequence,
                    structured_script,
                    base_confidence=self.llm_confidence
                )

                if corrections:
                    info(f"时长增强: 修正{len(corrections)}个镜头")
                    for corr in corrections[:5]:  # 只显示前5个
                        debug(f"  {corr.shot_id}: {corr.original_duration}s -> {corr.corrected_duration}s ({corr.reasons})")

                return enhanced_sequence

            return shot_sequence

        except Exception as e:
            print_log_exception()
            error(f"镜头拆分异常: {e}")
            return None
