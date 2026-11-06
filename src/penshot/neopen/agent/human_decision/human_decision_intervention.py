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
from typing import Any, Dict, List, Optional

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
        "7": "EDIT_ASSET",
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
        print("\n系统需要人工决策以继续处理")
        print(f"等待时间: {self.timeout_seconds}秒 ({self.timeout_seconds // 60}分钟)")

        print("\n请选择下一步操作:")
        options = [
            ("1", "CONTINUE", "继续流程（默认）"),
            ("2", "APPROVE", "批准通过"),
            ("3", "RETRY", "重新开始"),
            ("4", "REPAIR", "修复问题"),
            ("5", "ESCALATE", "升级处理"),
            ("6", "ABORT", "中止流程"),
            ("7", "EDIT_ASSET", "编辑资产提示词"),
        ]
        for num, code, desc in options:
            print(f"  [{num}] {code:10} - {desc}")

        print("\n输入选项编号 (1-7) 或输入选项名称: ", end="", flush=True)

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

        decision = result.decision
        asset_edits = []

        # 选择编辑资产时，继续采集具体修改内容；无资产或未修改则回退为继续
        if self.converter.normalize_input(decision) == "EDIT_ASSET":
            asset_edits = self._collect_asset_edits(graph_state)
            if not asset_edits:
                warning("未进行有效的资产提示词编辑，回退为继续流程")
                decision = "CONTINUE"

        # 更新状态
        graph_state.execution.human_feedback = {
            "decision": decision,
            "timeout": result.timeout,
            "auto_decision": result.auto_decision,
            "timestamp": result.timestamp,
            "raw_input": result.raw_input,
            "asset_edits": asset_edits,
        }

        # 编辑记录跨多次人工干预累计保留，避免后续回填/重试覆盖
        if asset_edits:
            graph_state.execution.asset_prompt_edits.extend(asset_edits)

        # 显示用户选择结果
        self._display_decision_result(decision)

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

        self._display_asset_plan(state)

        print("-" * 40)

    def _display_asset_plan(self, state: WorkflowState):
        """显示资产提示词摘要，便于人工判断是否需要编辑"""
        plan = state.domain.asset_plan or {}
        assets = plan.get("assets", [])
        if not assets:
            return

        print(f"资产计划: {len(assets)}个")
        for index, asset in enumerate(assets, 1):
            asset_id = asset.get("asset_id", "")
            asset_type = asset.get("asset_type", "")
            owner = asset.get("owner_name", "")
            status = asset.get("status", "")
            prompt = asset.get("image_prompt", "")
            if len(prompt) > 80:
                prompt = prompt[:80] + "..."
            print(f"  [{index}] {asset_id} ({asset_type}/{owner}) 状态={status}")
            print(f"      正向: {prompt}")
            negative = asset.get("negative_prompt", "")
            if negative:
                if len(negative) > 60:
                    negative = negative[:60] + "..."
                print(f"      负向: {negative}")

    def _collect_asset_edits(self, state: WorkflowState) -> List[Dict[str, Any]]:
        """采集人工资产提示词编辑，返回可回写的编辑记录"""
        plan = state.domain.asset_plan or {}
        assets = plan.get("assets", [])
        if not assets:
            print("\n当前没有可编辑的资产计划。")
            return []

        print("\n资产编辑说明: 输入编号选择资产，仅修改提示词字段，回车保持原值。")
        edits: List[Dict[str, Any]] = []

        while True:
            try:
                raw_index = input("\n请输入要编辑的资产编号（直接回车结束）: ").strip()
                if not raw_index:
                    break

                index = int(raw_index)
                if index < 1 or index > len(assets):
                    print(f"编号超出范围，请输入 1-{len(assets)}")
                    continue

                asset = assets[index - 1]
                asset_id = asset.get("asset_id", "")
                print(f"\n当前资产: {asset_id}")
                print(f"正向提示词: {asset.get('image_prompt', '')}")
                print(f"负向提示词: {asset.get('negative_prompt', '')}")

                field = input(
                    "选择字段 [1] 正向 [2] 负向 [3] 两者（默认1）: "
                ).strip() or "1"

                edit: Dict[str, Any] = {
                    "asset_id": asset_id,
                    "source": "human_intervention",
                    "revision_id": f"human-{int(time.time())}",
                }

                if field in ("1", "3"):
                    image_prompt = input("新的正向提示词（回车保持不变）: ").strip()
                    if image_prompt:
                        edit["image_prompt"] = image_prompt

                if field in ("2", "3"):
                    negative_prompt = input(
                        "新的负向提示词（回车保持不变）: "
                    ).strip()
                    if negative_prompt:
                        edit["negative_prompt"] = negative_prompt

                if "image_prompt" not in edit and "negative_prompt" not in edit:
                    print("未修改任何字段，已跳过。")
                    continue

                edits.append(edit)
                print(f"已记录对 {asset_id} 的提示词编辑。")

                again = input("继续编辑其他资产？[y/N]: ").strip().lower()
                if again not in ("y", "yes", "是"):
                    break
            except (EOFError, KeyboardInterrupt):
                print("\n已结束资产编辑。")
                break
            except ValueError:
                print("请输入有效的数字编号。")
                continue

        return edits

    def _display_decision_result(self, decision: str):
        """显示决策结果"""
        normalized = self.converter.normalize_input(decision)
        decision_state = self.converter.convert_to_decision_state(normalized)
        decision_desc = self.converter.get_decision_description(decision_state)

        print(f"\n已选择: {decision}")
        print(f"标准化: {normalized}")
        print(f"决策: {decision_state.value} ({decision_desc})")
