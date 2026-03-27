# Storyboard Generation Agent

English | [中文](../README.md)

A multi-agent collaborative storyboard generation system that splits scripts in various formats into short AI-generatable video script units, outputs high-quality shot fragment descriptions, and preserves narrative continuity. It supports multiple AI providers, is highly extensible and easy to use. 

Using LangChain + LangGraph, any format script can be parsed and converted into "Text to Video" script prompt words that conform to the model (5-20 seconds), while maintaining the continuity and consistency of the character story between the segments. It can be directly applied to models such as Sora, Veo, Runway, Pika, Kling, Tongyi Wanxiang, Stable Video Diffusion, etc. It supports MCP, REST API protocols and Function Call, and can be integrated and used through methods such as A2A, LangGraph, API, and Python libraries.

>
> Video creation pipeline: Client → LLM script authoring → <u>Storyboard parsing (splitting)</u> → DM video synthesis (text-to-video) → video assembly & rendering (FFmpeg)
>
> Note: This agent does not author scripts, does not generate video, nor does it perform final composition in the current version (future releases may add these). The highlighted step above is the agent's responsibility.
>



## Core features

- Intelligent script parsing: automatically identify scenes, dialogues and action directives; understand story structure.
- Precise timing planning: split content into shot-sized fragments and assign reasonable durations (AI-compatible).
- Continuity guardian: ensure adjacent fragments preserve character state, scene and plot consistency.
- High-quality storyboard generation: produce detailed Chinese visual descriptions and English AI video prompts.
- Audio prompt support: generate environment and audio design prompts for each fragment.
- Multi-model support: compatible with OpenAI, Qwen, DeepSeek, Ollama and others.
- Easy-to-use APIs: provide a Python library, Web API, LangGraph node and A2A integration options.
- Configurable generation parameters: temperature, durations, model selection, and other controls.
- Error handling and retry: automatic retries for failed generation tasks to improve success rates.
- Traceability: every fragment can be traced back to its original position in the script for verification and editing.


## Quick start

### 1. Environment

Prerequisites: Python 3.10 or newer

```bash
# Clone the project
git clone https://github.com/neopen/video-shot-agent.git
cd video-shot-agent

# Install as an editable package
pip install -e .

######### Option 1: automatic install #########
# The script will attempt to create a virtual environment, install dependencies and start the service. If it fails, follow the manual steps.
python main.py

######### Option 2: manual install #########
python -m venv .venv

# Activate virtual environment (Windows)
.venv\Scripts\activate
# Or (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```


### 2. Configuration

Copy the example environment file and set environment variables:

```bash
cp .env.example .env
```

Edit the `.env` file and configure the required parameters:

```properties
# ================= API CONFIG =================
# Server host
API__HOST=localhost
# Server port
API__PORT=8000

########################## LLM CONFIG #########################
# Supported providers (openai, qwen, deepseek, ollama). A fallback provider will be used if the default provider is unavailable.

# ================= DEFAULT LLM SETTINGS =================
LLM__DEFAULT__BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1
LLM__DEFAULT__API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM__DEFAULT__MODEL_NAME=qwen-plus
LLM__DEFAULT__TIMEOUT=60
LLM__DEFAULT__MAX_TOKENS=4096
```


### 3. Start the application

```bash
python main.py
```

> The service will start at `http://0.0.0.0:8000` and expose API endpoints.
>


### 4. Submit a task

Submit a storyboard generation task (example request):

```sh
curl --location --request POST 'http://localhost:8000/api/v1/storyboard' \
--header 'Content-Type: application/json' \
--data-raw '{
    "script": "Late at night, 11 PM. In a city apartment living room, heavy rain slams the windows. Lin Ran is wrapped in an old wool blanket on the sofa while a muted black-and-white movie plays on the TV. A half-drunk cup of cold tea beads on the coffee table. An old photo album lies open. The phone suddenly vibrates and shows 'Unknown Number'. She stares for three seconds, fingertip hovering above the answer key, throat tightening. Finally she accepts and puts the phone to her ear. Silence for two seconds, then a hoarse male voice says, 'It's me.' Lin Ran's fingers clench and her knuckles turn white. She breathes and speaks with a trembling voice: '...Chen Mo? Are you okay?' The caller pauses and whispers: 'I'm back.' Lin Ran jolts upright, pupils constrict, tears welling; she opens her mouth but no sound comes out; only the blanket slips from her shoulders."
}'
```


