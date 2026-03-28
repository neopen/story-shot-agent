"""
@FileName: base_llm_agent.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/9 21:23
"""
import time
from typing import Any, Dict, Optional

from penshot.neopen.agent.base_agent import BaseAgent
from penshot.neopen.agent.script_parser.script_parser_models import GlobalMetadata, ParsedScript
from penshot.neopen.client.client_factory import llm_chat_complete
from penshot.neopen.prompts.prompts_manager import prompt_manager
from penshot.neopen.tools.json_parser_tool import parse_json_response


class BaseLLMAgent(BaseAgent):

    def _get_prompt_template(self, key_name) -> str:
        """创建LLM提示词模板"""
        return prompt_manager.get_name_prompt(key_name)

    def _parse_llm_response(self, ai_response: str) -> Dict[str, Any]:
        """ 转换LLM响应，必要时需要重写该方法 """
        return parse_json_response(ai_response)

    def _call_llm_parse_with_retry(self, llm, system_prompt: str, user_prompt, max_retries: int = 2) -> Optional[Dict[str, Any]]:
        """
            调用LLM，返回转换后的对象（支持重试）
            返回 dict
        """
        return self._parse_llm_response(self._call_llm_chat_with_retry(llm, system_prompt, user_prompt, max_retries))

    def _call_llm_chat_with_retry(self, llm, system_prompt: str, user_prompt, max_retries: int = 2) -> Optional[str]:
        """
            调用LLM，直接返回json字符串（支持重试）
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        for attempt in range(max_retries):
            try:
                return llm_chat_complete(llm, messages)

            except Exception as e:
                if attempt == max_retries - 1:
                    raise Exception(f"LLM调用失败: {e}")
                time.sleep(1)

    def _call_llm_with_retry(self, llm, prompt: str, max_retries: int = 2) -> Optional[Any]:
        """调用LLM，支持重试"""
        for attempt in range(max_retries):
            try:
                return llm.invoke(prompt)

            except Exception as e:
                if attempt == max_retries - 1:
                    raise Exception(f"LLM调用失败: {e}")
                time.sleep(1)

    def _get_scene_info(self, scene_id: str, parsed_script: ParsedScript) -> str:
        """从ParsedScript获取场景信息"""
        if not parsed_script:
            return ""

        for scene in parsed_script.scenes:
            if scene.id == scene_id:
                characters = []
                for elem in scene.elements:
                    if elem.character and elem.character not in characters:
                        characters.append(elem.character)

                weather = scene.weather or "未知"
                time_of_day = scene.time_of_day or "未知"

                return f"场景{scene_id}: {scene.location}, 角色[{', '.join(characters)}], 天气{weather}, 时间{time_of_day}"
        return ""

    def _format_global_context(self, global_metadata: GlobalMetadata, scene_id: Optional[str] = None) -> str:
        """格式化全局上下文 - 从global_metadata获取"""
        if not global_metadata:
            return ""

        sections = []

        # 1. 关键道具
        if global_metadata.key_props:
            relevant_props = global_metadata.key_props
            if scene_id:
                relevant_props = [p for p in global_metadata.key_props if scene_id in p.appears_in]

            if relevant_props:
                props = []
                for prop in relevant_props:
                    color_info = f"（{prop.color}）" if prop.color else ""
                    props.append(f"  - {prop.name}{color_info}：{prop.description}")
                sections.append("【本场景关键道具】\n" + "\n".join(props))
            else:
                props = []
                for prop in global_metadata.key_props:
                    if prop.importance == "high":
                        props.append(f"⭐ {prop.name}：{prop.description}")
                    else:
                        props.append(f"📌 {prop.name}：{prop.description}")
                sections.append("【关键道具】\n" + "\n".join(props))

        # 2. 角色服装
        if global_metadata.character_outfits:
            outfits = []
            for outfit in global_metadata.character_outfits:
                color_info = f"{outfit.color}色" if outfit.color else ""
                style_info = f"、{outfit.style}" if outfit.style else ""
                material_info = f"、{outfit.material}" if outfit.material else ""
                outfits.append(f"  - {outfit.character}：{color_info}{outfit.description}{style_info}{material_info}")
            sections.append("【角色服装要求】\n" + "\n".join(outfits))

        # 3. 关键地点
        if global_metadata.key_locations:
            relevant_locs = global_metadata.key_locations
            if scene_id:
                relevant_locs = [loc for loc in global_metadata.key_locations if scene_id in loc.appears_in]

            if relevant_locs:
                locs = []
                for loc in relevant_locs:
                    cues = "，" + "、".join(loc.visual_cues) if loc.visual_cues else ""
                    locs.append(f"  - {loc.name}：{loc.description}{cues}")
                sections.append("【本场景地点】\n" + "\n".join(locs))
            else:
                locs = []
                for loc in global_metadata.key_locations:
                    cues = "，" + "、".join(loc.visual_cues) if loc.visual_cues else ""
                    locs.append(f"  - {loc.name}：{loc.description}{cues}")
                sections.append("【主要场景】\n" + "\n".join(locs))

        # 4. 连续性要点
        if global_metadata.continuity_notes:
            sections.append(f"【特别注意，连续性要求】\n{global_metadata.continuity_notes}")

        return "\n\n".join(sections)

    def _format_global_metadata(self, global_metadata: GlobalMetadata,
                                scene_id: Optional[str] = None,
                                format_type: str = "prompt") -> str:
        """
        统一的全局元数据格式化函数

        Args:
            global_metadata: GlobalMetadata对象
            scene_id: 当前场景ID，用于过滤相关道具
            format_type: 输出格式类型
                - "prompt": 提示词转换器使用（简洁单行）
                - "split": 视频分割器使用（中等详细）
                - "shot": 镜头分割器使用（最详细）

        Returns:
            格式化的字符串
        """
        if not global_metadata:
            return ""

        sections = []

        # === 1. 角色服装（所有格式都需要） ===
        if global_metadata.character_outfits:
            if format_type == "prompt":
                # 简洁格式：陈阳(黄色), 林小雨(浅灰)
                outfits = []
                for outfit in global_metadata.character_outfits:
                    color_info = f"({outfit.color})" if outfit.color else ""
                    outfits.append(f"{outfit.character}{color_info}")
                sections.append(f"角色服装：{', '.join(outfits)}")

            elif format_type == "split":
                # 中等格式：陈阳：黄色雨衣，林小雨：浅灰风衣
                outfits = []
                for outfit in global_metadata.character_outfits:
                    color_info = f"{outfit.color}色" if outfit.color else ""
                    outfits.append(f"{outfit.character}：{color_info}{outfit.description}")
                sections.append("【角色服装要求】\n" + "\n".join(f"  - {o}" for o in outfits))

            else:  # shot
                # 详细格式：包含材质、款式
                outfits = []
                for outfit in global_metadata.character_outfits:
                    details = []
                    if outfit.color:
                        details.append(f"{outfit.color}色")
                    if outfit.style:
                        details.append(outfit.style)
                    if outfit.material:
                        details.append(outfit.material)
                    detail_str = "、".join(details)
                    outfits.append(f"  - {outfit.character}：{outfit.description}（{detail_str}）")
                sections.append("【角色服装统一要求】\n" + "\n".join(outfits))

        # === 2. 关键道具（根据场景过滤） ===
        if global_metadata.key_props:
            # 根据scene_id过滤相关道具
            relevant_props = global_metadata.key_props
            if scene_id:
                relevant_props = [p for p in global_metadata.key_props if scene_id in p.appears_in]

            if relevant_props:
                if format_type == "prompt":
                    # 简洁格式：只列名称
                    props = [p.name for p in relevant_props[:10]]
                    sections.append(f"关键道具：{', '.join(props)}")

                elif format_type == "split":
                    # 中等格式：带颜色和描述
                    props = []
                    for prop in relevant_props:
                        color_info = f"（{prop.color}）" if prop.color else ""
                        props.append(f"  - {prop.name}{color_info}：{prop.description}")
                    section_title = "【本场景相关道具】" if scene_id else "【关键道具】"
                    sections.append(f"{section_title}\n" + "\n".join(props))

                else:  # shot
                    # 详细格式：包含重要性
                    props = []
                    for prop in relevant_props:
                        color_info = f"（{prop.color}）" if prop.color else ""
                        importance = "⭐" if prop.importance == "high" else "📌"
                        props.append(f"  {importance} {prop.name}{color_info}：{prop.description}")
                    sections.append("【关键道具一致性】\n" + "\n".join(props))

        # === 3. 关键地点 ===
        if global_metadata.key_locations:
            if format_type == "prompt":
                # 简洁格式：只列名称
                locs = [loc.name for loc in global_metadata.key_locations[:10]]
                sections.append(f"主要场景：{', '.join(locs)}")

            elif format_type == "split":
                # 中等格式
                locs = []
                for loc in global_metadata.key_locations:
                    cues = "，" + "、".join(loc.visual_cues) if loc.visual_cues else ""
                    locs.append(f"  - {loc.name}：{loc.description}{cues}")
                sections.append("【主要场景】\n" + "\n".join(locs))

            else:  # shot
                # 详细格式
                locs = []
                for loc in global_metadata.key_locations:
                    appears = f"[出现在: {', '.join(loc.appears_in)}]" if loc.appears_in else ""
                    cues = "，视觉特征：" + "、".join(loc.visual_cues) if loc.visual_cues else ""
                    locs.append(f"  - {loc.name}{appears}：{loc.description}{cues}")
                sections.append("【主要场景】\n" + "\n".join(locs))

        # === 4. 连续性要点 ===
        if global_metadata.continuity_notes:
            if format_type == "prompt":
                # 简洁格式：只取前50字
                notes = global_metadata.continuity_notes[:100] + "..." if len(global_metadata.continuity_notes) > 50 else global_metadata.continuity_notes
                sections.append(f"注意：{notes}")

            elif format_type == "split":
                sections.append(f"【特别注意】\n{global_metadata.continuity_notes}")

            else:  # shot
                sections.append(f"【连续性要点】\n{global_metadata.continuity_notes}")

        # 根据format_type返回不同分隔符
        if format_type == "prompt":
            return " | ".join(sections)  # 单行，用分隔符
        else:
            return "\n\n".join(sections)  # 多行，用空行分隔
