"""Ninja Persistence — unified polyglot persistence layer for Ninja Stack."""

from ninja_persistence.adapters.chroma import ChromaVectorAdapter
from ninja_persistence.adapters.graph import GraphAdapter
from ninja_persistence.adapters.milvus import MilvusVectorAdapter
from ninja_persistence.adapters.mongo import MongoAdapter
from ninja_persistence.adapters.sql import SQLAdapter
from ninja_persistence.connections import ConnectionManager, ConnectionProfile
from ninja_persistence.embedding.strategy import EmbeddingStrategy
from ninja_persistence.protocols import Repository
from ninja_persistence.registry import AdapterRegistry

__all__ = [
    "AdapterRegistry",
    "ChromaVectorAdapter",
    "ConnectionManager",
    "ConnectionProfile",
    "EmbeddingStrategy",
    "GraphAdapter",
    "MilvusVectorAdapter",
    "MongoAdapter",
    "Repository",
    "SQLAdapter",
]
