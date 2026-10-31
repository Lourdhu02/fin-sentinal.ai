# Model experiments

The shipped generator remains the configured Ollama model. The llama.cpp adapter
is implemented; no new GGUF has been downloaded or benchmarked in this series.

Evaluate Qwen3.5-4B Q4/Q6, Gemma 4 E4B Q4, and Qwen3.5-9B Q4 as challengers on the
target laptop. Pin artifact hashes and runtime versions before comparing them.
Start with one request slot and 4K/8K contexts. Measure actual runtime allocation,
including KV cache and vision projector; parameter counts are not a memory budget.

Measure exact fields, retrieval recall, citation precision, answer faithfulness,
abstention, time to first token, tokens/second, P95 latency, RAM/VRAM and sustained
thermal behavior. Compare CPU-only and GPU profiles on the same reviewed queries.

Docling, specialist document VLMs, compact embedding challengers and Qdrant remain
future experiments. Promote them only after quality and resource measurements.
Automatic hardware routing, semantic/numeric claim verification, layout bounding
boxes and validated SQL aggregation are not implemented yet.
