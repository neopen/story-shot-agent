# 剧本分镜智能体

中文 | [English](docu/README-en.md)

一个基于多智能体协作的剧本分镜系统，能够将多种格式的剧本拆分为AI可生成的短视频脚本单元，输出高质量分镜片段描述，并保证叙事连续性。支持多种AI提供商，具有强大的可扩展性和易用性。可以通过Python库、Web API、LangGraph节点或A2A系统集成使用。

> - **需求描述**：假如我有一段预估两分钟左右的剧本，想通过AI模型生成对应的短视频。
>
> - **技术受限**：目前的各种模型仅支持一次生成5-10秒长度的视频，想要生成两分钟长度的视频，只能通过“拼接”的方式，将多个5秒的片段合成为一个视频。
>
> - **任务&挑战点**：要实现视频拼接，第一步就需要拆分原剧本，拆分后的剧本尽量接近5-10秒时长（取决于模型），且每个视频片段还必须要保持连贯性，不然生成的视频片段合成后会导致场景、动作、人物等衔接不上。
>
>   且剧情中的动作、语速等会影响时长，所以需要考虑多种情景，比如：老人动作慢、生气怒吼时语速会较快、跑比走要快等等。
>
>   这便是本智能体需要完成的任务，用户只需要给出剧本，而后根据各种技术拆解，最后将拆解完成的剧本片段返回，用户只需要将其交给模型（Runway、Pika、Sora、Wan、Stable Video等）生成即可，最后再利用相关技术将片段合成为完整视频。

**视频创作流程**：客户端  → LLM 剧本创作  →  <u>***剧本解析（拆分）***</u> → DM 视频生成（文生视频） →  视频合成渲染（FFmpeg）

**注意**：本智能体不会参与剧本创作，目前版本不会调用模型生成视频，亦不会合成视频（未来版本会支持），以上流程中标注处就是本智能体的任务。

