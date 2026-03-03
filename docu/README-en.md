# Storyboard Generation Agent

An agent for converting screenplays into shot-level storyboards using multi-agent collaboration. It splits scripts in various formats into short AI-generatable video script units, outputs high-quality shot descriptions, and preserves narrative continuity. The system supports multiple AI providers, is highly extensible, and easy to use. It can be integrated as a Python library, Web API, LangGraph node, or A2A system.

> - Requirement: Given a roughly two-minute script, generate the corresponding short video sequences using AI models.
>
> - Technical constraint: Current video-generation models typically produce only 5–10 seconds per generation. To make a two-minute video, you must stitch multiple 5-second clips together.
>
> - Task & challenges: To stitch video clips, the first step is to split the original script into segments that closely match the target 5–10 second durations (depending on the model). Each clip must remain narratively coherent; otherwise stitched videos will have mismatched scenes, actions, or character continuity.
>
>   Actions, speech rate, and other factors affect duration — for example, an elderly person moves slower, angry shouting speeds up dialogue, running is faster than walking — so the agent must handle many situations.
>
>   This agent performs that task: the user provides a script, the system splits it according to configurable rules and model constraints, and returns segmented script fragments that the user can feed to video generation models (Runway, Pika, Sora, Wan, Stable Video, etc.) and later compose into a complete video using standard tools like FFmpeg.


Video creation pipeline: Client → LLM script authoring → <u>Storyboard parsing (splitting)</u> → DM video synthesis (text-to-video) → video assembly & rendering (FFmpeg)

Note: This agent does not currently author scripts, generate video, or perform final composition (future versions may add these). The highlighted step in the above pipeline is the agent's responsibility.

