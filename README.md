# 剧本分镜智能体

中文 | [English](docs/README-en.md)

一个基于多智能体协作的剧本分镜系统，能够将多种格式的剧本拆分为AI可生成的短视频脚本单元，输出高质量分镜片段描述，并保证叙事连续性。支持多种AI提供商，具有强大的可扩展性和易用性。

> 以 LangChain + LangGraph 实现通过 LLM 把任意格式剧本，解析转换为符合模型的 “Text to Video” 脚本片段提示词（5-n+5秒），且会保持片段间角色剧情的连贯性和一致性，可直接应用于Sora、Veo、Runway、Pika、Kling、通义万相、Stable Video Diffusion等模型。 支持 MCP、REST API 协议和 Function Call，可通过 A2A、LangGraph、API、Python 库等方式集成使用。

**创作流程**：客户端  → LLM 剧本创作  →  <u>***[剧本解析](https://github.com/neopen/video-shot-agent)（分镜转码）***</u> → DM 视频生成（文生视频） →  视频合成渲染（FFmpeg）

**该项目是典型的自然语言处理（NLP）应用场景**

> - **需求描述**：假如我有一段预估两分钟左右的剧本，想通过AI模型生成对应的短视频。
>
> - **技术受限**：目前的各种模型仅支持一次生成5-10秒长度的视频，想要生成两分钟长度的视频，只能通过“拼接”的方式，将多个5秒的片段合成为一个视频。
> - **任务&挑战点**：要实现视频拼接，第一步就需要拆分原剧本，拆分后的剧本尽量接近5-10秒时长（取决于模型），且每个视频片段还必须要保持连贯性，不然生成的视频片段合成后会导致场景、动作、人物等衔接不上。



架构及详细设计，参照博客文档：[剧本分镜智能体架构设计与实现（v1.0）](https://pengline.github.io/2026/02/7e6cd67dd5ee45248f2276ac145555f5/)




## 核心功能

- **智能剧本解析**：自动识别场景、对话和动作指令，理解故事结构
- **精准时序规划**：按镜头粒度智能切分内容，分配合理时长（符合AI）
- **连续性守护**：确保相邻分镜间角色状态、场景和情节的一致性
- **高质量分镜生成**：生成详细的中文画面描述和英文AI视频提示词
- **音频提示词支持**：为每个分镜生成对应的环境音和声音设计提示词
- **多模型支持**：兼容OpenAI、Qwen、DeepSeek、Ollama等多种AI提供商
- **易用的API接口**：提供Python库、Web API、LangGraph节点和A2A系统集成方式
- **可配置的生成参数**：支持温度、时长、模型选择等多维度参数配置
- **错误处理与重试机制**：自动重试失败的生成任务，确保高成功率
- **结果可追溯**：每个分镜片段都可追溯到原剧本位置，便于验证和调整

## 系统说明

1. **依赖外部API**：LLM版本需要稳定的网络连接
2. **AI模型限制**：生成的视频质量受限于AI视频模型能力
3. **处理长剧本**：长剧本可能需要分段处理
4. **多语言支持**：主要针对中文优化，其他语言效果待测试
5. **生成时长不确定**：AI生成的片段时长可能与预估不完全一致
6. **连续性挑战**：保持分镜间的连续性可能存在技术难点
7. **用户反馈机制**：当前版本不支持从用户反馈中学习优化
8. **错误处理**：异常情况可能导致生成失败
9. **声音同步**：实现声音与画面的一致性挑战，口型同步、环境音设计等需要进一步优化
10. **专业级分镜**：达到专业导演水准需要持续迭代和优化



## 快速上手

### 1. 环境准备

**前置条件**：Python 3.10 或更高版本

```bash
# 克隆项目
git clone https://github.com/neopen/video-shot-agent.git
cd video-shot-agent

# 安装为可编辑包
pip install -e .

######### 方式1：自动安装  #########
# 脚本会自动创建虚拟环境、安装依赖并启动服务，若失败，可手动安装
python main.py

######### 方式2：手动安装（uv） #########
uv venv --python 3.11
# 激活虚拟环境 (Linux/macOS)
source .venv/bin/activate
# 激活虚拟环境 (Windows)
.venv\Scripts\activate
# 安装依赖
uv pip install -r requirements.txt
```

### 2. 环境配置

复制配置文件并设置环境变量：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必要的参数：

```properties
#  服务器主机
API__HOST=localhost
#  服务器端口
API__PORT=8000

########################## LLM 模型配置 #########################
# LLM 厂商 API，支持的厂商（openai, qwen, deepseek, ollama）
LLM__DEFAULT__BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1
# LLM 厂商 KAY
LLM__DEFAULT__API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# LLM 厂商 模型
LLM__DEFAULT__MODEL_NAME=qwen-plus
# 默认API超时时间（秒）
LLM__DEFAULT__TIMEOUT=60
```

### 3. 启动应用

```bash
python main.py
```

> 应用将在 `http://0.0.0.0:8000` 启动，提供API 接口服务。
>

### 4. 提交任务

提交任务（自然语言短剧本）：

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

输出：结构化分镜结果（`audio_prompt` 为音频提示词信息，提示词包含双语）

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
        "voice_description": "ambient sound design only, no voice, pure atmospheric field recording style",
        "emotion": "neutral"
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
        "voice_description": "no voice, pure environmental atmosphere with ultra-low dynamic range and tactile silence",
        "emotion": "neutral",
        "previous_audio_id": "audio_001"
      }
    },
    ......
  ]
}
```



## 使用方法
### 环境准备

**安装依赖**：

```sh
# 直接安装
pip install penshot

