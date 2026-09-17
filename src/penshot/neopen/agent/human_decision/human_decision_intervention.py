# human_decision_intervention.py - 优化后的版本（保留控制台交互）
"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: human_decision_intervention.py
@Description: 人工干预工作流节点 - 控制台版本
@Author: NeoPen
@Time: 2026/2/5 17:28
"""
import threading
import time
from dataclasses import dataclass
from typing import Optional

from penshot.logger import info, warning, error
from penshot.neopen.agent.human_decision.human_decision_converter import HumanDecisionConverter
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


@dataclass
class UserInputResult:
    """用户输入结果"""
    decision: str
    timeout: bool
    auto_decision: bool
    timestamp: float
    raw_input: str


class ConsoleInputHandler:
    """控制台输入处理器 - 负责输入采集和超时控制"""

    # 有效决策选项
    VALID_DECISIONS = {
        "1": "CONTINUE",
        "2": "APPROVE",
        "3": "RETRY",
        "4": "REPAIR",
        "5": "ESCALATE",
        "6": "ABORT",
    }

    def __init__(self, timeout_seconds: int = 180):
        self.timeout_seconds = timeout_seconds
        self._input_received = False
        self._user_input: Optional[str] = None
        self._timeout_occurred = False
        self._lock = threading.Lock()

    def get_input_with_timeout(self) -> UserInputResult:
        """获取用户输入（带超时控制）"""
        self._display_prompt()

        # 启动输入线程
        input_thread = threading.Thread(target=self._input_thread, daemon=True)
        input_thread.start()

        # 等待输入或超时
        start_time = time.time()
        while not self._input_received and (time.time() - start_time) < self.timeout_seconds:
            time.sleep(0.1)

        with self._lock:
            if self._timeout_occurred:
                warning("人工输入超时，使用默认继续决策")
                return UserInputResult(
                    decision="CONTINUE",
                    timeout=True,
                    auto_decision=True,
                    timestamp=time.time(),
                    raw_input=""
                )
            elif self._user_input:
                info(f"接收到人工输入: {self._user_input}")
                return UserInputResult(
                    decision=self._user_input,
                    timeout=False,
                    auto_decision=False,
                    timestamp=time.time(),
                    raw_input=self._user_input
                )
            else:
                warning("未接收到有效输入，使用默认继续决策")
                return UserInputResult(
                    decision="CONTINUE",
                    timeout=False,
                    auto_decision=True,
                    timestamp=time.time(),
                    raw_input=""
                )

    def _display_prompt(self):
        """显示输入提示"""
        print("\n" + "=" * 60)
        print("AI视频生成系统 - 人工干预节点")
        print("=" * 60)
        print(f"\n系统需要人工决策以继续处理")
        print(f"等待时间: {self.timeout_seconds}秒 ({self.timeout_seconds // 60}分钟)")

        print("\n请选择下一步操作:")
        options = [
            ("1", "CONTINUE", "继续流程（默认）"),
            ("2", "APPROVE", "批准通过"),
            ("3", "RETRY", "重新开始"),
            ("4", "REPAIR", "修复问题"),
            ("5", "ESCALATE", "升级处理"),
            ("6", "ABORT", "中止流程"),
        ]
        for num, code, desc in options:
            print(f"  [{num}] {code:10} - {desc}")

        print("\n输入选项编号 (1-6) 或输入选项名称: ", end="", flush=True)

    def _input_thread(self):
        """输入采集线程"""
        try:
            # 使用 sys.stdin.readline() 替代 input()，并处理编码问题
            import sys
            try:
                # 尝试读取输入
                line = sys.stdin.readline()
                if line:
                    # 处理可能的编码问题
                    if isinstance(line, bytes):
                        raw_input = line.decode('utf-8', errors='replace').strip()
                    else:
                        raw_input = line.strip()
                else:
                    raw_input = ""
            except (UnicodeDecodeError, OSError) as e:
                # 处理编码错误或输入流关闭的情况
                warning(f"输入编码错误: {str(e)}")
                raw_input = ""

            with self._lock:
                if raw_input.isdigit():
                    self._user_input = self.VALID_DECISIONS.get(raw_input, "CONTINUE")
                else:
                    # 验证输入是否为有效决策
                    upper_input = raw_input.upper() if raw_input else "CONTINUE"
                    valid_values = set(self.VALID_DECISIONS.values())
                    self._user_input = upper_input if upper_input in valid_values else "CONTINUE"

                self._input_received = True

        except Exception as e:
            error(f"输入线程异常: {str(e)}")
            with self._lock:
                self._user_input = "CONTINUE"
                self._input_received = True


class HumanIntervention:
    """人工干预工作流节点（控制台版本）

    职责：
    1. 显示当前状态信息给用户
    2. 从控制台获取人工输入（带超时控制）
    3. 将输入保存到状态中
    4. 返回更新后的状态
    """

    def __init__(self, timeout_seconds: int = 180):
        """
        初始化人工干预节点

        Args:
            timeout_seconds: 超时时间，默认3分钟
        """
        self.timeout_seconds = timeout_seconds
        self.converter = HumanDecisionConverter()
        self.input_handler = ConsoleInputHandler(timeout_seconds)

    def __call__(self, graph_state: WorkflowState) -> WorkflowState:
        """执行人工干预节点"""
        print("\n" + "=" * 60)
        print("AI视频生成 - 人工决策节点")
        print("=" * 60)

        # 显示状态信息
        self._display_state_info(graph_state)

        # 获取用户输入
        result = self.input_handler.get_input_with_timeout()

        # 更新状态
        graph_state.execution.human_feedback = {
            "decision": result.decision,
            "timeout": result.timeout,
            "auto_decision": result.auto_decision,
            "timestamp": result.timestamp,
            "raw_input": result.raw_input,
        }

        # 显示用户选择结果
        self._display_decision_result(result.decision)

        return graph_state

    def _display_state_info(self, state: WorkflowState):
        """显示状态信息"""
        print("\n当前状态:")
        print("-" * 40)

        print(f"任务ID: {state.input.task_id}")
        print(f"当前阶段: {state.execution.current_stage}")

        if state.errors.error_messages:
            print(f"错误: {len(state.errors.error_messages)}个")
            for i, err in enumerate(state.errors.error_messages[-2:], 1):
                truncated = err[:60] + "..." if len(err) > 60 else err
                print(f"     {i}. {truncated}")

        if state.execution.total_retries > 0:
            print(f"重试: {state.execution.total_retries}/{state.execution.global_max_loops}")

        if state.domain.audit_report:
            status = state.domain.audit_report.status.value
            print(f"质量: {status}")

        if state.domain.continuity_issues:
            print(f"连续性: {len(state.domain.continuity_issues)}个问题")

        print("-" * 40)

    def _display_decision_result(self, decision: str):
        """显示决策结果"""
        normalized = self.converter.normalize_input(decision)
        decision_state = self.converter.convert_to_decision_state(normalized)
        decision_desc = self.converter.get_decision_description(decision_state)

        print(f"\n已选择: {decision}")
        print(f"标准化: {normalized}")
        print(f"决策: {decision_state.value} ({decision_desc})")
