"""
@FileName: test_parse_dict.py
@Description: 
@Author: HiPeng
@Time: 2026/3/29 16:16
"""
import json
from enum import Enum

from penshot.utils.obj_utils import convert_data_dict_safe, _is_enum_subclass

# 你的数据
data = {
    "instructions": {
      "metadata": {
        "generated_at": "2026-03-28T21:54:10.815164",
        "version": "mvp_1.0",
        "video_model": "runway_gen2",
        "audio_model": "XTTSv2",
        "total_prompts": 2,
        "converter_type": "LLMPromptConverter",
        "repair_history": [
          {
            "timestamp": 1774706072.1196313,
            "actions": [
              "截断过长提示词: frag_001 989 -> 200",
              "截断过长提示词: frag_002 881 -> 200"
            ],
            "issue_count": 4,
            "original_stats": {
              "prompt_count": 2,
              "avg_prompt_length": 935,
              "audio_count": 2
            },
            "new_stats": {
              "prompt_count": 2,
              "avg_prompt_length": 183,
              "audio_count": 2
            },
            "fixed_issues": 2
          }
        ]
      },
      "project_info": {
        "title": "AI视频项目",
        "total_fragments": 2,
        "total_duration": 7.27,
        "source_fragments": [
          "frag_001",
          "frag_002"
        ]
      },
      "fragments": [
        {
          "fragment_id": "frag_001",
          "prompt": "medium shot, modern open-plan office, light-gray walls and transparent glass partitions extending to frame edges, evenly distributed 5000K cool-white LED ceiling lighting, Li Xiao ...",
          "negative_prompt": "blurry face, distorted keyboard, incorrect hoodie color (e.g., black or gray instead of deep blue), hood up, smiling or distracted expression, visible text errors on screen, warm lighting, film grain, cartoon style, no code on screens, empty monitors, unrealistic shadows",
          "duration": 2.77,
          "model": "runway_gen2",
          "style": "cinematic realism, Fujifilm ETERNA grading, natural overcast lighting, 35mm lens",
          "requires_special_attention": 0,
          "audio_prompt": {
            "audio_id": "audio_001",
            "prompt": "low-frequency office ambient noise (HVAC hum + tactile mechanical keyboard clatter), subtle rhythmic keystrokes, faint intermittent terminal beep alerts, quiet air movement through blinds, no speech or music\n\n低频办公环境底噪（空调持续嗡鸣+机械键盘敲击声），细微有节奏的按键声，终端偶尔发出的短促‘滴’提示音，百叶窗缝隙间轻微气流声，无语音、无音乐",
            "negative_prompt": "human voice, phone ringtone, footsteps, laughter, sudden loud sounds, music, distortion, silence-only",
            "model_type": "AudioLDM_3",
            "voice_type": "narration",
            "audio_style": "realistic",
            "voice_character": "",
            "voice_description": "neutral ambient texture with precise transient detail for keyboard and HVAC",
            "speed": 1,
            "pitch_shift": 0,
            "emotion": "neutral",
            "stability": 0.7,
            "duration_seconds": 2.77,
            "sound_attributes": {
              "intensity": 0.8,
              "reverb": 0.3
            },
            "format": "wav",
            "sample_rate": 24000,
            "seed": 42719,
            "scene_context": "modern open-plan office during afternoon, quiet but dynamically textured ambient environment with focused work activity",
            "previous_audio_id": ""
          }
        },
        {
          "fragment_id": "frag_002",
          "prompt": "extreme close-up, cinematic realism, Xiao Li's left-profile face turning slightly, pupils sharply constricting, eyebrows lifting subtly, lips parting faintly; crisp short electroni...",
          "negative_prompt": "smiling, closed eyes, wrong sweatshirt color (e.g. red/green), missing glasses, visible phone device, text overlay, cartoon style, motion blur on face, distorted anatomy, extra limbs, unrealistic skin texture",
          "duration": 4.5,
          "model": "runway_gen2",
          "style": "cinematic realism, Fujifilm ETERNA, natural overcast, 35mm",
          "requires_special_attention": 0,
          "audio_prompt": {
            "audio_id": "audio_002",
            "prompt": "low-frequency office ambient noise (HVAC hum + light keyboard clatter), sudden crisp short electronic ringtone (high-pitched, 120ms duration, clean decay), subtle fabric rustle from sleeve movement, faint finger hover micro-sound above mechanical switches\n\n低频办公环境底噪（空调持续嗡鸣+轻微键盘敲击余响），突发清脆短促电子铃声（高音调、120毫秒、干净衰减），卫衣袖口滑动产生的细微布料摩擦声，手指悬停于机械键盘上方的极轻微气流声",
            "negative_prompt": "voice dialogue, footsteps, music, reverb-heavy ringtone, distorted audio, overlapping sounds, silence longer than 0.3s",
            "model_type": "AudioLDM_3",
            "voice_type": "narration",
            "audio_style": "realistic",
            "voice_character": "",
            "voice_description": "neutral male ambient sound design, high-fidelity spatial recording, balanced frequency response, studio-grade clarity",
            "speed": 1,
            "pitch_shift": 0,
            "emotion": "neutral",
            "stability": 0.7,
            "duration_seconds": 4.5,
            "sound_attributes": {
              "intensity": 0.8,
              "reverb": 0.3
            },
            "format": "wav",
            "sample_rate": 24000,
            "seed": 42719,
            "scene_context": "modern open-plan office, afternoon, cool white LED lighting (5000K), glass partitions, dual monitors, ergonomic chair, quiet but dynamically punctuated by digital alerts",
            "previous_audio_id": "audio_001"
          }
        }
      ],
      "global_settings": {
        "style_consistency": 1,
        "use_common_negative_prompt": 1
      },
      "execution_suggestions": [
        "按顺序生成片段",
        "保持相同种子值以获得一致性",
        "生成后检查片段衔接"
      ]
    }
  }

# 使用调试版本找出问题
# 或使用正式版本
converted = convert_data_dict_safe(data, enum_mode='value')


# 验证枚举是否全部转换
def check_for_enums(obj, path="root"):
    """递归检查是否还有 Enum 对象"""
    if isinstance(obj, Enum) or _is_enum_subclass(obj):
        print(f"❌ 发现未转换的 Enum: {path} = {obj}")
        return False

    if isinstance(obj, dict):
        for k, v in obj.items():
            if not check_for_enums(v, f"{path}.{k}"):
                return False
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            if not check_for_enums(item, f"{path}[{i}]"):
                return False

    return True


print("\n=== 检查是否还有 Enum ===")
if check_for_enums(converted):
    print("✅ 所有 Enum 已转换！")
else:
    print("❌ 仍有 Enum 未转换")

# JSON 序列化测试
print("\n=== JSON 序列化测试 ===")
try:
    json_str = json.dumps(converted, ensure_ascii=False, indent=2)
    print("✅ JSON 序列化成功！")
    print(f"JSON 长度：{len(json_str)} 字符")
except Exception as e:
    print(f"❌ JSON 序列化失败：{e}")