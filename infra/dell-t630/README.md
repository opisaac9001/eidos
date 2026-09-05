# Dell T630 inference host

This directory will contain reproducible host configuration after iDRAC hardware
inventory is captured. It intentionally does not yet pin an operating system,
driver, CUDA toolkit, or container image.

## Intended responsibilities

- Serve text-generation models behind an authenticated internal API.
- Generate embeddings and optionally rerank retrieved memories.
- Provide speech and image capabilities that work reliably on the installed
  hardware.
- Export health, temperature, utilization, latency, and capacity metrics.
- Keep model data and generated artifacts on dedicated storage.

## Hardware realities

Tesla P40 is a 24 GB Pascal card with CUDA compute capability 6.1. It remains
useful for quantized inference, especially across several cards, but it lacks
modern tensor cores and is not supported by every contemporary inference
engine. The initial benchmark target is therefore llama.cpp with explicit
Pascal/CUDA configuration.

The 360 GB of system memory is useful for large model loading, CPU offload,
retrieval indexes, databases, and caching. It does not substitute for GPU
bandwidth, so actual model assignments will be chosen from benchmarks rather
than aggregate memory alone.

## Information required before installation

- Exact P40 count and PCIe topology
- CPU models and NUMA layout
- RAID controller, virtual disks, and physical drive inventory
- SSD model, endurance, and intended boot/data role
- Available network interfaces and switch speed
- Power supplies, power budget, and cooling state
- Current BIOS, lifecycle controller, and iDRAC firmware