# 内部默认安装使用 ollama，如果要使用其他平台，需要安装对应的LLM包
# pip install langchain-openai	使用 openai 或 deepseek
# pip install dashscope			使用千问
```

**配置环境**：

> 1. 复制示例文件：`cp .env.example .env`
>
> 2. 编辑 .env 文件，填入配置
>
> ```properties
> # ================= LLM默认配置 =================
> LLM__DEFAULT__BASE_URL=https://api.openai.com/v1
> LLM__DEFAULT__API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
> LLM__DEFAULT__MODEL_NAME=gpt-4-turbo-preview
> LLM__DEFAULT__TIMEOUT=30
> 
> # ================= LLM备用配置 =================
> LLM__FALLBACK__BASE_URL=http://localhost:11434
> LLM__FALLBACK__MODEL_NAME=qwen3:4b
> LLM__FALLBACK__TIMEOUT=300
> LLM__FALLBACK__MAX_TOKENS=5000
> ```



### 1. 作为Python库使用

```python
from penshot.api.function_calls import create_penshot_agent

async def async_usage():
    """异步用法示例"""
    penshot = create_penshot_agent(max_concurrent=5)

    script = """
    早晨，一个女孩在咖啡馆读书，阳光透过窗户...
    """

    # 异步提交任务
    task_id = penshot.breakdown_script_async(
        script,
        callback=lambda r: print(f"回调: 任务 {r.task_id} 完成")
    )

    print(f"任务已提交: {task_id}")

    # 查询状态
    status = penshot.get_task_status(task_id)
    print(f"初始状态: {status.get('status')}")

    # 等待结果
    result = await penshot.wait_for_result_async(task_id)

    print(f"最终结果: 成功={result.success}, 状态={result.status}")
```

示例代码：[video-shot-agent/example/direct_usage.py at main · neopen/video-shot-agent](https://github.com/neopen/video-shot-agent/blob/main/example/direct_usage.py)



### 2. 集成到Web应用（API）

可以通过 HTTP API 将剧本分镜智能体集成到各种 Web 应用中：

```python
from penshot.api.function_calls import create_penshot_agent
from penshot.neopen.task.task_models import TaskStatus

