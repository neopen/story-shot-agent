"""
@FileName: llm_quality_auditor.py
@Description: LLM深度审查器 - 只负责LLM审查逻辑
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/27 0:00
"""
import json
import re
import time
from typing import Dict, Any, Optional, List

from penshot.logger import info, error, debug
from penshot.neopen.agent.base_llm_agent import BaseLLMAgent
from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoInstructions, AIVideoPrompt
from penshot.neopen.agent.quality_auditor.base_quality_auditor import BaseQualityAuditor
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    QualityAuditReport, AuditStatus, IssueType, SeverityLevel, RuleType
)
from penshot.neopen.shot_config import ShotConfig
from penshot.utils.log_utils import print_log_exception


class LLMQualityAuditor(BaseQualityAuditor, BaseLLMAgent):
    """LLM深度审查器 - 只负责LLM审查，不合并结果"""

    def __init__(self, llm_client, config: Optional[ShotConfig]):
        super().__init__(config)
        self.llm_client = llm_client
        self.last_llm_result = None
        self.last_audit_time = 0

    # llm_quality_auditor.py - 修改 audit 和 _call_llm_audit 方法

    def audit(self, instructions: AIVideoInstructions,
              historical_context: Optional[Dict[str, Any]] = None) -> QualityAuditReport:
        """执行LLM深度审查"""
        info(f"执行LLM深度审查，片段数: {len(instructions.fragments)}")

        if self._should_run_llm_audit(instructions):
            try:
                # 将历史上下文传递给 LLM 调用
                llm_result = self._call_llm_audit(instructions, historical_context)
                validated_result = self._validate_llm_result(llm_result, instructions)
                self.last_llm_result = validated_result
                self.last_audit_time = time.time()
                return self._convert_to_report(validated_result, instructions)
            except Exception as e:
                error(f"LLM审查失败: {str(e)}")
                print_log_exception()
                return self._create_error_report(instructions, str(e))
        else:
            info("使用缓存的LLM审查结果")
            return self._convert_to_report(self.last_llm_result, instructions)

    def _call_llm_audit(self, instructions: AIVideoInstructions,
                        historical_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """调用LLM进行审查"""
        fragments_data = []
        for i, frag in enumerate(instructions.fragments):
            frag_data = {
                "id": frag.fragment_id,
                "duration": frag.duration,
                "prompt": frag.prompt[:300] + "..." if len(frag.prompt) > 300 else frag.prompt,
                "model": frag.model,
                "index": i
            }
            fragments_data.append(frag_data)

        # 构建基础用户提示词
        user_prompt = self._build_audit_prompt(instructions)

        # 构建历史上下文提示
        history_hint = self._build_history_hint(historical_context)

        # 如果有历史上下文，将其整合到提示词中
        if history_hint:
            user_prompt = f"{user_prompt}\n\n{history_hint}"

        system_prompt = self._get_prompt_template("quality_auditor_system")

        debug("调用LLM进行质量审查")

        try:
            response = self._call_llm_parse_with_retry(
                self.llm_client, system_prompt, user_prompt, max_retries=2
            )

            if isinstance(response, str):
                try:
                    result = json.loads(response)
                except json.JSONDecodeError:
                    result = self._extract_json_from_text(response)
            else:
                result = response

            return self._normalize_llm_result(result, fragments_data)

        except Exception as e:
            error(f"LLM审查调用失败: {str(e)}")
            return {
                "status": AuditStatus.WARNING,
                "summary": "LLM审查执行失败",
                "issues": [],
                "fragments_checked": [f["id"] for f in fragments_data],
                "quality_score": 0,
                "timestamp": time.time()
            }

    def _build_history_hint(self, historical_context: Optional[Dict[str, Any]]) -> str:
        """构建历史上下文提示"""
        if not historical_context:
            return ""

        hints = []

        # 1. 历史审计结果
        historical_audit_results = historical_context.get("historical_audit_results")
        if historical_audit_results and isinstance(historical_audit_results, list):
            issue_stats = {}
            for result in historical_audit_results[-20:]:
                status = result.get("status") if isinstance(result, dict) else getattr(result, "status", None)
                if status in ["failed", "critical"]:
                    violations = result.get("violations", []) if isinstance(result, dict) else getattr(result, "violations", [])
                    for v in violations:
                        issue_type = self._extract_issue_type(v)
                        issue_stats[issue_type] = issue_stats.get(issue_type, 0) + 1

            if issue_stats:
                sorted_issues = sorted(issue_stats.items(), key=lambda x: x[1], reverse=True)
                top_issues = [f"{t}({c}次)" for t, c in sorted_issues[:3]]
                hints.append(f"【历史常见问题】{', '.join(top_issues)}，请重点关注这些问题类型。")

        # 2. 成功修复模式
        successful_repair_patterns = historical_context.get("successful_repair_patterns")
        if successful_repair_patterns and isinstance(successful_repair_patterns, list):
            successful_issue_types = set()
            for pattern in successful_repair_patterns[:10]:
                if isinstance(pattern, dict):
                    issue_types = pattern.get("issue_types", [])
                    successful_issue_types.update(issue_types)

            if successful_issue_types:
                hints.append(f"【历史成功修复】以下问题类型有成功修复经验: {', '.join(list(successful_issue_types)[:5])}，可参考历史修复策略。")

        # 3. 历史质量趋势
        if historical_audit_results and len(historical_audit_results) >= 5:
            recent_scores = []
            for r in historical_audit_results[-5:]:
                if isinstance(r, dict):
                    score = r.get("score", 0)
                else:
                    score = getattr(r, "score", 0)
                recent_scores.append(score)
            avg_score = sum(recent_scores) / len(recent_scores)
            if avg_score < 70:
                hints.append(f"【质量趋势】近期审查平均分数偏低({avg_score:.0f}分)，建议严格审查。")
            elif avg_score > 85:
                hints.append(f"【质量趋势】近期审查质量良好({avg_score:.0f}分)，保持标准。")

        if not hints:
            return ""

        return "\n".join([
            "",
            "=" * 40,
            "【历史审查参考】",
            *hints,
            "=" * 40,
            ""
        ])


    def _should_run_llm_audit(self, instructions: AIVideoInstructions) -> bool:
        """判断是否应该执行LLM审查"""
        if self.last_llm_result is None:
            return True
        if time.time() - self.last_audit_time > 300:
            return True
        if len(instructions.fragments) != len(self.last_llm_result.get("fragments_checked", [])):
            return True
        return False


    def _build_audit_prompt(self, instructions: AIVideoInstructions) -> str:
        """构建审查提示词"""
        fragments_list = []
        for i, frag in enumerate(instructions.fragments):
            prompt_preview = frag.prompt[:200] + "..." if len(frag.prompt) > 200 else frag.prompt
            fragments_list.append(
                f"  {i + 1}. [{frag.fragment_id}] {frag.duration}秒: {prompt_preview}"
            )

        fragments_text = "\n".join(fragments_list)

        prompt_template = self._get_prompt_template("quality_auditor_user")

        return prompt_template.format(
            title=instructions.project_info.get("title", "未命名项目"),
            fragment_count=len(instructions.fragments),
            total_duration=instructions.project_info.get("total_duration", 0.0),
            fragments_list=fragments_text
        )

    def _validate_llm_result(self, llm_result: Dict, instructions: AIVideoInstructions) -> Dict:
        """验证LLM结果，过滤误报"""
        validated_issues = []
        false_positive_count = 0

        for issue in llm_result.get("issues", []):
            fragment = self._find_fragment(instructions, issue.get("fragment_id"))
            if not fragment:
                false_positive_count += 1
                continue

            if self._is_false_positive(issue, fragment):
                debug(f"检测到误报: {issue.get('description', '')[:50]}...")
                false_positive_count += 1
                continue

            validated_issues.append(issue)

        llm_result["issues"] = validated_issues
        llm_result["false_positives_filtered"] = false_positive_count
        return llm_result

    def _is_false_positive(self, issue: Dict, fragment: AIVideoPrompt) -> bool:
        """判断是否为误报"""
        issue_type = issue.get("type", "")
        description = issue.get("description", "").lower()

        if issue_type == IssueType.TRUNCATION:
            if not self._is_truly_truncated(fragment.prompt):
                return True
        elif issue_type == IssueType.DURATION:
            if 0.5 <= fragment.duration <= 5.0:
                return True
        elif issue_type == IssueType.WEATHER:
            if not self._has_weather_conflict(fragment.prompt):
                return True
        elif issue_type == IssueType.CHARACTER:
            if self._has_character_consistency(fragment):
                return True
        elif issue_type == IssueType.ACTION:
            if self._has_action_description(fragment.prompt):
                return True

        return False

    def _is_truly_truncated(self, prompt: str) -> bool:
        """判断提示词是否真的被截断"""
        truncation_markers = ['...', '…', 'wea', 'som', 'the ', 'and ']
        end_markers = ['.', '!', '?', ';', ':', '"]', '}', '）', '）']
        last_100_chars = prompt[-100:] if len(prompt) > 100 else prompt

        has_truncation = any(marker in last_100_chars for marker in truncation_markers)
        has_end = any(marker in last_100_chars[-10:] for marker in end_markers)

        return has_truncation and not has_end

    def _has_weather_conflict(self, prompt: str) -> bool:
        """检查是否有气象冲突"""
        prompt_lower = prompt.lower()
        has_rain = any(word in prompt_lower for word in ["rain", "rainy", "下雨", "雨", "wet"])
        has_golden_hour = "golden hour" in prompt_lower
        has_sunny = any(word in prompt_lower for word in ["sunny", "sunlight", "晴天", "阳光"])
        has_overcast = any(word in prompt_lower for word in ["overcast", "阴天", "灰蒙蒙", "cloudy"])

        return (has_rain and has_golden_hour) or (has_rain and has_sunny) or (has_overcast and has_golden_hour)

    def _has_character_consistency(self, fragment: AIVideoPrompt) -> bool:
        """检查角色一致性"""
        character_keywords = ['character', '角色', 'person', '人', 'man', 'woman', 'girl', 'boy']
        prompt_lower = fragment.prompt.lower()
        return any(keyword in prompt_lower for keyword in character_keywords)

    def _has_action_description(self, prompt: str) -> bool:
        """检查是否有动作描述"""
        action_keywords = ['action', '动作', 'move', '运动', '动态', 'walk', 'run', 'jump', 'turn']
        prompt_lower = prompt.lower()
        return any(keyword in prompt_lower for keyword in action_keywords)

    def _find_fragment(self, instructions: AIVideoInstructions, fragment_id: str) -> Optional[AIVideoPrompt]:
        """查找片段"""
        if not fragment_id or fragment_id == "unknown":
            return None
        for frag in instructions.fragments:
            if frag.fragment_id == fragment_id:
                return frag
        return None

    def _normalize_llm_result(self, result: Dict, fragments_data: List[Dict]) -> Dict:
        """规范化LLM结果"""
        normalized = {
            "status": self._normalize_status(result.get("status", "NEEDS_REVIEW")),
            "summary": result.get("summary", "LLM审查完成"),
            "issues": [],
            "fragments_checked": [f["id"] for f in fragments_data],
            "quality_score": result.get("quality_score", 80.0),
            "timestamp": time.time()
        }

        issues = result.get("issues", [])
        if isinstance(issues, list):
            for issue in issues:
                if isinstance(issue, dict):
                    normalized_issue = {
                        "fragment_id": issue.get("fragment_id", "unknown"),
                        "type": self._normalize_issue_type(issue.get("type", "OTHER")),
                        "description": issue.get("description", ""),
                        "severity": self._normalize_severity(issue.get("severity", "WARNING")),
                        "suggestion": issue.get("suggestion", "")
                    }
                    normalized["issues"].append(normalized_issue)

        return normalized

    def _normalize_status(self, status: str) -> str:
        if not status:
            return AuditStatus.NEEDS_REVIEW.value
        status_upper = status.upper()
        for status_enum in AuditStatus:
            if status_enum.name == status_upper:
                return status_enum.value
        return AuditStatus.NEEDS_REVIEW.value

    def _normalize_issue_type(self, issue_type: str) -> str:
        if not issue_type:
            return IssueType.OTHER.value
        issue_type_upper = issue_type.upper()
        for issue_enum in IssueType:
            if issue_enum.name == issue_type_upper:
                return issue_enum.value
        return IssueType.OTHER.value

    def _normalize_severity(self, severity: str) -> str:
        if not severity:
            return SeverityLevel.WARNING.value
        severity_upper = severity.upper()
        for severity_enum in SeverityLevel:
            if severity_enum.name == severity_upper:
                return severity_enum.value
        return SeverityLevel.WARNING.value

    def _convert_to_report(self, llm_result: Dict, instructions: AIVideoInstructions) -> QualityAuditReport:
        """转换为报告格式（不包含基本规则结果）"""
        report = QualityAuditReport(
            project_info={
                "title": instructions.project_info.get("title", "未命名项目"),
                "fragment_count": len(instructions.fragments),
                "total_duration": instructions.project_info.get("total_duration", 0.0)
            },
            status=llm_result.get("status", AuditStatus.NEEDS_REVIEW),
            checks=[],
            violations=[]
        )

        for issue in llm_result.get("issues", []):
            self._add_violation(
                report=report,
                rule_type=RuleType.LLM_COHERENCE,
                issue_type=issue.get("type", IssueType.OTHER),
                description=issue.get("description", ""),
                severity=issue.get("severity", SeverityLevel.WARNING),
                fragment_id=issue.get("fragment_id"),
                suggestion=issue.get("suggestion")
            )

        report.score = llm_result.get("quality_score", 80.0)
        return report

    def _create_error_report(self, instructions: AIVideoInstructions, error_msg: str) -> QualityAuditReport:
        """创建错误报告"""
        return QualityAuditReport(
            project_info={
                "title": instructions.project_info.get("title", "未命名项目"),
                "fragment_count": len(instructions.fragments),
                "total_duration": instructions.project_info.get("total_duration", 0.0)
            },
            status=AuditStatus.WARNING,
            checks=[],
            violations=[]
        )

    def _extract_json_from_text(self, text: str) -> Dict:
        """从文本中提取JSON"""
        json_pattern = r'\{[^{}]*\}'
        matches = re.findall(json_pattern, text)
        for match in matches:
            try:
                return json.loads(match)
            except:
                continue
        return {}