### 5. Get results

Check task status:

```sh
# Example task_id returned after submission
curl --location --request GET 'http://localhost:8000/api/v1/status/HL202603061937129004'
```

Retrieve task result:

```sh
# Example task_id returned after submission
curl --location --request GET 'http://localhost:8000/api/v1/result/HL202603061937129004'
```

Output: structured storyboard result (the `audio_prompt` section contains audio prompt information)

Example (abbreviated) JSON output structure:

```json
{
  "fragments": [
    {
      "fragment_id": "frag_001",
      "prompt": "Cinematic wide shot: midnight 11 PM in a compact urban apartment living room — rain lashes violently against the window, blurring distant neon signs (pink, cyan, magenta) into soft streaks; dim ambient light from a silent black-and-white vintage film playing on an old CRT TV casts faint flickering glow; medium-gray fabric sofa, weathered oak coffee table, analog wall clock frozen at 11:00, half-drawn beige curtains; woman (Lin Ran) curled on sofa under a thick, off-white hand-knitted wool blanket — coarse texture, yellowed edges, visible pilling and wear; she wears a loose, muted gray cotton long-sleeve top with subtle collar folds; her face is tired but alert, eyes slightly red, jaw gently tensed; shallow depth of field, film grain, naturalistic color grading, moody chiaroscuro lighting, 35mm cinematic realism",
      "negative_prompt": "cartoon, anime, 3D render, photorealistic stock photo, bright lighting, smiling face, modern fashion, high saturation, text, logo, watermark, sharp focus everywhere, clean unused objects, glossy surfaces, daylight, people walking, dialogue subtitles",
      "duration": 4.2,
      "model": "runway_gen2",
      "style": "cinematic 35mm film, moody realism, shallow depth of field, natural lighting, muted palette, subtle motion blur on rain streaks",
      "requires_special_attention": false,
      "audio_prompt": {
        "audio_id": "audio_001",
        "prompt": "Low-frequency rain ambience (intensity 0.95), distant muffled TV static hiss (black-and-white film tone), near-silence punctuated by faint breath and fabric rustle — no speech, no music, no sudden transients; highly restrained dynamic range, immersive spatial audio, slight reverb suggesting small enclosed apartment space",
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
      "prompt": "medium shot, cinematic lighting, Lin Ran curled up on a light gray fabric sofa, wrapped in a creamy off-white vintage wool blanket — thick, coarse-knit, slightly yellowed and pilled at edges, showing visible wear; she wears a neutral-toned (light gray/mushroom beige) soft cotton long-sleeve top, loose fit, subtle collar pleats, no jewelry or decoration; her expression is exhausted yet alert, eyes slightly red-rimmed, quiet emotional tension; background: modern small-city apartment living room — light gray fabric sofa, warm-toned wooden coffee table, vintage wall clock frozen at 11:00, half-drawn curtains revealing blurred neon lights and rain-streaked window; muted black-and-white old film playing silently on TV screen; ambient low-frequency rain, faint TV static hum, restrained vocal dynamic range",
      "negative_prompt": "modern fashion clothing, bright colors, glossy textures, sharp focus on face only, text overlays, logos, cartoon style, anime, photorealistic skin imperfections, motion blur, shaky cam, high saturation, studio lighting, smiling, energetic pose, multiple people, clean unused objects",
      "duration": 3.0,
      "model": "runway_gen2",
      "style": "cinematic, realistic, muted color palette, shallow depth of field, Kodak Portra 400 film grain, emotionally restrained tone",
      "requires_special_attention": false,
      "audio_prompt": {
        "audio_id": "audio_002",
        "prompt": "ambient low-frequency rainfall (intensity 0.9), distant faint television white noise (black-and-white film static), near-silence with subtle breath and micro-movement cues, highly compressed vocal dynamic range, no dialogue, immersive domestic stillness",
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

(Actual output will contain a structured list of fragments with prompts, timing, audio prompts, metadata and continuity notes.)


## Integration examples

Notes on packaging and installation:

```sh
pip install penshot
# pip install https://github.com/neopen/video-shot-agent/releases/download/v0.2.1/penshot-0.2.1-py3-none-any.whl

