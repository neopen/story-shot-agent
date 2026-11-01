import requests
from langchain_ollama import OllamaLLM
import subprocess
import time

def setup_ollama_connection(model_name="deepseek-r1:8b"):
    """确保 Ollama 连接和模型就绪"""
    
    # 检查 Ollama 服务是否可用
    try:
        response = requests.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            print("✓ Ollama 服务运行正常")
        else:
            print("✗ Ollama 服务异常")
            start_ollama_service()
    except requests.exceptions.ConnectionError:
        print("✗ Ollama 服务未启动，尝试启动...")
        start_ollama_service()
    
    # 检查模型是否存在
    try:
        response = requests.get("http://localhost:11434/api/tags")
        models = response.json().get("models", [])
        model_exists = any(model_name in model.get("name", "") for model in models)
        
        if not model_exists:
            print(f"模型 {model_name} 未找到，开始下载...")
            download_model(model_name)
        else:
            print(f"✓ 模型 {model_name} 已就绪")
            
    except Exception as e:
        print(f"检查模型时出错: {e}")

def start_ollama_service():
    """启动 Ollama 服务"""
    try:
        print("正在启动 Ollama 服务...")
        subprocess.Popen(["ollama", "serve"])
        time.sleep(5)  # 等待服务启动
        print("✓ Ollama 服务启动完成")
    except Exception as e:
        print(f"启动 Ollama 服务失败: {e}")
        print("请手动启动 Ollama 服务")

def download_model(model_name):
    """下载指定的模型"""
    try:
        print(f"正在下载模型: {model_name}")
        result = subprocess.run(["ollama", "pull", model_name], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ 模型 {model_name} 下载成功")
        else:
            print(f"下载失败: {result.stderr}")
            # 尝试下载一个更通用的模型
            fallback_model = "deepseek-r1:8b"
            print(f"尝试下载备用模型: {fallback_model}")
            subprocess.run(["ollama", "pull", fallback_model])
            return fallback_model
    except Exception as e:
        print(f"下载模型时出错: {e}")
        return None
    return model_name

# 在初始化 LLM 之前调用
def create_ollama_llm(model_name, temperature=0):
    """创建 Ollama LLM 实例，包含错误处理"""
    
    # 确保连接和模型就绪
    actual_model = setup_ollama_connection(model_name)
    
    if actual_model is None:
        # 如果指定模型失败，使用默认模型
        actual_model = "deepseek-r1:8b"
        print(f"使用默认模型: {actual_model}")
    
    try:
        llm = OllamaLLM(
            model=actual_model,
            temperature=temperature,
            base_url="http://localhost:11434",  # 明确指定 base_url
            client_kwargs={"timeout": 120}  # 超时通过 client_kwargs 传给 ollama.Client
        )
        
        # 测试连接
        test_response = llm.invoke("Hello")
        print(f"✓ Ollama 连接测试成功: {test_response}")
        return llm
        
    except Exception as e:
        print(f"创建 Ollama 实例失败: {e}")
        raise


if __name__ == "__main__":
    # 使用改进后的函数
    try:
        llm = create_ollama_llm("deepseek-r1:8b")
        # 现在可以安全地使用 self.llm.invoke(filled_prompt)
    except Exception as e:
        print(f"初始化失败: {e}")