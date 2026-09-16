# -*- coding: utf-8 -*-
"""Verify GPU model loading on Python 3.12 (RTX 5060)."""
import time
import pyarrow.dataset  # noqa: F401

print("=== 1) settings 读取 ===", flush=True)
from backend.src.config import settings
print("openai_api_key len:", len(settings.openai_api_key), flush=True)
print("openai_api_base:", settings.openai_api_base, flush=True)
print("bge_model_path:", settings.bge_model_path, flush=True)

print("=== 2) BGE-M3 加载 (GPU) ===", flush=True)
from backend.src.rag.embedder import embedder
t0 = time.perf_counter()
embedder.warmup()
print(f"BGE-M3 加载耗时: {time.perf_counter()-t0:.1f} s", flush=True)

dv, _ = embedder.embed_query("血管超声图像分割的核心功能")
print(f"embed_query dim: {dv.shape}", flush=True)

print("=== 3) Reranker 加载 + 检索 (GPU) ===", flush=True)
from backend.src.rag.retriever import retriever
t0 = time.perf_counter()
ev = retriever.retrieve("血管超声图像分割的核心功能")
print(f"检索耗时: {time.perf_counter()-t0:.1f} s, 结果 {len(ev)} 条", flush=True)
for e in ev[:3]:
    print(f"  - {e['source'][:30]} score={e['score']:.3f}", flush=True)

import torch
print(f"GPU 峰值显存: {torch.cuda.max_memory_allocated()/1024**3:.2f} GB", flush=True)