# The package defaults to using Ollama; install provider-specific LLM clients as required:
# pip install langchain-openai  # for OpenAI/DeepSeek
# pip install dashscope        # for Qwen
```

Configuration notes:

> 1. Copy the example env file: `cp .env.example .env`
>
> 2. Edit `.env` and fill in real values (API keys, base URLs, model names)
>
>    ```python
>    # ================= LLM default config =================
>    LLM__DEFAULT__BASE_URL=https://api.openai.com/v1
>    LLM__DEFAULT__API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
>    LLM__DEFAULT__MODEL_NAME=gpt-4-turbo-preview
>    LLM__DEFAULT__TIMEOUT=30
>    LLM__DEFAULT__MAX_TOKENS=4000
>          
>    # ================= LLM Backup config =================
>    LLM__FALLBACK__BASE_URL=http://localhost:11434
>    LLM__FALLBACK__MODEL_NAME=qwen3:4b
>    LLM__FALLBACK__TIMEOUT=300
>    LLM__FALLBACK__MAX_TOKENS=5000
>    ```
>




### 1. Use as a Python library

```python
from penshot.api import PenshotFunction
from penshot.neopen import ShotConfig
from penshot.neopen.shot_language import Language

async def async_usage():
    """异步用法示例"""

    agent = PenshotFunction(language=Language.ZH, max_concurrent=5)

    script = """
    早晨，一个女孩在咖啡馆读书，阳光透过窗户...
    """
    
    task_id = agent.breakdown_script_async(
        script,
        callback=lambda r: print(f"回调: 任务 {r.task_id} 完成")
    )

    print(f"任务已提交: {task_id}")

    # 查询状态
    status = agent.get_task_status(task_id)
    print(f"初始状态: {status.get('status')}")

    # 等待结果
    result = await agent.wait_for_result_async(task_id)

    print(f"最终结果: 成功={result.success}, 状态={result.status}")

    return result
```


### 2. Integrate into a Web application (API)

You can expose a simple HTTP API endpoint to call the storyboard generator:

```python
from penshot.api import PenshotFunction
from penshot.neopen import ShotConfig
from penshot.neopen.shot_language import Language
from penshot.neopen.task.task_models import TaskStatus