详细设计参照文档：[**剧本分镜智能体的架构设计与实现细节**](https://pengline.github.io/2025/10/0194020a663c408fb500dd7532349519/)




## 核心功能

- **智能剧本解析**：自动识别场景、对话和动作指令，理解故事结构
- **精准时序规划**：按镜头粒度智能切分内容，分配合理时长
- **连续性守护**：确保相邻分镜间角色状态、场景和情节的一致性
- **高质量分镜生成**：生成详细的中文画面描述和英文AI视频提示词
- **多模型支持**：兼容OpenAI、Qwen、DeepSeek、Ollama等多种AI提供商



## 快速上手

### 1. 环境准备

**前置条件**：Python 3.10 或更高版本

```bash
# 克隆项目
git clone https://github.com/HengLine/video-shot-agent.git
cd video-shot-agent

# 安装为可编辑包
pip install -e .

######### 方式1：自动安装
# 脚本会自动创建虚拟环境、安装依赖并启动服务，若失败，可手动安装
python main.py


######### 方式2：手动安装
python -m venv .venv
# 激活虚拟环境 (Windows)
.venv\Scripts\activate
# 或者 (Linux/Mac)
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置设置

复制配置文件并设置环境变量：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必要的参数：

```properties
# 部署环境（development, production）
APP__ENVIRONMENT=development
# 剧本的语言设置，目前支持：zh（中文）或en（英文）
APP__LANGUAGE=zh
# ================= API配置 =================
#  服务器主机，支持HOST环境变量
API__HOST=localhost
#  服务器端口，支持PORT环境变量
API__PORT=8000

########################## LLM 模型配置 #########################
# 系统支持的厂商（openai, qwen, deepseek, ollama），当默认模型不可用时使用备用厂商

# ================= LLM默认配置 =================
# LLM 厂商 API
LLM__DEFAULT__BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1
# LLM 厂商 KAY
LLM__DEFAULT__API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# LLM 厂商 模型
LLM__DEFAULT__MODEL_NAME=qwen-plus
# 生成温度参数，控制输出的随机性： 0.0 = 确定性输出，1.0 = 最大随机性
LLM__DEFAULT__TEMPERATURE=0.1
# 默认API超时时间（秒）
LLM__DEFAULT__TIMEOUT=60
# 最大重试次数
LLM__DEFAULT__MAX_RETRIES=2
# 最大生成令牌数
LLM__DEFAULT__MAX_TOKENS=3000
LLM__DEFAULT__RETRY_DELAY=1

# ================= LLM备用配置 =================
LLM__FALLBACK__BASE_URL=http://localhost:11434
LLM__FALLBACK__MODEL_NAME=qwen3:4b
LLM__FALLBACK__TEMPERATURE=0.1
LLM__FALLBACK__TIMEOUT=300
LLM__FALLBACK__MAX_TOKENS=5000
```

### 3. 启动应用

```bash
python main.py
```

应用将在 `http://0.0.0.0:8000` 启动，提供API接口服务。

### 4. 提交任务

提交任务：

```sh
curl --location --request POST 'http://localhost:8000/api/v1/storyboard' \
--header 'Content-Type: application/json' \
--data-raw '{
    "script": "深夜11点，城市公寓客厅，窗外大雨滂沱。林然裹着旧羊毛毯蜷在沙发里，电视静音播放着黑白老电影。茶几上半杯凉茶已凝出水雾，旁边摊开一本旧相册。手机突然震动，屏幕亮起“未知号码”。她盯着看了三秒，指尖悬停在接听键上方，喉头轻轻滚动。终于，她按下接听，将手机贴到耳边。电话那头沉默两秒，传来一个沙哑的男声：“是我。”  林然的手指瞬间收紧，指节泛白，呼吸停滞了一瞬。  她声音微颤：“……陈默？你还好吗？”  对方停顿片刻，低声说：“我回来了。” 林然猛地坐直，瞳孔收缩，泪水在眼眶中打转。她张了张嘴，却发不出声音，只有毛毯从肩头滑落。”"
}'
```



### 5. 获取结果

查看任务状态：

```sh
# HL202603061937129004 为任务提交成功后返回的 task_id
curl --location --request GET 'http://localhost:8000/api/v1/status/HL202603061937129004'
```

获取任务结果：

```sh
# HL202603061937129004 为任务提交成功后返回的 task_id
curl --location --request GET 'http://localhost:8000/api/v1/result/HL202603061937129004'
```

输出：结构化分镜结果（`audio_prompt` 为音频提示词信息）

```json
{
  "fragments": [
    {
      "fragment_id": "frag_001",
      "prompt": "Cinematic wide shot: midnight 11 PM in a compact urban apartment living room — rain lashes violently against the window, blurring distant neon signs (pink, cyan, magenta) into soft streaks; dim ambient light from a silent black-and-white vintage film playing on an old CRT TV casts faint flickering glow; medium-gray fabric sofa, weathered oak coffee table, analog wall clock frozen at 11:00, half-drawn beige curtains; woman (Lin Ran) curled on sofa under a thick, off-white hand-knitted wool blanket — coarse texture, yellowed edges, visible pilling and wear; she wears a loose, muted gray cotton long-sleeve top with subtle collar folds; her face is tired but alert, eyes slightly red, jaw gently tensed; shallow depth of field, film grain, naturalistic color grading, moody chiaroscuro lighting, 35mm cinematic realism\n\n全景镜头：深夜11点的城市公寓客厅，窗外大雨滂沱，雨幕模糊映出远处霓虹灯（粉、青、洋红）的光斑；室内微光来自静音播放的黑白老电影CRT电视，泛出轻微闪烁荧光；米灰布艺沙发、原木茶几、指针停在11点的老式挂钟、半掩的米色窗帘；林然蜷坐于沙发，裹着厚实米白旧羊毛毯——粗纺质感、边缘泛黄起球、生活磨损明显；身穿中性灰素色棉质长袖上衣，宽松剪裁、领口微褶；神情疲惫而警觉，眼眶微红，下颌线轻绷；浅景深，胶片颗粒感，自然影调，明暗对比克制的电影级写实风格",
      "negative_prompt": "cartoon, anime, 3D render, photorealistic stock photo, bright lighting, smiling face, modern fashion, high saturation, text, logo, watermark, sharp focus everywhere, clean unused objects, glossy surfaces, daylight, people walking, dialogue subtitles",
      "duration": 4.2,
      "model": "runway_gen2",
      "style": "cinematic 35mm film, moody realism, shallow depth of field, natural lighting, muted palette, subtle motion blur on rain streaks",
      "requires_special_attention": false,
      "audio_prompt": {
        "audio_id": "audio_001",
        "prompt": "Low-frequency rain ambience (intensity 0.95), distant muffled TV static hiss (black-and-white film tone), near-silence punctuated by faint breath and fabric rustle — no speech, no music, no sudden transients; highly restrained dynamic range, immersive spatial audio, slight reverb suggesting small enclosed apartment space\n\n低频雨声基底（强度0.95），远处模糊的老式黑白电视底噪（嘶嘶白噪音），近乎寂静中夹杂极轻微呼吸声与羊毛毯摩擦声——无人声台词、无音乐、无突兀瞬态；高度克制的动态范围，沉浸式空间音频，轻微混响体现小户型密闭空间感",
        "negative_prompt": "speech, dialogue, footsteps, door creak, music, birdsong, wind howl, thunderclap, laughter, applause, narration",
        "model_type": "AudioLDM_3",
        "voice_type": "narration",
        "audio_style": "cinematic",
        "voice_character": null,
        "voice_description": "ambient sound design only, no voice, pure atmospheric field recording style",
        "pitch_shift": 0.0,
        "emotion": "neutral",
        "previous_audio_id": "audio_014"
      }
    },
    {
      "fragment_id": "frag_002",
      "prompt": "medium shot, cinematic lighting, Lin Ran curled up on a light gray fabric sofa, wrapped in a creamy off-white vintage wool blanket — thick, coarse-knit, slightly yellowed and pilled at edges, showing visible wear; she wears a neutral-toned (light gray/mushroom beige) soft cotton long-sleeve top, loose fit, subtle collar pleats, no jewelry or decoration; her expression is exhausted yet alert, eyes slightly red-rimmed, quiet emotional tension; background: modern small-city apartment living room — light gray fabric sofa, warm-toned wooden coffee table, vintage wall clock frozen at 11:00, half-drawn curtains revealing blurred neon lights and rain-streaked window; muted black-and-white old film playing silently on TV screen; ambient low-frequency rain, faint TV static hum, restrained vocal dynamic range\n\n中景，电影感布光：林然蜷坐于米灰布艺沙发中，裹着米白色旧羊毛毯——厚实粗纺、局部泛黄起球、边缘磨损，具明显生活使用痕迹；身穿中性灰/米白色素色棉质长袖上衣，宽松剪裁，领口微褶，无装饰；神情疲惫而警觉，眼眶微红，情绪张力内敛；背景为现代都市小户型客厅：米灰布艺沙发、暖调原木茶几、静止于11点的老式挂钟、半掩窗帘映出窗外模糊霓虹与雨痕；电视静音播放黑白老电影；环境音为低频雨声基底 + 微弱电视底噪 + 高度克制的人声动态范围",
      "negative_prompt": "modern fashion clothing, bright colors, glossy textures, sharp focus on face only, text overlays, logos, cartoon style, anime, photorealistic skin imperfections, motion blur, shaky cam, high saturation, studio lighting, smiling, energetic pose, multiple people, clean unused objects",
      "duration": 3.0,
      "model": "runway_gen2",
      "style": "cinematic, realistic, muted color palette, shallow depth of field, Kodak Portra 400 film grain, emotionally restrained tone",
      "requires_special_attention": false,
      "audio_prompt": {
        "audio_id": "audio_002",
        "prompt": "ambient low-frequency rainfall (intensity 0.9), distant faint television white noise (black-and-white film static), near-silence with subtle breath and micro-movement cues, highly compressed vocal dynamic range, no dialogue, immersive domestic stillness\n\n低频雨声（强度0.9）、远处微弱电视底噪（黑白电影静电声）、近乎寂静中夹杂细微呼吸与身体微动声、人声动态范围高度压缩、无台词、沉浸式居家静默氛围",
        "negative_prompt": "dialogue, music, footsteps, door sounds, phone ring, laughter, wind, thunder, abrupt transients, high-frequency hiss, stereo panning effects",
        "model_type": "AudioLDM_3",
        "voice_type": "narration",
        "audio_style": "cinematic",
        "voice_character": null,
        "voice_description": "no voice, pure environmental atmosphere with ultra-low dynamic range and tactile silence",
        "pitch_shift": 0.0,
        "emotion": "neutral",
        "previous_audio_id": "audio_001"
      }
    },
    ......
  ]
}
```



## 智能体集成示例

**安装依赖**：

```sh
# 选择最新版本，下载 whl 包（https://github.com/HengLine/video-shot-agent/releases）
# https://github.com/HengLine/video-shot-agent/releases/download/v0.1.3-beta/hengshot-0.1.3-py3-none-any.whl
# 内部默认安装使用 ollama，如果要使用其他平台，需要安装对应的包
pip install hengshot-0.1.1-py3-none-any.whl
# 安装指定LLM 包
# pip install langchain-openai	使用 openai 或 deepseek
# pip install dashscope			使用千问
```

**环境配置**：

> 1. 复制示例文件：cp .env.example .env
>
> 2. 编辑 .env 文件，填入真实配置
>
> ```properties
> # .env - 实际配置文件
> # ================= 应用配置 =================
> APP__LANGUAGE=zh
> 
> # ================= LLM默认配置 =================
> LLM__DEFAULT__BASE_URL=https://api.openai.com/v1
> LLM__DEFAULT__API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
> LLM__DEFAULT__MODEL_NAME=gpt-4-turbo-preview
> LLM__DEFAULT__TEMPERATURE=0.7
> LLM__DEFAULT__TIMEOUT=30
> LLM__DEFAULT__MAX_RETRIES=3
> LLM__DEFAULT__MAX_TOKENS=4000
> ```



### 1. 作为Python库使用

```python
from hengshot.hengline import generate_storyboard
from hengshot.hengline.hengline_config import HengLineConfig

async def basic_usage():
    """基础用法示例"""
    script = """
    场景：现代办公室
    时间：下午3点
    人物：小李（程序员）
    动作：小李正在写代码，突然接到电话，表情惊讶
    """
    
    # 创建自定义配置 LLM
    custom_config = HengLineConfig(
        model_name="gpt-4",
        base_url="http://localhost:11434",  # 假设本地部署了 Ollama
        temperature=0.2
    )

    # 简单调用
    result = await generate_storyboard(
        script_text=script,
        config=custom_config
    )
    print(f"生成完成，任务ID: {result.get('task_id')}")
    print(f"生成结果: {result.get('success', False)}")
    print(f"分镜片段: {result.get('data', {})}")

    return result
```

### 2. 集成到Web应用（API）

可以通过 HTTP API 将剧本分镜智能体集成到各种 Web 应用中：

```python
from hengshot.hengline import generate_storyboard
from hengshot.hengline.hengline_config import HengLineConfig

@app.post("/api/generate-storyboard")
async def generate_storyboard_endpoint(script_text: str):
    """
    生成视频分镜的Web API端点
    """
    
    # 创建自定义配置 LLM
    custom_config = HengLineConfig(
        model_name="gpt-4",
        base_url="http://localhost:11434",  # 假设本地部署了 Ollama
        temperature=0.2
    )
    
    try:
        return await generate_storyboard(
            script_text=script_text,
            config=custom_config
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")
```



### 3. 集成到LangGraph节点

可以将剧本分镜智能体作为 LangGraph 工作流中的一个节点。

使用方式：[剧本分镜智能体架构设计与实现 | 集成到 LangGraph 节点](https://pengline.github.io/2025/10/0194020a663c408fb500dd7532349519/)



### 4. 集成到A2A系统

将剧本分镜智能体集成到Agent-to-Agent协作系统中。

如：上游是剧本创作智能体，下游是 文生视频+剪辑 智能。

使用方式：[剧本分镜智能体架构设计与实现 | 集成到 A2A 系统](https://pengline.github.io/2025/10/0194020a663c408fb500dd7532349519/)



## 版本与展望

> 1. **依赖外部API**：LLM版本需要稳定的网络连接
> 2. **AI模型限制**：生成的视频质量受限于AI视频模型能力
> 3. **处理长剧本**：长剧本可能需要分段处理
> 4. **多语言支持**：主要针对中文优化，其他语言效果待测试

### MVP版本限制

1. **简单规则**：使用固定规则，无法处理复杂剧本结构
2. **无状态记忆能力**：只支持一次拆解，不支持超长文本的多次拆分
3. **无学习能力**：不会从用户反馈中学习优化
4. **简单切割**：视频分割简单，会有一致性、连续性、时长压缩等问题
5. **有限的自定义**：配置选项较少
6. **错误处理简单**：遇到异常可能直接失败

### 短期计划

1. **智能分割**：优化长镜头分割逻辑，保持动作连贯性
2. **连续性检查**：角色服装、位置、道具的一致性验证
3. **多模型适配**：针对Sora、Pika等模型的提示词优化
4. **规则+LLM混合**：支持本地规则处理，两种方式结合
5. **英文剧本**：完整支持英文剧本输入
6. **错误恢复**：节点失败时智能降级
7. **配置扩展**：更细粒度的参数控制
8. **质量评分**：为每个片段输出置信度评分
9. **调试模式**：保存中间结果，便于问题定位
10. **声音支持**：支持声音提示词生成，配合文生音频智能体使用，实现声音与画面的一致性


### 中期计划

1. **高级镜头语言**：支持复杂镜头运动（推拉摇移跟）
2. **情感分析**：根据剧本情感自动调整视觉风格
3. **超长剧本**：分块处理+上下文记忆
4. **自动优化**：从历史结果学习成功模式
5. **批量处理**：多剧本队列处理
6. **Web界面**：可视化操作
7. **素材库集成**：支持角色/场景参考图
8. **多格式导出**：故事板、时间线XML、数据集格式
9. **状态记忆系统**：基于ID的Embedding+状态追踪，支持超长剧本分段处理
10. **结果下载**：支持导出完整分镜结果文件

### 长期计划

1. **多模态输入**：支持图片+音频+文本混合输入
2. **实时预览**：低分辨率快速预览
3. **智能修复**：自动检测并修复连续性问题
4. **生态集成**：Premiere/FCP/DaVinci插件
5. **协作功能**：多人协同+版本控制
6. **学习进化**：从用户反馈中自动改进
7. **商业化**：用量统计、团队管理、企业SLA
8. **剧本仓库**：历史剧本管理+版本追溯
9. **增量处理**：仅处理修改部分，复用已有结果
10. **AI导演助理**：提供创意建议、镜头设计指导等增值功能
11. **跨模态一致性**：确保视觉输出与剧本文字描述在情感、风格上的高度一致
12. **个性化定制**：根据用户偏好调整分镜风格、节奏、构图等参数，满足不同创作者的需求


### 终极目标

1. **任意剧本适配**：任何长度、任何语言、任何类型
2. **零信息损失**：剧本100%内容被视觉化呈现
3. **专业级输出**：达到专业导演分镜水准
4. **实时交互**：边写剧本边生成预览
5. **风格定制**：可指定任何导演风格/电影美学
6. **自动优化循环**：每次使用都在进化
7. **剧本-片段双向追溯**：每个片段可追溯回原文位置，支持交叉验证
8. **语义对齐度检测**：评估生成片段与原文的匹配程度
9. **多轮修正机制**：根据检测结果自动调整再生成
10. **剧本理解深度**：潜台词、隐喻、象征的视觉化映射
11. **风格一致性引擎**：全剧视觉风格统一（色调、构图、节奏）
12. **自动分镜评分**：从专业导演视角评估分镜质量
13. **人工反馈闭环**：用户调整结果反馈给模型持续优化



## 贡献指南

欢迎提交Issue和Pull Request来改进这个项目：

1. **报告问题**：在使用中遇到的问题
2. **功能建议**：希望添加的新功能
3. **代码优化**：性能优化或代码重构
4. **文档改进**：补充或修正文档x1