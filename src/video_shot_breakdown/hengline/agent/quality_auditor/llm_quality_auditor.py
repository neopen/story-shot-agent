"""
@FileName: llm_quality_auditor.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/27 0:00
"""
import json
import re
import time
from typing import Dict, Any, Optional, List

from video_shot_breakdown.hengline.agent.base_agent import BaseAgent
from video_shot_breakdown.hengline.agent.prompt_converter.prompt_converter_models import AIVideoInstructions, AIVideoPrompt
from video_shot_breakdown.hengline.agent.quality_auditor.base_quality_auditor import BaseQualityAuditor
from video_shot_breakdown.hengline.agent.quality_auditor.quality_auditor_models import QualityAuditReport, AuditStatus, IssueType, SeverityLevel
from video_shot_breakdown.hengline.agent.quality_auditor.rule_quality_auditor import RuleQualityAuditor
from video_shot_breakdown.hengline.hengline_config import HengLineConfig
from video_shot_breakdown.logger import info, error, debug


class LLMQualityAuditor(BaseQualityAuditor, BaseAgent):
    """基于LLM的质量审查器"""

    def __init__(self, llm_client, config: Optional[HengLineConfig]):
        super().__init__(config)
        self.llm_client = llm_client
        self.basic_auditor = RuleQualityAuditor(config)

        # 缓存上次的LLM审查结果，避免重复调用
        self.last_llm_result = None
        self.last_audit_time = 0


    def audit(self, instructions: AIVideoInstructions) -> QualityAuditReport:
        """使用LLM进行质量审查"""
        info(f"使用LLM进行质量审查，片段数: {len(instructions.fragments)}")

        # 1. 先执行基本规则检查
        basic_report = self.basic_auditor.audit(instructions)

        # 2. 检查是否需要执行LLM审查（避免频繁调用）
        if self._should_run_llm_audit(instructions):
            try:
                info("执行LLM深度审查")
                llm_result = self._call_llm_audit_fixed(instructions)

                # 验证LLM结果，过滤误报
                validated_result = self._validate_llm_result(llm_result, instructions)

                # 合并结果
                self._merge_llm_result_fixed(basic_report, validated_result)

                # 更新缓存
                self.last_llm_result = validated_result
                self.last_audit_time = time.time()

            except Exception as e:
                error(f"LLM审查失败: {str(e)}")
                # 添加错误标记但不中断流程
                self._add_check(
                    basic_report,
                    "LLM审查状态",
                    AuditStatus.WARNING,
                    f"LLM审查执行失败: {str(e)[:100]}"
                )
        else:
            info("跳过LLM审查（使用缓存或无需执行）")
            if self.last_llm_result:
                self._merge_llm_result_fixed(basic_report, self.last_llm_result)

        # 3. 修复统计信息
        fixed_report = self._fix_report_statistics(basic_report)

        # 4. 后处理
        return self.post_process(fixed_report)

    def _should_run_llm_audit(self, instructions: AIVideoInstructions) -> bool:
        """判断是否应该执行LLM审查"""
        # 如果没有缓存结果，需要执行
        if self.last_llm_result is None:
            return True

        # 如果超过5分钟，重新执行
        if time.time() - self.last_audit_time > 300:
            return True

        # 如果片段数量变化，重新执行
        if len(instructions.fragments) != len(self.last_llm_result.get("fragments_checked", [])):
            return True

        return False

    def _call_llm_audit_fixed(self, instructions: AIVideoInstructions) -> Dict[str, Any]:
        """LLM审查调用"""
        # 准备完整的片段信息
        fragments_data = []
        for i, frag in enumerate(instructions.fragments):
            frag_data = {
                "id": frag.fragment_id,
                "duration": frag.duration,
                "prompt": frag.prompt,
                "model": frag.model,
                "index": i
            }
            fragments_data.append(frag_data)

        # 构建审查提示词
        user_prompt = self._build_audit_prompt(instructions)
        system_prompt = self._get_prompt_template("quality_auditor_system")

        debug("调用LLM进行质量审查")

        try:
            # 调用LLM
            response = self._call_llm_parse_with_retry(
                self.llm_client,
                system_prompt,
                user_prompt,
                max_retries=2
            )

            # 解析响应
            if isinstance(response, str):
                try:
                    result = json.loads(response)
                except json.JSONDecodeError:
                    # 尝试提取JSON
                    result = self._extract_json_from_text(response)
            else:
                result = response

            # 确保结果格式正确
            return self._normalize_llm_result(result, fragments_data)

        except Exception as e:
            error(f"LLM审查调用失败: {str(e)}")
            # 返回空结果
            return {
                "status": AuditStatus.WARNING,
                "summary": "LLM审查执行失败",
                "issues": [],
                "fragments_checked": [f["id"] for f in fragments_data],
                "timestamp": time.time()
            }

    def _build_audit_prompt(self, instructions: AIVideoInstructions) -> str:
        """构建审查提示词"""
        # 准备片段列表文本
        fragments_list = []
        for i, frag in enumerate(instructions.fragments):
            # 截取适当长度的提示词，避免token超限
            prompt_preview = frag.prompt[:300] + "..." if len(frag.prompt) > 300 else frag.prompt
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

    def _extract_json_from_text(self, text: str) -> Dict:
        """从文本中提取JSON"""
        import re

        # 查找JSON对象
        json_pattern = r'\{[^{}]*\}'
        matches = re.findall(json_pattern, text)

        for match in matches:
            try:
                return json.loads(match)
            except:
                continue

        return {}

    def _normalize_llm_result(self, result: Dict, fragments_data: List[Dict]) -> Dict:
        """规范化LLM结果格式"""
        normalized = {
            "status": self._normalize_status(result.get("status", "NEEDS_REVIEW")),
            "summary": result.get("summary", "LLM审查完成"),
            "issues": [],
            "fragments_checked": [f["id"] for f in fragments_data],
            "timestamp": time.time()
        }

        # 规范化问题列表
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
        """规范化状态 - 直接使用AuditStatus枚举"""
        if not status:
            return AuditStatus.NEEDS_REVIEW.value

        # 将输入转换为大写
        status_upper = status.upper()

        # 遍历AuditStatus枚举，查找匹配的key
        for status_enum in AuditStatus:
            if status_enum.name == status_upper:
                return status_enum.value

        # 如果没有匹配，返回NEEDS_REVIEW
        return AuditStatus.NEEDS_REVIEW.value

    def _normalize_issue_type(self, issue_type: str) -> str:
        """规范化问题类型 - 直接从IssueType枚举获取值"""
        if not issue_type:
            return IssueType.OTHER.value

        # 将输入转换为大写
        issue_type_upper = issue_type.upper()

        # 遍历IssueType枚举，查找匹配的key
        for issue_enum in IssueType:
            if issue_enum.name == issue_type_upper:
                return issue_enum.value

        # 如果没有匹配，返回OTHER
        return IssueType.OTHER.value

    def _normalize_severity(self, severity: str) -> str:
        """规范化严重程度 - 直接从SeverityLevel枚举获取值"""
        if not severity:
            return SeverityLevel.WARNING.value

        # 将输入转换为大写
        severity_upper = severity.upper()

        # 遍历SeverityLevel枚举，查找匹配的key
        for severity_enum in SeverityLevel:
            if severity_enum.name == severity_upper:
                return severity_enum.value

        # 如果没有匹配，返回WARNING
        return SeverityLevel.WARNING.value


    def _validate_llm_result(self, llm_result: Dict,
                             instructions: AIVideoInstructions) -> Dict:
        """验证LLM结果，过滤误报"""
        validated_issues = []
        false_positive_count = 0

        for issue in llm_result.get("issues", []):
            # 找到对应的片段
            fragment = self._find_fragment(instructions, issue.get("fragment_id"))
            if not fragment:
                # 如果片段不存在，忽略此问题
                false_positive_count += 1
                continue

            # 检查是否为误报
            if self._is_false_positive(issue, fragment):
                debug(f"检测到误报: {issue.get('description', '')[:50]}...")
                false_positive_count += 1
                continue

            validated_issues.append(issue)

        # 更新结果
        llm_result["issues"] = validated_issues
        llm_result["false_positives_filtered"] = false_positive_count

        return llm_result

    def _find_fragment(self, instructions: AIVideoInstructions,
                       fragment_id: str) -> Optional[AIVideoPrompt]:
        """查找片段"""
        if not fragment_id or fragment_id == "unknown":
            return None

        for frag in instructions.fragments:
            if frag.fragment_id == fragment_id:
                return frag

        return None

    def _is_false_positive(self, issue: Dict, fragment: AIVideoPrompt) -> bool:
        """判断是否为误报"""
        issue_type = issue.get("type", "")
        description = issue.get("description", "").lower()

        # 1. 检查截断误报
        if issue_type == IssueType.TRUNCATION or "截断" in description:
            if not self._is_truly_truncated(fragment.prompt):
                return True

        # 2. 检查场景引用误报
        if issue_type == IssueType.SCENE or "场景" in description:
            if self._has_valid_scene_reference(fragment.prompt):
                return True

        # 3. 检查气象冲突误报
        if issue_type == IssueType.WEATHER or "气象" in description:
            if not self._has_weather_conflict(fragment.prompt):
                return True

        # 4. 检查角色误报
        if issue_type == IssueType.CHARACTER or "角色" in description:
            if self._has_character_consistency(fragment):
                return True

        # 5. 检查动作误报
        if issue_type == IssueType.ACTION or "动作" in description:
            if self._has_action_description(fragment.prompt):
                return True

        # 6. 检查时长误报
        if issue_type == IssueType.DURATION or "时长" in description:
            if self._is_duration_reasonable(fragment.duration):
                return True

        # 7. 检查风格误报
        if issue_type == IssueType.STYLE or "风格" in description:
            if self._has_style_description(fragment):
                return True

        return False

    def _is_truly_truncated(self, prompt: str) -> bool:
        """判断提示词是否真的被截断"""
        # 检查常见的截断标记
        truncation_markers = ['...', '…', 'wea', 'som', 'the ', 'and ']
        end_markers = ['.', '!', '?', ';', ':', '"]', '}', '）', '）']

        last_100_chars = prompt[-100:] if len(prompt) > 100 else prompt

        # 如果有截断标记但没有结束标记，可能是真截断
        has_truncation = any(marker in last_100_chars for marker in truncation_markers)
        has_end = any(marker in last_100_chars[-10:] for marker in end_markers)

        # 返回True表示是真的截断
        return has_truncation and not has_end

    def _has_valid_scene_reference(self, prompt: str) -> bool:
        """检查是否有有效的场景引用"""
        # 提取场景引用
        scene_refs = re.findall(r'scene_\d+', prompt)
        scene_refs.extend(re.findall(r'场景\d+', prompt))

        # 如果有场景引用，认为是有效的（简化处理）
        return len(scene_refs) > 0

    def _has_weather_conflict(self, prompt: str) -> bool:
        """检查是否有气象冲突"""
        prompt_lower = prompt.lower()

        # 检测天气关键词
        has_rain = any(word in prompt_lower for word in ["rain", "rainy", "下雨", "雨", "wet"])
        has_golden_hour = "golden hour" in prompt_lower
        has_sunny = any(word in prompt_lower for word in ["sunny", "sunlight", "晴天", "阳光"])
        has_overcast = any(word in prompt_lower for word in ["overcast", "阴天", "灰蒙蒙", "cloudy"])

        # 检查真正的冲突
        if has_rain and has_golden_hour:
            return True
        if has_rain and has_sunny:
            return True
        if has_overcast and has_golden_hour:
            return True

        return False

    def _has_character_consistency(self, fragment: AIVideoPrompt) -> bool:
        """检查角色一致性"""
        # 检查是否有角色描述
        character_keywords = ['character', '角色', 'person', '人', 'man', 'woman', 'girl', 'boy']
        prompt_lower = fragment.prompt.lower()

        return any(keyword in prompt_lower for keyword in character_keywords)

    def _has_action_description(self, prompt: str) -> bool:
        """检查是否有动作描述"""
        action_keywords = ['action', '动作', 'move', '运动', '动态', 'walk', 'run', 'jump', 'turn']
        prompt_lower = prompt.lower()

        return any(keyword in prompt_lower for keyword in action_keywords)

    def _is_duration_reasonable(self, duration: float) -> bool:
        """检查时长是否合理"""
        # 0.5-5秒是合理范围
        return 0.5 <= duration <= 5.0

    def _has_style_description(self, fragment: AIVideoPrompt) -> bool:
        """检查是否有风格描述"""
        # 检查是否有style字段
        if hasattr(fragment, 'style') and fragment.style:
            return True

        # 检查提示词中是否有风格关键词
        style_keywords = ['cinematic', 'style', 'aesthetic', 'look', 'feel', 'vibe', '风格', '美学']
        prompt_lower = fragment.prompt.lower()

        return any(keyword in prompt_lower for keyword in style_keywords)

    def _merge_llm_result_fixed(self, report: QualityAuditReport,
                                llm_result: Dict[str, Any]) -> None:
        """修复版合并LLM结果"""
        # 添加LLM检查记录
        status = llm_result.get("status", AuditStatus.NEEDS_REVIEW.value)
        summary = llm_result.get("summary", "")

        self._add_check(
            report,
            "LLM连贯性检查",
            status,
            summary
        )

        # 添加LLM发现的问题
        issues = llm_result.get("issues", [])
        for issue in issues:
            severity = issue.get("severity", SeverityLevel.WARNING.value)

            # 构建详细描述
            description = f"[{issue.get('type', '其他')}] {issue.get('description', '')}"

            self._add_violation(
                report=report,
                rule_id="llm_coherence",
                rule_name="LLM连贯性检查",
                description=description,
                severity=severity,
                fragment_id=issue.get("fragment_id"),
                suggestion=issue.get("suggestion")
            )

        # 添加统计信息
        if not hasattr(report, 'stats'):
            report.stats = {}

        report.stats["llm_fragments_checked"] = len(llm_result.get("fragments_checked", []))
        report.stats["false_positives_filtered"] = llm_result.get("false_positives_filtered", 0)
        report.stats["llm_issues_found"] = len(issues)

    def _fix_report_statistics(self, report: QualityAuditReport) -> QualityAuditReport:
        """修复报告中的统计信息"""
        if not hasattr(report, 'stats'):
            report.stats = {}

        # 重新计算各种严重程度的违规数量
        severity_counts = {
            SeverityLevel.INFO.value: 0,
            SeverityLevel.WARNING.value: 0,
            SeverityLevel.MODERATE.value: 0,
            SeverityLevel.MAJOR.value: 0,
            SeverityLevel.CRITICAL.value: 0,
            SeverityLevel.ERROR.value: 0
        }

        # 更新统计信息
        report.stats.update({
            SeverityLevel.INFO.value: severity_counts[SeverityLevel.INFO.value],
            SeverityLevel.WARNING.value: severity_counts[SeverityLevel.WARNING.value],
            SeverityLevel.MODERATE.value: severity_counts[SeverityLevel.MODERATE.value],
            SeverityLevel.MAJOR.value: severity_counts[SeverityLevel.MAJOR.value],
            SeverityLevel.CRITICAL.value: severity_counts[SeverityLevel.CRITICAL.value],
            SeverityLevel.ERROR.value: severity_counts[SeverityLevel.ERROR.value],
            "total_violations": len(report.violations),
            "fragments_checked": report.project_info.get("fragment_count", 0)
        })

        # 计算检查通过率
        total_checks = len(report.checks)
        passed_checks = sum(1 for check in report.checks if check.get("status") == AuditStatus.PASSED.value)

        if total_checks > 0:
            report.stats["passed_checks"] = passed_checks
            report.stats["total_checks"] = total_checks
            report.stats["pass_rate"] = round(passed_checks / total_checks, 2)
            report.stats["failed_checks"] = total_checks - passed_checks

        # 确定最终状态
        if severity_counts[SeverityLevel.ERROR.value] > 0:
            report.status = AuditStatus.FAILED
        elif severity_counts[SeverityLevel.CRITICAL.value] > 0:
            report.status = AuditStatus.CRITICAL_ISSUES
        elif severity_counts[SeverityLevel.MAJOR.value] > 0:
            report.status = AuditStatus.MAJOR_ISSUES
        elif severity_counts[SeverityLevel.MODERATE.value] > 0:
            report.status = AuditStatus.MODERATE_ISSUES
        elif severity_counts[SeverityLevel.WARNING.value] > 0:
            report.status = AuditStatus.MINOR_ISSUES
        else:
            report.status = AuditStatus.PASSED

        # 生成修复后的结论
        report.conclusion = self._generate_fixed_conclusion(report)

        return report

    def _generate_fixed_conclusion(self, report: QualityAuditReport) -> str:
        """生成修复后的结论"""
        if report.status == AuditStatus.PASSED:
            return "审查通过，可以开始视频生成"

        issues_summary = []
        if report.stats.get(SeverityLevel.ERROR.value, 0) > 0:
            issues_summary.append(f"{report.stats[SeverityLevel.ERROR.value]}个错误")
        if report.stats.get(SeverityLevel.CRITICAL.value, 0) > 0:
            issues_summary.append(f"{report.stats[SeverityLevel.CRITICAL.value]}个严重问题")
        if report.stats.get(SeverityLevel.MAJOR.value, 0) > 0:
            issues_summary.append(f"{report.stats[SeverityLevel.MAJOR.value]}个主要问题")
        if report.stats.get(SeverityLevel.MODERATE.value, 0) > 0:
            issues_summary.append(f"{report.stats[SeverityLevel.MODERATE.value]}个中度问题")
        if report.stats.get(SeverityLevel.WARNING.value, 0) > 0:
            issues_summary.append(f"{report.stats[SeverityLevel.WARNING.value]}个警告")

        if issues_summary:
            return f"发现{', '.join(issues_summary)}，请根据建议修复"

        return "审查完成"