def create_web_app() -> FastAPI:
    app = FastAPI(
        title="Penshot 分镜生成 API",
        description="智能分镜视频生成服务",
        version="0.1.0"
    )

    # 初始化服务
    penshot = create_penshot_agent(max_concurrent=5)

    # 启用 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/api/generate", response_model=TaskResponse, tags=["Storyboard"])
    async def generate_storyboard(request: ScriptRequest):
        """
        生成视频分镜（异步）
        """
        try:
            # 异步模式
            task_id = penshot.breakdown_script_async(script_text=request.script_text)

            return TaskResponse(
                task_id=task_id,
                status=TaskStatus.PENDING,
                message="任务已提交，请使用 /api/status/{task_id} 查询状态",
                created_at=datetime.now(timezone.utc)
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")
            
    @app.get("/api/result/{task_id}", response_model=TaskResultResponse, tags=["Task"])
    async def get_task_result(task_id: str):
        """
        获取任务结果
        """
        result = penshot.get_task_result(task_id)

        if not result:
            raise HTTPException(status_code=404, detail=f"任务不存在或未完成: {task_id}")

        return TaskResultResponse(
            task_id=result.task_id,
            success=result.success,
            status=result.status,
            data=result.data,
            error=result.error,
            processing_time_ms=result.processing_time_ms
        )
```

示例代码：[video-shot-agent/example/web_app.py at main · neopen/video-shot-agent](https://github.com/neopen/video-shot-agent/blob/main/example/web_app.py)



### 3. 集成到 LangGraph 节点

可以将剧本分镜智能体作为 LangGraph 工作流中的一个节点。

示例代码：[video-shot-agent/example/langgraph_integration.py at main · neopen/video-shot-agent](https://github.com/neopen/video-shot-agent/blob/main/example/langgraph_integration.py)



### 4. 集成到 A2A 系统

将剧本分镜智能体集成到 Agent-to-Agent 协作系统中。如：上游是剧本创作智能体，下游是 文生视频+剪辑 智能体。

示例代码：[video-shot-agent/example/a2a_integration.py at main · neopen/video-shot-agent](https://github.com/neopen/video-shot-agent/blob/main/example/a2a_integration.py)



### 5. 使用 MCP Client

安装环境

```python
# 使用 Python 模块方式启动 MCP Server
python -m penshot.mcp_server
# 或指定参数启动 MCP Server
python -m penshot.mcp_server --max-concurrent 5 --queue-size 500
```

客户端示例

```python
class MCPClient:
    """MCP 客户端 - 同步版本，Windows 兼容"""

    def __init__(self, server_module: str = "penshot.mcp_server"):
        self.server_module = server_module
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')

    def start(self):
        """启动 MCP Server 子进程"""
        cmd = [sys.executable, "-m", self.server_module]

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            bufsize=1
        )
        print(f"MCP Server 已启动，PID: {self.process.pid}")
        time.sleep(2)

    def _clean_ansi(self, text: str) -> str:
        """清理 ANSI 转义码"""
        return self._ansi_escape.sub('', text)

    def read_json_response(self, timeout: float = 30) -> Optional[dict]:
        """读取 JSON 响应，跳过非 JSON 行并清理 ANSI 转义码"""

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # 检查是否有数据可读（非阻塞）
                import msvcrt
                if msvcrt.kbhit():
                    pass
            except:
                pass

            # 使用非阻塞方式读取
            try:
                # Windows 上不能直接 select 管道，使用轮询方式
                line = self.process.stdout.readline()
                if line:
                    cleaned_line = self._clean_ansi(line).strip()
                    if cleaned_line and cleaned_line.startswith('{'):
                        try:
                            return json.loads(cleaned_line)
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass

            # 短暂休眠，避免 CPU 占用过高
            time.sleep(0.05)

        return None

    def _call(self, method: str, params: dict = None) -> dict:
        """调用 MCP 方法"""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {}
        }

        # 发送请求
        request_str = json.dumps(request, ensure_ascii=False)
        try:
            self.process.stdin.write(request_str + "\n")
            self.process.stdin.flush()
        except BrokenPipeError:
            raise Exception("Server 进程已断开")

        # 读取响应
        response = self.read_json_response()
        if response is None:
            stderr = self.process.stderr.read()
            raise Exception(f"Server 无响应: {stderr}")

        return response

    def breakdown_script(self, script: str, wait: bool = False, timeout: int = 300) -> dict:
        """拆分剧本"""
        result = self._call("tools/call", {
            "name": "breakdown_script",
            "arguments": {
                "script": script.strip(),
                "wait": wait,
                "timeout": timeout
            }
        })

        if "error" in result:
            raise Exception(result["error"]["message"])

        content = result.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            text_content = content[0]["text"]
            try:
                parsed = json.loads(text_content)
                return parsed
            except json.JSONDecodeError:
                print(f"   [DEBUG] JSON解析失败，原始文本: {text_content}")
                return {}
        return {}

    def get_task_result(self, task_id: str) -> dict:
        """获取任务结果"""
        result = self._call("tools/call", {
            "name": "get_task_result",
            "arguments": {"task_id": task_id}
        })

        content = result.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
        return {}
```

详细示例代码：[video-shot-agent/example/mcp_client.py at main · neopen/video-shot-agent](https://github.com/neopen/video-shot-agent/blob/main/example/mcp_client.py)



## 版本与展望

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
3. **超长剧本**：分块处理+上下文记忆（RAG + 向量数据库）
4. **自动优化**：从历史结果学习成功模式
5. **批量处理**：多剧本队列处理
6. **Web界面**：可视化操作
7. **素材库集成**：支持角色/场景参考图
8. **多格式导出**：故事板、时间线XML、数据集格式
9. **更多参数**：支持更多细节控制，如镜头运动类型、构图规则、色调风格等
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

欢迎提交 Issue 和 Pull Request 来改进这个项目：

1. **报告问题**：在使用中遇到的问题
2. **功能建议**：希望添加的新功能
3. **代码优化**：性能优化或代码重构
4. **文档改进**：补充或修正文档