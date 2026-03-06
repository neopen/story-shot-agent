"""
@FileName: web_app.py
@Description: 集成到Web应用（FastAPI示例）
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/2/10 19:44
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from hengshot.hengline import generate_storyboard

app = FastAPI(title="视频分镜生成API")

class ScriptRequest(BaseModel):
    script_text: str
    task_id: str = None  # 可选，不传会自动生成

@app.post("/api/generate-storyboard")
async def generate_storyboard_endpoint(request: ScriptRequest):
    """
    生成视频分镜的Web API端点
    """
    try:
        result = await generate_storyboard(
            script_text=request.script_text,
            task_id=request.task_id
        )
        return {
            "success": True,
            "task_id": result.get("task_id"),
            "storyboards": result.get("shots", []),
            "metadata": result.get("metadata", {})
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)