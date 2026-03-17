"""
@FileName: langchain_memory_tool.py
@Description: 使用LangChain的VectorStoreRetrieverMemory实现时序规划智能体的状态记忆功能
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10 - 2025/11
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain.docstore.document import Document
from langchain.memory import VectorStoreRetrieverMemory
from langchain_community.vectorstores import Chroma

from penshot.neopen.client.client_factory import get_default_embedding_client
from penshot.logger import debug, warning, error
from penshot.utils.log_utils import print_log_exception


class LangChainMemoryTool:
    """
    使用LangChain的VectorStoreRetrieverMemory实现的状态记忆工具
    替代原有的向量记忆+状态机功能
    """

    def __init__(self):
        """
        初始化LangChain记忆工具
        """
        # 默认配置路径
        self.config_path = Path(__file__).parent.parent / "config" / "langchain_memory_config.yaml"
        self.config = self._load_config()

        # 默认使用内存模式
        self.use_memory_mode = True
        self._memory_store = []
        self.embeddings = None

        try:
            # 初始化嵌入模型
            debug("开始初始化嵌入模型...")
            self.embeddings = get_default_embedding_client()

            if not self.embeddings:
                debug("嵌入模型为None")
            else:
                debug(f"嵌入模型类型: {type(self.embeddings).__name__}")
                # 检查嵌入模型的具体属性
                if hasattr(self.embeddings, 'model_name'):
                    debug(f"嵌入模型名称: {self.embeddings.model_name}")
                elif hasattr(self.embeddings, 'model'):
                    debug(f"嵌入模型名称: {self.embeddings.model}")

            # 检查嵌入模型是否兼容
            compatibility = False
            if self.embeddings:
                debug("开始检查嵌入模型兼容性...")
                compatibility = self._is_embeddings_compatible(self.embeddings)
                debug(f"嵌入模型兼容性检查结果: {compatibility}")

                # 验证适配器是否成功添加
                if compatibility:
                    has_doc = hasattr(self.embeddings, 'embed_documents')
                    has_query = hasattr(self.embeddings, 'embed_query')
                    debug(f"嵌入模型适配器状态 - embed_documents: {has_doc}, embed_query: {has_query}")

            if self.embeddings and compatibility:
                try:
                    # 确保chromadb可用
                    debug("检查chromadb是否可用...")
                    try:
                        import chromadb
                        debug(f"chromadb版本: {chromadb.__version__}")
                    except ImportError:
                        warning("尝试使用chromadb，但未安装")
                        return

                    # 初始化向量存储
                    debug("开始初始化向量存储...")
                    self.vectorstore = self._initialize_vectorstore()
                    debug("向量存储初始化成功")

                    # 初始化记忆检索器
                    debug("开始初始化记忆检索器...")
                    self.memory = self._initialize_memory()
                    debug("记忆检索器初始化成功")

                    self.use_memory_mode = False
                    debug("成功切换到向量存储模式")
                except ImportError as e:
                    debug(f"导入错误: {e}")
                    if "chromadb" in str(e):
                        warning("缺少chromadb包，将使用简化的内存模式。安装: pip install chromadb")
                    else:
                        warning(f"初始化向量存储失败: {e}，将使用简化的内存模式")
                except Exception as e:
                    debug(f"初始化异常: {type(e).__name__}: {e}")
                    warning(f"初始化向量存储和记忆检索器失败: {e}，将使用简化的内存模式")
            else:
                # 为不兼容的嵌入模型提供适配或回退
                if self.embeddings:
                    debug("嵌入模型存在但不兼容")
                    warning("嵌入模型不兼容或缺少必要方法，将使用简化的内存模式")
                else:
                    debug("嵌入模型不存在")
                    warning("无法初始化嵌入模型，将使用简化的内存模式")
        except Exception as e:
            debug(f"整体初始化异常: {type(e).__name__}: {e}")
            warning(f"初始化过程发生错误: {e}，将使用简化的内存模式")

        debug(f"LangChain记忆工具初始化完成 (模式: {'内存' if self.use_memory_mode else '向量存储'})")

    def _is_embeddings_compatible(self, embeddings) -> bool:
        """
        检查嵌入模型是否兼容
        
        Args:
            embeddings: 嵌入模型实例
            
        Returns:
            是否兼容
        """
        # 检查是否是llama_index的OllamaEmbedding
        if isinstance(embeddings, LlamaOllamaEmbedding):
            debug("检测到llama_index的OllamaEmbedding，添加专用适配器")
            # 使用包装类替换原始嵌入模型
            wrapper = self._add_llama_index_embeddings_adapter(embeddings)
            if wrapper:
                # 替换self.embeddings为包装后的对象
                self.embeddings = wrapper
                return True
            else:
                warning("创建llama_index的OllamaEmbedding适配器失败")
                return False

        # 检查必要的方法是否存在
        required_methods = ['embed_documents', 'embed_query']
        missing_methods = []

        for method in required_methods:
            if not hasattr(embeddings, method):
                missing_methods.append(method)

        # 如果有缺失的方法，尝试添加通用适配器
        if missing_methods:
            warning(f"嵌入模型缺少方法: {missing_methods}，尝试添加通用适配器")
            self._add_generic_embeddings_adapter(embeddings)
            # 即使添加了适配器，也需要再次检查方法是否已成功添加
            new_missing_methods = []
            for method in required_methods:
                if not hasattr(embeddings, method):
                    new_missing_methods.append(method)

            if not new_missing_methods:
                debug("适配器添加成功，所有必要方法已可用")
                return True
            else:
                warning(f"适配器添加失败，仍缺少方法: {new_missing_methods}")
                return False

        # 如果所有方法都存在，直接返回兼容
        debug("嵌入模型已包含所有必要方法")
        return True

    def _add_llama_index_embeddings_adapter(self, embeddings):
        """
        为llama_index的OllamaEmbedding创建包装类适配器
        
        Args:
            embeddings: llama_index的OllamaEmbedding实例
            
        Returns:
            包装后的嵌入模型对象
        """

        # 创建一个包装类，而不是尝试修改原始对象
        class OllamaEmbeddingsWrapper:
            def __init__(self, original_embeddings):
                self.original_embeddings = original_embeddings
                # 复制原始对象的属性
                for attr in dir(original_embeddings):
                    if not attr.startswith('__') and not callable(getattr(original_embeddings, attr)):
                        setattr(self, attr, getattr(original_embeddings, attr))

            def embed_documents(self, documents):
                results = []
                for doc in documents:
                    try:
                        # llama_index的OllamaEmbedding通常有get_text_embedding或embed方法
                        if hasattr(self.original_embeddings, 'get_text_embedding'):
                            embedding = self.original_embeddings.get_text_embedding(doc)
                        elif hasattr(self.original_embeddings, 'embed'):
                            embedding = self.original_embeddings.embed(doc)
                        else:
                            # 尝试直接调用嵌入对象，有些实现支持这种方式
                            embedding = self.original_embeddings(doc)

                        # 确保返回的是列表
                        if isinstance(embedding, list):
                            # 检查是否为空列表
                            if not embedding:
                                warning(f"嵌入结果为空列表，使用默认空向量")
                                results.append([0.0] * 1024)
                            else:
                                results.append(embedding)
                        elif hasattr(embedding, 'tolist'):
                            try:
                                # 捕获tolist()转换可能出现的异常
                                list_embedding = embedding.tolist()
                                # 检查转换后的列表是否为空
                                if not list_embedding:
                                    warning(f"嵌入结果转换为空列表，使用默认空向量")
                                    results.append([0.0] * 1024)
                                else:
                                    results.append(list_embedding)
                            except Exception as tolist_error:
                                warning(f"嵌入结果转换为列表失败: {tolist_error}")
                                results.append([0.0] * 1024)
                        else:
                            warning(f"嵌入结果格式不正确: {type(embedding)}")
                            # 使用适当维度的空向量作为后备
                            results.append([0.0] * 1024)  # 假设维度为1024
                    except Exception as e:
                        warning(f"生成文档嵌入失败: {e}")
                        # 使用适当维度的空向量作为后备
                        results.append([0.0] * 1024)
                return results

            def embed_query(self, query):
                if not query or not isinstance(query, str):
                    # raise ValueError("查询文本不能为空且必须为字符串")
                    return [0.0] * 1024
                try:
                    # llama_index的OllamaEmbedding通常有get_text_embedding或embed方法
                    if hasattr(self.original_embeddings, 'get_text_embedding'):
                        embedding = self.original_embeddings.get_text_embedding(query)
                    elif hasattr(self.original_embeddings, 'embed'):
                        embedding = self.original_embeddings.embed(query)
                    else:
                        # 尝试直接调用嵌入对象
                        embedding = self.original_embeddings(query)

                    # 确保返回的是列表
                    if isinstance(embedding, list):
                        # 检查是否为空列表
                        if not embedding:
                            warning(f"查询嵌入结果为空列表，使用默认空向量")
                            return [0.0] * 1024
                        return embedding
                    elif hasattr(embedding, 'tolist'):
                        try:
                            # 捕获tolist()转换可能出现的异常
                            list_embedding = embedding.tolist()
                            # 检查转换后的列表是否为空
                            if not list_embedding:
                                warning(f"查询嵌入结果转换为空列表，使用默认空向量")
                                return [0.0] * 1024
                            return list_embedding
                        except Exception as tolist_error:
                            warning(f"查询嵌入结果转换为列表失败: {tolist_error}")
                            return [0.0] * 1024
                    else:
                        warning(f"查询嵌入结果格式不正确: {type(embedding)}")
                        # 使用适当维度的空向量作为后备
                        return [0.0] * 1024
                except Exception as e:
                    print_log_exception()
                    error(f"生成查询嵌入失败: {e}")
                    # 使用适当维度的空向量作为后备
                    return [0.0] * 1024

        # 返回包装后的对象
        wrapper = OllamaEmbeddingsWrapper(embeddings)
        debug("已成功创建llama_index的OllamaEmbedding包装类适配器")
        return wrapper

    def _add_generic_embeddings_adapter(self, embeddings):
        """
        为其他不兼容的嵌入模型添加通用适配器
        
        Args:
            embeddings: 需要适配的嵌入模型实例
        """

        # 为嵌入模型添加embed_documents方法
        def embed_documents(documents):
            results = []
            for doc in documents:
                try:
                    # 尝试多种可能的方法
                    embedding = None
                    if hasattr(embeddings, 'embed'):
                        embedding = embeddings.embed(doc)
                    elif hasattr(embeddings, '__call__'):
                        try:
                            embedding = embeddings(doc)
                        except Exception:
                            pass

                    if embedding is None:
                        raise ValueError("无法找到可用的嵌入方法")

                    # 确保返回的是列表
                    if isinstance(embedding, list):
                        # 检查是否为空列表
                        if not embedding:
                            warning(f"嵌入结果为空列表，使用默认空向量")
                            results.append([0.0] * 1024)
                        else:
                            results.append(embedding)
                    elif hasattr(embedding, 'tolist'):
                        try:
                            # 捕获tolist()转换可能出现的异常
                            list_embedding = embedding.tolist()
                            # 检查转换后的列表是否为空
                            if not list_embedding:
                                warning(f"嵌入结果转换为空列表，使用默认空向量")
                                results.append([0.0] * 1024)
                            else:
                                results.append(list_embedding)
                        except Exception as tolist_error:
                            warning(f"嵌入结果转换为列表失败: {tolist_error}")
                            results.append([0.0] * 1024)
                    else:
                        warning(f"嵌入结果格式不正确: {type(embedding)}")
                        # 使用默认维度的空向量作为后备
                        results.append([0.0] * 1024)
                except Exception as e:
                    warning(f"生成文档嵌入失败: {e}")
                    # 使用默认维度的空向量作为后备
                    results.append([0.0] * 1024)
            return results

        # 添加embed_query方法
        def embed_query(query):
            try:
                # 尝试多种可能的方法
                embedding = None
                if hasattr(embeddings, 'embed'):
                    embedding = embeddings.embed(query)
                elif hasattr(embeddings, '__call__'):
                    try:
                        embedding = embeddings(query)
                    except Exception:
                        pass

                if embedding is None:
                    raise ValueError("无法找到可用的嵌入方法")

                # 确保返回的是列表
                if isinstance(embedding, list):
                    # 检查是否为空列表
                    if not embedding:
                        warning(f"查询嵌入结果为空列表，使用默认空向量")
                        return [0.0] * 1024
                    return embedding
                elif hasattr(embedding, 'tolist'):
                    try:
                        # 捕获tolist()转换可能出现的异常
                        list_embedding = embedding.tolist()
                        # 检查转换后的列表是否为空
                        if not list_embedding:
                            warning(f"查询嵌入结果转换为空列表，使用默认空向量")
                            return [0.0] * 1024
                        return list_embedding
                    except Exception as tolist_error:
                        warning(f"查询嵌入结果转换为列表失败: {tolist_error}")
                        return [0.0] * 1024
                else:
                    warning(f"查询嵌入结果格式不正确: {type(embedding)}")
                    # 使用默认维度的空向量作为后备
                    return [0.0] * 1024
            except Exception as e:
                print_log_exception()
                error(f"生成查询嵌入失败: {e}")
                # 使用默认维度的空向量作为后备
                return [0.0] * 1024

        # 动态添加方法
        embeddings.embed_documents = embed_documents
        embeddings.embed_query = embed_query
        debug("已尝试为嵌入模型添加通用适配器方法")

    def _load_config(self) -> Dict[str, Any]:
        """
        从单独的配置文件加载配置
        
        Returns:
            配置字典
        """
        default_config = {
            "vector_store": {
                "persist_directory": "./data/vectorstore_db"
            },
            "retrieval": {
                "search_kwargs": {"k": 5},
                "return_docs": True
            },
            "memory_keys": {
                "memory_key": "history",
                "input_key": "input"
            }
        }

        if self.config_path and self.config_path.exists():
            try:
                import yaml
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config:
                        debug(f"成功从 {self.config_path} 加载LangChain记忆配置")
                        return config
            except Exception as e:
                warning(f"加载配置文件失败: {e}，使用默认配置")

        return default_config

    def _initialize_vectorstore(self) -> Chroma:
        """
        初始化向量存储

        Returns:
            Chroma向量存储实例
        """
        try:
            # 从配置中获取持久化目录
            persist_directory = self.config.get("vector_store", {}).get("persist_directory", "./vectorstore_db")

            # 创建或加载向量存储
            vectorstore = Chroma(
                persist_directory=persist_directory,
                embedding_function=self.embeddings
            )
            debug(f"向量存储初始化成功，持久化目录: {persist_directory}")
            return vectorstore
        except Exception as e:
            error(f"初始化向量存储失败: {e}")
            # 返回一个简单的内存向量存储作为后备
            return Chroma(embedding_function=self.embeddings)

    def _initialize_memory(self) -> VectorStoreRetrieverMemory:
        """
        初始化记忆检索器

        Returns:
            VectorStoreRetrieverMemory实例
        """
        # 从配置中获取检索参数
        search_kwargs = self.config.get("retrieval", {}).get("search_kwargs", {"k": 5})

        retriever = self.vectorstore.as_retriever(
            search_kwargs=search_kwargs
        )

        # 从配置中获取键名
        memory_key = self.config.get("memory_keys", {}).get("memory_key", "history")
        input_key = self.config.get("memory_keys", {}).get("input_key", "input")
        return_docs = self.config.get("retrieval", {}).get("return_docs", True)

        memory = VectorStoreRetrieverMemory(
            retriever=retriever,
            memory_key=memory_key,
            input_key=input_key,
            return_docs=return_docs
        )

        return memory

    def store_state(self, state: Dict[str, Any], context: Optional[str] = None) -> bool:
        """
        存储状态到向量记忆中

        Args:
            state: 要存储的状态信息
            context: 上下文信息

        Returns:
            是否存储成功
        """
        try:
            # 构建状态文本
            state_text = json.dumps(state, ensure_ascii=False)

            # 添加上下文信息
            if context:
                state_text = f"上下文: {context}\n状态: {state_text}"

            # 使用内存模式
            if self.use_memory_mode:
                # 确保_memory_store存在
                if not hasattr(self, '_memory_store'):
                    self._memory_store = []

                self._memory_store.append({
                    "state": state,
                    "context": context,
                    "text": state_text
                })
                debug(f"内存模式 - 成功存储状态: {state.get('action', '未知动作')}")
                return True

            # 向量存储模式
            try:
                # 获取输入键名
                input_key = self.config.get("memory_keys", {}).get("input_key", "input")

                # 存储到向量数据库
                input_data = {input_key: state_text}
                if hasattr(self, 'memory') and self.memory:
                    self.memory.save_context(input_data, {})

                    # 检查是否需要自动持久化
                    if self.config.get("state_storage", {}).get("auto_persist", True):
                        self.persist_memory()

                    debug(f"成功存储状态: {state.get('action', '未知动作')}")
                    return True
                else:
                    error("memory属性不存在或为None")
                    return False
            except Exception as inner_e:
                error(f"向量存储模式存储失败: {inner_e}")
                return False
        except Exception as e:
            error(f"存储状态失败: {e}")
            return False

    def retrieve_similar_states(self, query: str, k: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        检索相似的状态

        Args:
            query: 查询文本
            k: 返回的结果数量

        Returns:
            相似状态列表
        """
        try:
            # 使用内存模式
            if self.use_memory_mode:
                results = []
                # 确保_memory_store存在
                if hasattr(self, '_memory_store'):
                    for item in self._memory_store:
                        # 简单的关键词匹配
                        if query.lower() in item["text"].lower():
                            results.append({
                                "content": item["text"],
                                "metadata": {"score": 1.0}
                            })
                    # 限制返回数量
                    if k:
                        results = results[:k]
                debug(f"内存模式 - 检索到 {len(results)} 个相似状态")
                return results

            # 向量存储模式
            try:
                # 检查必要属性
                if not hasattr(self, 'memory') or not self.memory:
                    error("memory属性不存在或为None")
                    return []
                if not hasattr(self, 'vectorstore'):
                    error("vectorstore属性不存在")
                    return []

                # 获取当前配置的k值
                original_k = self.config.get("retrieval", {}).get("search_kwargs", {}).get("k", 5)

                # 使用自定义的k值，如果提供
                if k:
                    self.config.setdefault("retrieval", {}).setdefault("search_kwargs", {})["k"] = k
                    retriever = self.vectorstore.as_retriever(
                        search_kwargs=self.config.get("retrieval", {}).get("search_kwargs", {})
                    )
                    self.memory.retriever = retriever

                # 检索相似状态
                input_key = self.config.get("memory_keys", {}).get("input_key", "input")
                similar_states = self.memory.load_memory_variables({input_key: query})

                # 恢复原始k值
                if k:
                    self.config.setdefault("retrieval", {}).setdefault("search_kwargs", {})["k"] = original_k
                    retriever = self.vectorstore.as_retriever(
                        search_kwargs=self.config.get("retrieval", {}).get("search_kwargs", {})
                    )
                    self.memory.retriever = retriever

                # 处理返回的文档
                results = []
                memory_key = self.config.get("memory_keys", {}).get("memory_key", "history")
                if memory_key in similar_states and similar_states[memory_key]:
                    if isinstance(similar_states[memory_key], list):
                        for doc in similar_states[memory_key]:
                            if isinstance(doc, Document):
                                results.append({
                                    "content": doc.page_content,
                                    "metadata": doc.metadata
                                })
                            else:
                                results.append({"content": str(doc)})
                    else:
                        results.append({"content": str(similar_states[memory_key])})

                debug(f"检索到 {len(results)} 个相似状态")
                return results
            except Exception as inner_e:
                error(f"向量存储模式检索失败: {inner_e}")
                return []
        except Exception as e:
            error(f"检索相似状态失败: {e}")
            return []

    def get_state_transition_suggestions(self, current_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        获取状态转换建议

        Args:
            current_state: 当前状态

        Returns:
            状态转换建议列表
        """
        try:
            # 使用内存模式
            if self.use_memory_mode:
                suggestions = []
                current_action = current_state.get("action", "").lower()

                # 确保_memory_store存在
                if hasattr(self, '_memory_store'):
                    for item in self._memory_store:
                        item_action = item["state"].get("action", "").lower()
                        # 找到与当前动作不同的状态作为建议
                        if item_action != current_action:
                            suggestions.append({
                                "state": item["state"],
                                "score": 1.0
                            })

                debug(f"内存模式 - 生成了 {len(suggestions)} 个状态转换建议")
                return suggestions

            # 向量存储模式
            try:
                # 构建查询
                current_action = current_state.get("action", "")
                current_emotion = current_state.get("emotion", "")
                query = f"从'{current_action}'动作和'{current_emotion}'情绪的状态转换"

                # 检索相似的状态转换
                similar_transitions = self.retrieve_similar_states(query)

                # 处理结果，提取可能的下一个状态
                suggestions = []
                for transition in similar_transitions:
                    try:
                        # 尝试从内容中提取状态信息
                        content = transition["content"]
                        if "状态: {" in content:
                            # 改进的JSON提取逻辑：使用正则表达式匹配完整的JSON对象
                            import re
                            # 匹配"状态: {"后面的第一个完整JSON对象
                            json_pattern = r'状态: (\{[^}]*\})'
                            match = re.search(json_pattern, content)
                            if match:
                                state_json = match.group(1)
                                try:
                                    state = json.loads(state_json)
                                    suggestions.append({
                                        "state": state,
                                        "score": transition.get("metadata", {}).get("score", 1.0)
                                    })
                                except json.JSONDecodeError as json_e:
                                    # 如果解析失败，尝试更宽松的方式
                                    # 查找最外层的括号对
                                    json_start = content.find("状态: {") + 5
                                    # 使用栈来找到匹配的结束括号
                                    brace_count = 0
                                    json_end = -1
                                    for i in range(json_start, len(content)):
                                        if content[i] == '{':
                                            brace_count += 1
                                        elif content[i] == '}':
                                            brace_count -= 1
                                            if brace_count == 0:
                                                json_end = i + 1
                                                break
                                    if json_end > json_start:
                                        state_json = content[json_start:json_end]
                                        try:
                                            state = json.loads(state_json)
                                            suggestions.append({
                                                "state": state,
                                                "score": transition.get("metadata", {}).get("score", 1.0)
                                            })
                                        except json.JSONDecodeError as json_e2:
                                            error(f"解析JSON失败(宽松模式): {json_e2}")
                                            error(f"问题JSON内容: {state_json[:100]}...")
                    except Exception as e:
                        error(f"处理转换建议失败: {e}")

                # 按分数排序
                suggestions.sort(key=lambda x: x["score"], reverse=True)

                debug(f"生成了 {len(suggestions)} 个状态转换建议")
                return suggestions
            except Exception as inner_e:
                error(f"向量存储模式获取转换建议失败: {inner_e}")
                return []
        except Exception as e:
            error(f"获取状态转换建议失败: {e}")
            return []

    def clear_memory(self) -> bool:
        """
        清空记忆

        Returns:
            是否清空成功
        """
        try:
            # 内存模式
            if self.use_memory_mode:
                if hasattr(self, '_memory_store'):
                    self._memory_store = []
                    debug("内存模式 - 记忆已清空")
                return True

            # 向量存储模式
            try:
                # 重新初始化向量存储
                self.vectorstore = self._initialize_vectorstore()
                self.memory = self._initialize_memory()
                debug("记忆已清空")
                return True
            except Exception as inner_e:
                error(f"向量存储模式清空失败: {inner_e}")
                return False
        except Exception as e:
            error(f"清空记忆失败: {e}")
            return False

    def persist_memory(self) -> bool:
        """
        持久化记忆

        Returns:
            是否持久化成功
        """
        # 内存模式下不需要持久化
        if self.use_memory_mode:
            debug("内存模式不需要持久化")
            return True

        try:
            # 检查vectorstore是否存在
            if hasattr(self, 'vectorstore') and hasattr(self.vectorstore, "persist"):
                self.vectorstore.persist()
                debug("记忆已持久化")
                return True
            else:
                debug("向量存储不存在或不支持持久化")
                return False
        except Exception as e:
            error(f"持久化记忆失败: {e}")
            return False
