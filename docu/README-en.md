# Storyboard Generation Agent

English | [中文](../README.md)

A multi-agent collaborative storyboard generation system that splits scripts in various formats into short AI-generatable video script units, outputs high-quality shot descriptions, and preserves narrative continuity. It supports multiple AI providers, is highly extensible and easy to use. The system can be used as a Python library, Web API, LangGraph node, or integrated into A2A systems.

> - Requirement: Given a roughly two-minute script, generate the corresponding short video sequences using AI models.
>
> - Technical constraint: Current models typically generate only 5–10 seconds of video per run. To produce a two-minute video you must compose multiple 5-second clips together.
>
> - Task & challenges: To enable video stitching, the first step is to split the original script into segments that are close to the target 5–10 second durations (depending on the model). Each clip must remain coherent; otherwise stitched clips will show mismatched scenes, actions, or character continuity.
>
>   Actions, speech rate and other factors affect timing — e.g., an elderly person moves slower, angry shouting accelerates delivery, running is faster than walking — so the splitter must consider many scenarios.
>
>   This agent performs that task. The user provides the script, the system splits it according to rules and configurable model constraints, and returns segmented script fragments the user can feed into video generation models (Runway, Pika, Sora, Wan, Stable Video, etc.). The final composition can be done with standard tools (FFmpeg) or future automated steps.


Video creation pipeline: Client → LLM script authoring → <u>Storyboard parsing (splitting)</u> → DM video synthesis (text-to-video) → video assembly & rendering (FFmpeg)

Note: This agent does not create scripts, generate video, or perform final composition in the current version (future versions may add these). The highlighted step above is the agent's responsibility.

