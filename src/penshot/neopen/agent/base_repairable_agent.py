"""
@FileName: base_repairable_agent.py
@Description: 可修复智能体基类 - 定义统一的修复接口
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/3/28
"""
import time
from abc import abstractmethod
from typing import Optional, List, Dict, Any, TypeVar, Generic

from penshot.neopen.agent.base_agent import BaseAgent
from penshot.neopen.agent.quality_auditor.quality_auditor_models import BasicViolation, QualityRepairParams

T = TypeVar('T')  # 输出类型泛型
K = TypeVar('K')  # 输出类型泛型


class BaseRepairableAgent(BaseAgent, Generic[T, K]):
    """
    可修复智能体基类

    定义统一的修复接口，所有需要支持修复的智能体都应继承此类
    """

    def __init__(self):
        """初始化"""
        self.repair_history: List[Dict[str, Any]] = []
        self.current_repair_params: Optional[QualityRepairParams] = None

    @abstractmethod
    def process(self, *args, **kwargs) -> Optional[T]:
        """
        核心处理方法 - 子类必须实现

        Returns:
            处理结果
        """
        pass

    @abstractmethod
    def detect_issues(self, result: T, node_params: K) -> List[BasicViolation]:
        """
        检测结果中的问题

        Args:
            result: 处理结果
            node_params: 节点所需参数

            , *args, **kwargs

        Returns:
            问题列表
        """
        pass

    def apply_repair_params(self, repair_params: QualityRepairParams) -> None:
        """
        应用修复参数（在下次执行时生效）

        调用时机：在 process 方法执行之前，由工作流节点调用
        作用：将修复参数保存到 self.current_repair_params，供 process 方法使用
        """
        self.current_repair_params = repair_params

        # 记录修复历史
        self.repair_history.append({
            "timestamp": time.time(),
            "repair_params": {
                "issue_types": repair_params.issue_types,
                "suggestions": repair_params.suggestions
            }
        })

        # 子类可以重写此方法，根据修复参数调整内部状态
        self._on_repair_params_applied()

    def _on_repair_params_applied(self) -> None:
        """
        修复参数应用后的回调方法

        子类可以重写此方法，根据 self.current_repair_params 调整内部配置
        例如：增加镜头数量、缩短时长阈值等
        """
        pass

    def repair_result(self, result: T, issues: List[BasicViolation], node_params: K) -> T:
        """
        修复已有结果（后处理修复）

        调用时机：质量审查后立即调用，不等待重试
        作用：直接修正已经生成的结果
        """
        # 记录修复历史
        self.repair_history.append({
            "timestamp": time.time(),
            "issues_count": len(issues),
            "repair_type": "post_process"
        })

        return result

    def clear_repair_params(self) -> None:
        """清空当前修复参数（修复成功后调用）"""
        self.current_repair_params = None

    def get_repair_history(self) -> List[Dict[str, Any]]:
        """获取修复历史"""
        return self.repair_history

    def clear_repair_history(self):
        """清空修复历史"""
        self.repair_history = []
