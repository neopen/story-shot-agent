# 剧本分镜智能体

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

### 4. 调用接口

提交任务：

```sh
curl --location --request POST 'http://localhost:8000/api/v1/storyboard' \
--header 'Content-Type: application/json' \
--data-raw '{
    "script": "剧本标题：《雨中的约定》\n时长：约30秒\n场景：城市街角咖啡店外，雨天\n角色：\n- 林小雨（女，20岁，学生，抱着一本湿漉漉的书）\n- 陈阳（男，22岁，兼职外卖员，穿着黄色雨衣）\n\n[开场]\n（雨声淅沥，镜头从灰蒙蒙的天空下摇，聚焦在咖啡店外的长椅上。林小雨蹲在长椅旁，用手帕擦拭一本被雨水浸湿的诗集，神情焦急。）\n林小雨（自言自语，带着哭腔）：\n\"明明说好今天还书的……这雨下得，他会不会不来了？\"\n\n[镜头切换]\n（陈阳骑着电动车冲进雨幕，后座外卖箱里露出一角蓝色封面的书。他刹车太急，差点撞上长椅，林小雨的书掉进水洼。）\n陈阳（手忙脚乱捡书，抬头）：\n\"对不起！这书……是你的？\"\n\n[特写]\n（两本书并排躺在水洼里——林小雨的《飞鸟集》，陈阳外卖箱里的同款书，封面上贴着\"借阅卡：陈阳→林小雨\"。）\n林小雨（愣住，突然笑了）：\n\"你迟到十分钟，但……书没湿透。\"\n\n陈阳（挠头，从雨衣里掏出干毛巾裹住书）：\n\"我跑了两条街找防水袋……诗里说'\''雨是云的眼泪'\''，可我不想让你哭。\"\n\n[结尾]\n（雨渐小，阳光穿透云层。林小雨翻开书，里面夹着一张电影票根，日期是下周三。陈阳脱下雨衣罩在她头上，两人并肩跑向屋檐，笑声渐远。）\n画外音（林小雨的旁白）：\n\"有些约定，会迟到，但永远不会缺席。\"\n\n[黑屏，字幕浮现]\n\"雨会停，而故事才刚刚开始。\"\n\n风格：清新治愈，带点幽默，适合短视频平台传播。\n核心冲突：用\"湿书\"和\"迟到\"制造小误会，通过\"同款书\"和\"电影票\"暗示双向暗恋，雨天象征情感转折。"
}'
```

获取任务结果：

```sh
# hengline202602061816441424 为任务提交成功后返回的 task_id
curl --location --request GET 'http://localhost:8000/api/v1/result/hengline202602061816441424'
```

查看任务状态：

```sh
# hengline202602061816441424 为任务提交成功后返回的 task_id
curl --location --request GET 'http://localhost:8000/api/v1/status/hengline202602061816441424'
```



## 输入输出示例

输入：中文剧本

```json
{
    "script": "深夜11点，城市公寓客厅，窗外大雨滂沱。林然裹着旧羊毛毯蜷在沙发里，电视静音播放着黑白老电影。茶几上半杯凉茶已凝出水雾，旁边摊开一本旧相册。手机突然震动，屏幕亮起“未知号码”。她盯着看了三秒，指尖悬停在接听键上方，喉头轻轻滚动。终于，她按下接听，将手机贴到耳边。电话那头沉默两秒，传来一个沙哑的男声：“是我。”  林然的手指瞬间收紧，指节泛白，呼吸停滞了一瞬。  她声音微颤：“……陈默？你还好吗？”  对方停顿片刻，低声说：“我回来了。” 林然猛地坐直，瞳孔收缩，泪水在眼眶中打转。她张了张嘴，却发不出声音，只有毛毯从肩头滑落。”"
}
```

输出：结构化分镜结果

