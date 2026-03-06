"""
@FileName: llama_index_loader.py
@Description: LlamaIndex 文档加载模块，提供各种文档加载器，支持不同格式的文档导入
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/12/18
"""

import os
from typing import List, Dict, Optional, Any
from llama_index.core import SimpleDirectoryReader
from llama_index.core.schema import Document
from hengshot.logger import debug, info, error


class DocumentLoader:
    """
    文档加载器类
    负责从各种来源加载单个文档
    """
    
    @staticmethod
    def load_file(file_path: str, **kwargs) -> Optional[Document]:
        """
        加载单个文件
        
        Args:
            file_path: 文件路径
            **kwargs: 额外参数
                - text_kwargs: 文本处理参数
                - encoding: 文件编码
                
        Returns:
            Document对象，如果加载失败返回None
        """
        try:
            if not os.path.exists(file_path):
                error(f"文件不存在: {file_path}")
                return None
            
            debug(f"开始加载文件: {file_path}")
            
            # 获取文件扩展名
            file_ext = os.path.splitext(file_path)[1].lower()
            
            # 支持的文件类型
            supported_types = ['.txt', '.md', '.pdf', '.docx', '.doc', '.json', '.csv']
            
            if file_ext not in supported_types:
                warning(f"不支持的文件类型: {file_ext}，尝试作为文本文件加载")
            
            # 使用SimpleDirectoryReader加载单个文件
            # 需要将文件放在列表中，并且设置required_exts
            loader = SimpleDirectoryReader(
                input_files=[file_path],
                **kwargs
            )
            
            documents = loader.load_data()
            
            if documents and len(documents) > 0:
                info(f"成功加载文件: {file_path}，提取到{len(documents)}个文档")
                return documents[0]  # 返回第一个文档
            else:
                warning(f"文件加载成功但未提取到内容: {file_path}")
                return None
                
        except Exception as e:
            error(f"加载文件失败: {file_path}，错误: {str(e)}")
            return None
    
    @staticmethod
    def create_document(text: str, metadata: Optional[Dict[str, Any]] = None) -> Document:
        """
        直接从文本创建文档对象
        
        Args:
            text: 文档文本内容
            metadata: 文档元数据
            
        Returns:
            Document对象
        """
        if metadata is None:
            metadata = {}
            
        return Document(
            text=text,
            metadata=metadata
        )


class DirectoryLoader:
    """
    目录加载器类
    负责从目录加载多个文档
    """
    
    @staticmethod
    def load_directory(
        directory_path: str,
        recursive: bool = True,
        required_exts: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        **kwargs
    ) -> List[Document]:
        """
        加载目录中的所有文档
        
        Args:
            directory_path: 目录路径
            recursive: 是否递归加载子目录
            required_exts: 必需的文件扩展名列表，例如['.txt', '.md']
            exclude: 排除的文件或目录列表
            **kwargs: 额外参数传递给SimpleDirectoryReader
            
        Returns:
            Document对象列表
        """
        try:
            if not os.path.exists(directory_path):
                error(f"目录不存在: {directory_path}")
                return []
            
            if not os.path.isdir(directory_path):
                error(f"路径不是目录: {directory_path}")
                return []
            
            debug(f"开始加载目录: {directory_path}，递归={recursive}")
            
            # 配置加载器
            loader_kwargs = {
                'input_dir': directory_path,
                'recursive': recursive,
                **kwargs
            }
            
            # 添加必需的扩展名过滤
            if required_exts:
                loader_kwargs['required_exts'] = required_exts
            
            # 添加排除列表
            if exclude:
                loader_kwargs['exclude'] = exclude
            
            loader = SimpleDirectoryReader(**loader_kwargs)
            
            documents = loader.load_data()
            
            info(f"成功加载目录: {directory_path}，提取到{len(documents)}个文档")
            return documents
            
        except Exception as e:
            error(f"加载目录失败: {directory_path}，错误: {str(e)}")
            return []
    
    @staticmethod
    def load_directories(
        directory_paths: List[str],
        recursive: bool = True,
        required_exts: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        **kwargs
    ) -> List[Document]:
        """
        加载多个目录中的所有文档
        
        Args:
            directory_paths: 目录路径列表
            recursive: 是否递归加载子目录
            required_exts: 必需的文件扩展名列表
            exclude: 排除的文件或目录列表
            **kwargs: 额外参数
            
        Returns:
            合并后的Document对象列表
        """
        all_documents = []
        
        for directory_path in directory_paths:
            documents = DirectoryLoader.load_directory(
                directory_path,
                recursive=recursive,
                required_exts=required_exts,
                exclude=exclude,
                **kwargs
            )
            all_documents.extend(documents)
        
        info(f"成功加载{len(directory_paths)}个目录，总计提取到{len(all_documents)}个文档")
        return all_documents


def warning(message: str):
    """
    临时警告函数，后续可以从logger模块导入
    """
    print(f"[警告] {message}")