For a detailed design and architecture discussion, see: [Storyboard Agent — Architecture and Implementation Details](https://pengline.github.io/2025/10/0194020a663c408fb500dd7532349519/)



## Core features

- Intelligent script parsing: automatically recognize scenes, dialogues and action directives; understand story structure.
- Precise timing planning: split content into shot-sized fragments and assign reasonable durations.
- Continuity guardian: ensure adjacent fragments maintain character state, scene and plot consistency.
- High-quality storyboard generation: produce detailed Chinese visual descriptions and English AI prompt phrases for video models.
- Multi-model support: compatible with OpenAI, Qwen, DeepSeek, Ollama and other providers.


## Quick start

### 1. Environment

Prerequisites: Python 3.10 or newer

```bash
# Clone the project
git clone https://github.com/HengLine/video-shot-agent.git
cd video-shot-agent

# Install as an editable package
pip install -e .

######### Option 1: automatic install
# The script will attempt to create a virtual environment, install dependencies and start the service. If it fails, follow the manual steps.
python main.py

######### Option 2: manual install
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

Edit the `.env` file and set required values:

```properties
# Deployment environment (development, production)
APP__ENVIRONMENT=development
# Script language preference, supported: zh (Chinese) or en (English)
APP__LANGUAGE=zh
# ================= API CONFIG =================
# Server host
API__HOST=localhost
# Server port
API__PORT=8000

########################## LLM CONFIG #########################
# Supported providers (openai, qwen, deepseek, ollama). A fallback provider will be used if the default provider is unavailable.

# ================= DEFAULT LLM SETTINGS =================
# Provider base URL
LLM__DEFAULT__BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1
# Provider API key
LLM__DEFAULT__API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# Provider model name
LLM__DEFAULT__MODEL_NAME=qwen-plus
# Generation temperature (0.0 = deterministic, 1.0 = higher randomness)
LLM__DEFAULT__TEMPERATURE=0.1
# Default API timeout (seconds)
LLM__DEFAULT__TIMEOUT=60
# Maximum retry attempts
LLM__DEFAULT__MAX_RETRIES=2
# Maximum tokens
LLM__DEFAULT__MAX_TOKENS=3000
LLM__DEFAULT__RETRY_DELAY=1

# ================= FALLBACK LLM SETTINGS =================
LLM__FALLBACK__BASE_URL=http://localhost:11434
LLM__FALLBACK__MODEL_NAME=qwen3:4b
LLM__FALLBACK__TEMPERATURE=0.1
LLM__FALLBACK__TIMEOUT=300
LLM__FALLBACK__MAX_TOKENS=5000
```


### 3. Start the application

```bash
python main.py
```

The service will start at `http://0.0.0.0:8000` and expose API endpoints.


### 4. Submit a job

Submit a job example (JSON payload shows a sample script):

```sh
curl --location --request POST 'http://localhost:8000/api/v1/storyboard' \
--header 'Content-Type: application/json' \
--data-raw '{
    "script": "深夜11点，城市公寓客厅，窗外大雨滂沱。林然裹着旧羊毛毯蜷在沙发里，电视静音播放着黑白老电影。茶几上半杯凉茶已凝出水雾，旁边摊开一本旧相册。手机突然震动，屏幕亮起“未知号码”。她盯着看了三秒，指尖悬停在接听键上方，喉头轻轻滚动。终于，她按下接听，将手机贴到耳边。电话那头沉默两秒，传来一个沙哑的男声：“是我。”  林然的手指瞬间收紧，指节泛白，呼吸停滞了一瞬。  她声音微颤：“……陈默？你还好吗？”  对方停顿片刻，低声说：“我回来了。” 林然猛地坐直，瞳孔收缩，泪水在眼眶中打转。她张了张嘴，却发不出声音，只有毛毯从肩头滑落。"
}'
```


### 5. Get results

Check job status:

```sh
# Example task_id returned after submission
curl --location --request GET 'http://localhost:8000/api/v1/status/HL202603061937129004'
```

Retrieve job result:

```sh
# Example task_id returned after submission
curl --location --request GET 'http://localhost:8000/api/v1/result/HL202603061937129004'
```

Output: structured storyboard result (`audio_prompt` contains audio prompt information)

(Example JSON omitted for brevity — the file contains a representative structured output with fragment prompts, durations, audio_prompt objects, etc.)


## Agent integration examples

Installation:

```sh
# Choose the desired release wheel from https://github.com/HengLine/video-shot-agent/releases
# Example:
# https://github.com/HengLine/video-shot-agent/releases/download/v0.1.3-beta/hengshot-0.1.3-py3-none-any.whl
pip install hengshot-0.1.1-py3-none-any.whl
# Install provider-specific LLM client packages as needed:
# pip install langchain-openai    # for openai or deepseek
# pip install dashscope          # for qwen
```

Configuration notes:

> 1. Copy the example environment file: `cp .env.example .env`
> 2. Edit `.env` and fill in real values

```properties
# .env - example
# ================= Application =================
APP__LANGUAGE=zh

# ================= DEFAULT LLM =================
LLM__DEFAULT__BASE_URL=https://api.openai.com/v1
LLM__DEFAULT__API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM__DEFAULT__MODEL_NAME=gpt-4-turbo-preview
LLM__DEFAULT__TEMPERATURE=0.7
LLM__DEFAULT__TIMEOUT=30
LLM__DEFAULT__MAX_RETRIES=3
LLM__DEFAULT__MAX_TOKENS=4000
```


### 1. Use as a Python library

```python
from hengshot.hengline import generate_storyboard
from hengshot.hengline.hengline_config import HengLineConfig

async def basic_usage():
    """Basic usage example"""
    script = """
    Scene: modern office
    Time: 3 PM
    Character: Xiaoli (programmer)
    Action: Xiaoli is coding when he receives a phone call and looks surprised
    """
    
    # Create custom LLM config
    custom_config = HengLineConfig(
        model_name="gpt-4",
        base_url="http://localhost:11434",  # assume Ollama is running locally
        temperature=0.2
    )

    # Simple call
    result = await generate_storyboard(
        script_text=script,
        config=custom_config
    )
    print(f"Task submitted, task_id: {result.get('task_id')}")
    print(f"Success: {result.get('success', False)}")
    print(f"Fragments: {result.get('data', {})}")

    return result
```


### 2. Integrate in a Web app (API)

You can integrate the storyboard agent via HTTP endpoints:

```python
@app.post("/api/generate-storyboard")
async def generate_storyboard_endpoint(script_text: str):
    """
    Web API endpoint that returns storyboard fragments
    """
    # Create custom LLM config
    custom_config = HengLineConfig(
        model_name="gpt-4",
        base_url="http://localhost:11434",  # assume Ollama is running locally
        temperature=0.2
    )
    try:
        return await generate_storyboard(
            script_text=script_text,
            config=custom_config
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")
```


### 3. LangGraph node integration

You can use the agent as a node in a LangGraph workflow. See examples in the repository for a sample node implementation and workflow wiring.


### 4. Integrate into A2A systems

The agent can be integrated into Agent-to-Agent workflows where upstream agents provide scripts and downstream agents perform text-to-video and editing.


## Version & limitations

> 1. Relies on external APIs: LLMs require stable network connectivity
> 2. AI model limits: generated video quality depends on video model capabilities
> 3. Long scripts: long scripts may require chunked processing
> 4. Multi-language: primarily optimized for Chinese, other languages need testing


### MVP limitations

1. Simple rules: uses fixed heuristics and cannot handle all complex structures
2. No persistent memory: supports a single split pass, not iterative long-text splitting
3. No learning: does not learn from user feedback
4. Simple splitting: may have continuity, duration compression issues
5. Limited customization: fewer configuration options
6. Simple error handling: unexpected errors may cause failure


### Short-term roadmap

1. Smarter splitting: optimize long-shot splitting to keep action continuity
2. Continuity checks: verify costume, position and prop consistency
3. Multi-model prompts: optimize prompts for Sora, Pika and others
4. Rules + LLM hybrid: support local rule processing combined with LLM
5. English script support: full support for English script input
6. Error fallback: smart degradation on node failure
7. Config expansion: finer-grained parameter controls
8. Quality scoring: output confidence score per fragment
9. Debug mode: save intermediate results for troubleshooting
10. Audio prompts: support audio prompt generation that aligns with visuals


### Mid-term roadmap

1. Advanced camera language: support complex camera moves (push/pull/track/pan/tilt)
2. Emotion analysis: adjust visual style according to script sentiment
3. Long-script processing: chunking with context memory
4. Auto-optimization: learn successful patterns from history
5. Batch processing: multi-script queue handling
6. Web UI: visual operations
7. Asset library integration: support reference images for characters/scenes
8. Multi-format export: storyboard, timeline XML, dataset formats
9. State memory: ID-based embeddings and state tracking for long scripts
10. Result download: export complete storyboard files


### Long-term roadmap

1. Multi-modal input: support images + audio + text
2. Real-time preview: low-resolution quick previews
3. Smart repair: automatically detect and fix continuity issues
4. Ecosystem integrations: Premiere/FCP/DaVinci plugins
5. Collaboration: multi-user collaboration and version control
6. Learning evolution: automatically improve from user feedback
7. Commercialization: usage metrics, team management, enterprise SLA
8. Script repository: historical script management and versioning
9. Incremental processing: reprocess only changed parts, reuse existing results
10. AI director assistant: offer creative suggestions and shot design guidance
11. Cross-modal consistency: ensure visual output matches script emotion and style
12. Personalization: adjust style, pacing and composition to user preferences


### Ultimate goals

1. Support any script length, language and genre
2. Zero information loss: fully visualize the script content
3. Professional-grade outputs: match director-level storyboard quality
4. Real-time interaction: generate previews while authoring
5. Style customization: support any director/film aesthetic
6. Continuous optimization loop: each use improves the system
7. Fragment↔script traceability: map each fragment back to original text
8. Semantic alignment checks: evaluate fragment-to-script match
9. Multi-round correction: auto-adjust and regenerate based on checks
10. Deep script understanding: visualize subtext, metaphor and symbolism
11. Global style engine: unify visual style across the whole script
12. Automatic storyboard scoring from a director's perspective
13. Human feedback loop: incorporate manual corrections into model updates


## Contributing

Contributions are welcome. Please open issues or PRs for:

1. Bug reports
2. Feature requests
3. Code improvements and refactors
4. Documentation updates
