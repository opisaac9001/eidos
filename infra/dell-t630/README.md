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

The verified 256 GB of system memory is useful for large model loading, CPU offload,
retrieval indexes, databases, and caching. It does not substitute for GPU
bandwidth, so actual model assignments will be chosen from benchmarks rather
than aggregate memory alone.

The first live inventory is recorded in [INVENTORY.md](INVENTORY.md). OS installation
is currently blocked because the only detected 2 TB SATA SSD reports failed with
zero usable capacity. RAID and boot configuration must remain untouched until a
healthy installation target is present.

## Information required before installation

- Confirm that the three video controllers in PCIe slots 3, 6, and 7 are Tesla P40s
- CPU models and NUMA layout
- RAID controller, virtual disks, and physical drive inventory
- SSD model, endurance, and intended boot/data role
- Available network interfaces and switch speed
- Power supplies, power budget, and cooling state
- Current BIOS, lifecycle controller, and iDRAC firmware

## Read-only first contact

Before choosing or installing an operating system, export the iDRAC HTTPS
certificate and run the bounded Redfish inventory command from a trusted machine.
It performs GET requests only and refuses plain HTTP or URLs containing embedded
credentials:

```bash
export EIDOS_IDRAC_URL=https://IDRAC_HOST
export EIDOS_IDRAC_USERNAME=YOUR_IDRAC_USER
export EIDOS_IDRAC_PASSWORD=YOUR_IDRAC_PASSWORD
PYTHONPATH=src .venv/bin/python -m eidos inventory-server \
  --ca-file /path/to/idrac-ca.pem \
  --output infra/dell-t630/inventory.local.json
```

Keep `inventory.local.json` private because serial numbers and network addresses
can appear in it; local inventory reports are ignored by Git. Review the report
before any disk, firmware, BIOS, boot, RAID, or operating-system change. If the
certificate cannot be validated, fix trust or replace the iDRAC certificate—the
tool deliberately has no insecure TLS switch.