```json
{
  "fragments": [
    {
      "fragment_id": "frag_001",
      "prompt": "Cinematic wide shot of a rainy-night city apartment living room: rain-streaked window blurs vibrant neon signs outside into soft, glowing color smudges; interior lit solely by a single warm yellow floor lamp casting gentle light on a dusty vintage record player, faded movie posters on the walls, and stacked leather-bound notebooks; shallow depth of field, moody chiaroscuro lighting, film grain texture, 35mm cinematic color grading, atmospheric haze, hyper-detailed realism, slow ambient camera drift",
      "negative_prompt": "bright lighting, daylight, people, text, logos, modern furniture, clean surfaces, sharp focus everywhere, cartoonish style, low resolution, motion blur artifacts, lens flare, overexposure, cluttered composition",
      "duration": 4.0,
      "model": "runway_gen2",
      "style": "cinematic noir ambiance with nostalgic analog warmth",
      "requires_special_attention": false
    },
    {
      "fragment_id": "frag_002",
      "prompt": "Cinematic medium shot: Lin Ran curled up on a light gray fabric sofa, bare feet resting on a textured wool rug, knees covered by a faded indigo blanket with worn edges; she wears a creamy white cotton robe, hair slightly damp at the ends, her profile softly illuminated by warm floor lamp light revealing tired, serene contours; outside the window, a faint lightning flash briefly illuminates her still, delicate eyelashes — shallow depth of field, soft cinematic lighting, film grain texture, 35mm anamorphic lens aesthetic, natural skin tones, ultra-detailed fabric and textile realism, subtle ambient occlusion, moody yet intimate atmosphere.",
      "negative_prompt": "blurry, deformed hands, extra limbs, text, logos, cartoonish style, low resolution, oversaturated colors, harsh shadows, noisy grain, CGI look, anime style, smiling, motion blur, talking, open eyes blinking, daylight, cluttered background",
      "duration": 3.0,
      "model": "runway_gen2",
      "style": "Cinematic, moody, intimate, photorealistic, 35mm film aesthetic",
      "requires_special_attention": false
    }
    ......
  ]
}
```



## 智能体集成示例

**安装依赖**：

```sh
# 下载 whl 包，选择指定版本（v0.1.1-beta）
# https://github.com/HengLine/video-shot-agent/releases/download/v0.1.1-beta/hengshot-0.1.1-py3-none-any.whl
pip install hengshot-0.1.1-py3-none-any.whl
```

**环境配置**：

> 1. 复制示例文件：cp .env.example .env
>
> 2. 编辑 .env 文件，填入真实配置
>
> ```properties
> # .env - 实际配置文件
> # ================= 应用配置 =================
> APP__ENVIRONMENT=production
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

可以将剧本分镜智能体作为 LangGraph 工作流中的一个节点：

```python
# 定义状态结构
class StoryboardState(BaseModel):
    script_text: str = Field(description="输入剧本文本")
    task_id: str = Field(default=None, description="任务ID")
    storyboard_result: Dict[str, Any] = Field(default=None, description="分镜生成结果")
    next_step: str = Field(default="", description="下一步操作指示")


# 创建分镜生成节点
async def storyboard_generator_node(state: StoryboardState) -> Dict[str, Any]:
    """
    LangGraph 工作流中的分镜生成节点
    """
    try:
        result = await generate_storyboard(
            script_text=state.script_text,
            task_id=state.task_id
        )

        return {
            "storyboard_result": result,
            "next_step": "storyboard_generated"
        }
    except Exception as e:
        return {
            "storyboard_result": {"error": str(e)},
            "next_step": "error"
        }


# 构建工作流示例
def create_storyboard_workflow():
    workflow = StateGraph(StoryboardState)

    # 添加节点
    workflow.add_node("generate_storyboard", storyboard_generator_node)

    # 设置入口点
    workflow.set_entry_point("generate_storyboard")
    workflow.add_edge("generate_storyboard", END)

    return workflow.compile()


# 使用示例
async def run_langgraph_example():
    app = create_storyboard_workflow()

    # 初始化状态
    initial_state = StoryboardState(
        script_text="一个男孩在公园里放风筝，天空很蓝...",
        task_id="storyboard_task_001"
    )

    # 运行工作流
    final_state = await app.ainvoke(initial_state)

    return final_state
```

### 4. 集成到A2A系统

将剧本分镜智能体集成到Agent-to-Agent协作系统中：

如：上游是剧本创作智能体，下游是 文生视频+剪辑 智能。

```python
@dataclass
class A2ATask:
    """A2A任务数据类"""
    task_id: str
    script_content: str
    priority: int = 1
    metadata: Dict[str, Any] = None


class StoryboardA2AAgent:
    """分镜生成的A2A代理"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.task_queue = []

    async def process_task(self, task: A2ATask) -> Dict[str, Any]:
        """
        处理A2A任务
        """
        try:
            # 调用分镜生成智能体
            result = await generate_storyboard(
                script_text=task.script_content,
                task_id=task.task_id
            )

            return {
                "agent_id": self.agent_id,
                "task_id": task.task_id,
                "status": "completed",
                "result": result,
                "metadata": task.metadata or {}
            }
        except Exception as e:
            return {
                "agent_id": self.agent_id,
                "task_id": task.task_id,
                "status": "failed",
                "error": str(e)
            }
```



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