For a detailed architecture and design discussion, see: [Storyboard Agent — Architecture and Implementation Details](https://pengline.github.io/2025/10/0194020a663c408fb500dd7532349519/)


## Key Features

- Intelligent script parsing: automatically recognize scenes, dialogues, and action directives; understand story structure.
- Precise timing planning: split content into shots and assign reasonable durations.
- Continuity guardian: ensure adjacent shots keep character state, scene, and plot consistency.
- High-quality storyboard generation: produce detailed Chinese camera/scene descriptions and English AI prompt phrases for video models.
- Multi-model support: compatible with OpenAI, Qwen, DeepSeek, Ollama, and others.


## Quick Start

### 1. Environment

Prerequisites: Python 3.10 or newer

```bash
# Clone the project
git clone https://github.com/HengLine/video-shot-agent.git
cd video-shot-agent

# Install as an editable package
pip install -e .

######### Option 1: automatic install
# The script will try to create a virtual environment, install dependencies, and start the service. If it fails, follow the manual steps.
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

Copy configuration files and set environment variables:

```bash
cp .env.example .env
```

Edit the `.env` file and set required values:

```properties
# Deployment environment (development, production)
APP__ENVIRONMENT=development
# Script language preference, supported: zh (Chinese) or en (English)
APP__LANGUAGE=zh
# ================= API =================
# Server host
API__HOST=localhost
# Server port
API__PORT=8000

########################## LLM CONFIGURATION #########################
# Supported LLM providers (openai, qwen, deepseek, ollama). The fallback provider will be used if the default provider is not available.

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


### 4. API usage examples

Submit a job:

```sh
curl --location --request POST 'http://localhost:8000/api/v1/storyboard' \
--header 'Content-Type: application/json' \
--data-raw '{
    "script": "Title: \"A Rainy Appointment\"\nEstimated duration: ~30s\nScene: outside a city corner cafe, raining\nCharacters:\n- Lin Xiaoyu (F, 20, student, holding a soggy book)\n- Chen Yang (M, 22, part-time delivery driver, wearing a yellow raincoat)\n
[Opening]\n(Sound of rain, the camera tilts down from a gloomy sky and focuses on a bench outside the cafe. Lin Xiaoyu kneels beside the bench, using a handkerchief to pat a rain-damp poetry book, looking anxious.)\nLin Xiaoyu (murmuring, voice trembling):\n\"We agreed she'd return the book today... will he not show up because of the rain?\"\n
[Cut]\n(Chen Yang rides into the rain on his electric bike; a corner of a blue-covered book sticks out of the delivery box. He brakes abruptly, nearly hitting the bench; Lin Xiaoyu's book falls into a puddle.)\nChen Yang (frantically picking up the book, looking up):\n\"Sorry! Is this yours?\"\n
[CLOSE-UP]\n(Two books lie side-by-side in the puddle — Lin Xiaoyu's \"The Winged Ones\" and the same edition in Chen Yang's delivery box, with a lending sticker reading \"Lent: Chen Yang → Lin Xiaoyu\".)\nLin Xiaoyu (stunned, then smiling):\n\"You're ten minutes late, but... the book didn't get soaked.\"\n
Chen Yang (scratching his head, pulls a dry towel from his raincoat and wraps the book):\n\"I ran two blocks looking for a waterproof bag... The poem says 'Rain is the clouds' tears', but I don't want you to cry.\"\n
[Ending]\n(The rain eases, sunlight breaks through. Lin Xiaoyu opens the book and finds a movie ticket stub inside dated next Wednesday. Chen Yang takes off his raincoat and covers her head; they run together under an awning, laughing.)\nVoiceover (Lin Xiaoyu):\n\"Some promises may be late, but never absent.\"\n
[Black screen, subtitles appear]\n\"The rain will stop, and the story is just beginning.\"\n\nTone: fresh and healing with light humor, suitable for short video platforms.\nCore conflict: use the \"wet book\" and \"lateness\" for a small misunderstanding, reveal mutual interest via the matching book and ticket. Rain symbolizes emotional turning point."
}'
```

Retrieve job results:

```sh
# Example task_id returned after submission
curl --location --request GET 'http://localhost:8000/api/v1/result/hengline202602061816441424'
```

Check job status:

```sh
curl --location --request GET 'http://localhost:8000/api/v1/status/hengline202602061816441424'
```


## Input / Output example

Input: Chinese script text

```json
{
    "script": "At 11 PM in a city apartment living room, heavy rain slams the windows. Lin Ran is wrapped in an old wool blanket on the sofa while a muted black-and-white movie plays on the TV. A half-finished cup of cold tea has dew on it on the coffee table. An old photo album lies open. The phone suddenly vibrates and shows 'Unknown Number'. She stares for three seconds, her fingertip hovering above the answer key, throat tightening. Finally she presses accept and puts the phone to her ear. Silence for two seconds, then a hoarse male voice: 'It's me.' Lin Ran's fingers clench, her knuckles whitening. She breathes in and speaks with a trembling voice: '...Chen Mo? Are you okay?' The caller pauses then murmurs: 'I'm back.' Lin Ran jolts upright, pupils constrict, tears forming; she opens her mouth but can't make a sound; only the blanket slips from her shoulders.""
}
```

Output: structured storyboard result

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


## Agent integration examples

Installation:

```sh
# Download the wheel package and install (example v0.1.1-beta)
# https://github.com/HengLine/video-shot-agent/releases/download/v0.1.1-beta/hengshot-0.1.1-py3-none-any.whl
pip install hengshot-0.1.1-py3-none-any.whl
```

Configuration notes:

1. Copy the example environment file: `cp .env.example .env`
2. Edit `.env` and fill in real values

```properties
# Example .env
# ================= Application =================
APP__ENVIRONMENT=production
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

You can use the agent as a node in a LangGraph workflow:

```python
from pydantic import BaseModel, Field
from typing import Dict, Any

# Define state structure
class StoryboardState(BaseModel):
    script_text: str = Field(description="Input script text")
    task_id: str = Field(default=None, description="Task ID")
    storyboard_result: Dict[str, Any] = Field(default=None, description="Generated storyboard result")
    next_step: str = Field(default="", description="Next step indicator")


# Create storyboard generation node
async def storyboard_generator_node(state: StoryboardState) -> Dict[str, Any]:
    """
    LangGraph node that generates storyboard fragments
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


# Example workflow builder
def create_storyboard_workflow():
    workflow = StateGraph(StoryboardState)

    # Add node
    workflow.add_node("generate_storyboard", storyboard_generator_node)

    # Set entry point
    workflow.set_entry_point("generate_storyboard")
    workflow.add_edge("generate_storyboard", END)

    return workflow.compile()


# Usage example
async def run_langgraph_example():
    app = create_storyboard_workflow()

    initial_state = StoryboardState(
        script_text="A boy flying a kite in the park on a sunny day...",
        task_id="storyboard_task_001"
    )

    final_state = await app.ainvoke(initial_state)

    return final_state
```


### 4. Integrate into A2A systems

The storyboard agent can be integrated into Agent-to-Agent workflows where upstream agents provide scripts and downstream agents perform text-to-video and editing. Example:

```python
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class A2ATask:
    """A2A task dataclass"""
    task_id: str
    script_content: str
    priority: int = 1
    metadata: Dict[str, Any] = None


class StoryboardA2AAgent:
    """A2A agent wrapper for storyboard generation"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.task_queue = []

    async def process_task(self, task: A2ATask) -> Dict[str, Any]:
        """
        Process an A2A task
        """
        try:
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


## Roadmap and limitations

Notes:

1. The system depends on external LLM APIs and needs a stable network connection.
2. Generated video quality depends on the capabilities of the target video model.
3. Long scripts may need chunked processing.
4. Primary focus is Chinese; effectiveness in other languages requires verification.


MVP constraints:

1. Simple rules-based splitting; cannot handle very complex script structures.
2. No persistent memory across long processes — single-pass splitting only.
3. No online learning from user feedback.
4. Simple splitting logic — may cause continuity and timing compression issues.
5. Limited customization options.
6. Basic error handling — failures may abort the job.


Short-term (v1.x) goals:

1. Smarter shot splitting to keep action continuity.
2. Continuity checks for costumes, positions, and props.
3. Optimized prompts for specific video models (Sora, Pika, etc.).
4. Hybrid rules+LLM approach for robust parsing.
5. Full English-language input support.
6. Improved error recovery and graceful degradation.
7. More fine-grained configuration options.
8. Per-fragment confidence scoring.
9. Debug mode storing intermediate data for troubleshooting.


Mid-term (v2.x) goals:

1. Advanced camera language: complex moves (dolly, crane, pan, tilt, follow).
2. Emotion-aware visual style tuning.
3. Chunked processing with contextual memory for very long scripts.
4. Automated optimization from historical results.
5. Batch processing for multiple scripts.
6. Web-based visual interface.
7. Integration with asset libraries for character/scene references.
8. Multi-format exports: storyboard, timeline XML, dataset formats.
9. Stateful tracking using embeddings and IDs to support long workflows.
10. Result download and packaging.


Long-term (v3.x) vision:

1. Multi-modal input: images, audio and text combined.
2. Real-time low-resolution previews.
3. Intelligent continuity repair.
4. Integrations: Premiere/FCP/DaVinci plugins.
5. Collaboration features and version control.
6. Online learning from user feedback.
7. Commercial features: usage metrics, team management, SLAs.
8. Script repository with history and versioning.
9. Incremental processing that reuses unchanged fragments.
10. Traceability between script lines and generated fragments.
11. Semantic alignment scoring for fragment-script match.
12. Multi-round correction workflows.
13. Deep script understanding: subtext, metaphor, symbolism to visual mapping.
14. Global style consistency engine.
15. Automated director-level quality scoring.
16. User feedback loop for continual improvement.


## Contribution

Please open issues or pull requests to improve the project:

1. Report bugs or usage problems.
2. Propose new features.
3. Performance improvements or code refactors.
4. Documentation fixes or additions.