def create_web_app(
        config: Optional[ShotConfig] = None,
        enable_cors: bool = True
) -> FastAPI:
    """
    创建 Web 应用

    Args:
        config: 全局配置
        enable_cors: 是否启用 CORS

    Returns:
        FastAPI 应用实例
    """

    app = FastAPI(
        title="Penshot 分镜生成 API",
        description="智能分镜视频生成服务",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # 初始化服务
    config = config or ShotConfig()
    penshot = PenshotFunction(config=config)

    # 启用 CORS
    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.post("/api/generate", response_model=TaskResponse, tags=["Storyboard"])
    async def generate_storyboard(
            request: ScriptRequest
    ):
        """
        生成视频分镜（异步）

        提交剧本进行分镜生成，立即返回 task_id
        """
        try:
            language = Language.ZH if request.language == "zh" else Language.EN

            # 确定任务ID
            task_id = request.task_id

            if request.wait:
                # 同步模式
                result = penshot.breakdown_script(
                    script_text=request.script_text,
                    task_id=task_id,
                    language=language,
                    wait_timeout=request.timeout
                )

                return TaskResponse(
                    task_id=result.task_id,
                    status=result.status,
                    message="同步处理完成" if result.success else f"处理失败: {result.error}",
                    created_at=datetime.now(timezone.utc)
                )
            else:
                # 异步模式
                task_id = penshot.breakdown_script_async(
                    script_text=request.script_text,
                    task_id=task_id,
                    language=language
                )

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

        - **task_id**: 任务ID
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


### 3. LangGraph node integration

The agent can be used as a node in a LangGraph workflow — see the repository docs for examples and wiring instructions.


### 4. A2A integration

Integrate the storyboard agent into agent-to-agent workflows where upstream agents provide scripts and downstream agents perform text-to-video generation and editing.


## Limitations & outlook

> 1. Relies on external APIs: stable network connectivity is required for LLM providers.
> 2. AI model limits: generated video quality depends on the capabilities of the chosen video model.
> 3. Long scripts: very long scripts may need chunked processing.
> 4. Multi-language: currently optimized for Chinese; other languages need further testing.
> 5. Uncertain generated durations: actual generated fragment durations may not perfectly match estimates.
> 6. Continuity challenges: maintaining continuity across fragments can be technically difficult.
> 7. No online learning: the current version does not learn from user feedback.
> 8. Error handling: exceptional cases may lead to failure.
> 9. Audio synchronization: lip sync and environmental audio design require further work.
> 10. Professional-grade storyboards: achieving director-level output will need iterative improvements.


### MVP limitations

1. Simple rules: uses heuristic rules and cannot handle very complex script structures.
2. No persistent memory: supports single-pass splitting; not designed for iterative long-text splitting.
3. No learning: does not learn from feedback.
4. Simple splitting: fragmentation may still produce continuity/duration issues.
5. Limited customization: fewer parameter options in this version.
6. Basic error handling: unexpected errors may cause task failure.


### Short-term roadmap

1. Smarter splitting: improve long-shot splitting to keep action continuity.
2. Continuity checks: verify costume, position and prop consistency.
3. Multi-model prompt tuning: optimize prompts for Sora, Pika and other models.
4. Rules + LLM hybrid: combine local rules with LLM processing.
5. English script support: full support for English input.
6. Error fallback: graceful degradation on node failure.
7. Configuration expansion: finer-grained parameters.
8. Quality scoring: output confidence per fragment.
9. Debug mode: save intermediate results for troubleshooting.
10. Audio prompts: generate audio prompts aligned with visuals.


### Mid-term roadmap

1. Advanced camera language: support complex camera moves (push/pull/track/pan/tilt).
2. Emotion analysis: adjust visual style according to script sentiment.
3. Long-script processing: chunking with context memory (RAG + vector DB).
4. Auto-optimization: learn successful patterns from history.
5. Batch processing: multi-script queue handling.
6. Web UI: visual operations and editing.
7. Asset library integration: support reference images for characters/scenes.
8. Multi-format export: storyboard, timeline XML, dataset formats.
9. More parameters: support camera motion types, composition rules, color grading presets.
10. Result download: export complete storyboard files.


### Long-term roadmap

1. Multi-modal inputs: support images + audio + text inputs.
2. Real-time preview: low-resolution quick previews.
3. Smart repair: automatically detect and fix continuity issues.
4. Ecosystem integrations: Premiere/FCP/DaVinci plugins.
5. Collaboration: multi-user collaboration and version control.
6. Learning evolution: automatically improve from feedback.
7. Commercialization: usage analytics, team management, enterprise SLAs.
8. Script repository: historical script management and versioning.
9. Incremental processing: reprocess only changed parts, reuse existing results.
10. AI director assistant: provide creative suggestions and shot design guidance.
11. Cross-modal consistency: ensure visuals align with script emotion and style.
12. Personalization: adapt style, pacing and composition to user preferences.


### Ultimate goals

1. Support any script length, language and genre.
2. Zero information loss: fully visualize script content.
3. Professional-grade outputs: match director-level storyboard quality.
4. Real-time interaction: generate previews while writing.
5. Style customization: support any director/film aesthetic.
6. Continuous optimization loop: each use improves the system.
7. Fragment↔script traceability: map fragments back to original text locations.
8. Semantic alignment checks: evaluate fragment-to-script match.
9. Multi-round correction: auto-adjust and regenerate based on checks.
10. Deep script understanding: visualize subtext, metaphor and symbolism.
11. Global style engine: unify visual style across the whole script.
12. Automatic storyboard scoring from a director's perspective.
13. Human feedback loop: incorporate manual corrections into model updates.


## Contributing

Contributions are welcome. Please open issues or PRs for:

1. Bug reports
2. Feature requests
3. Code improvements and refactors
4. Documentation updates
