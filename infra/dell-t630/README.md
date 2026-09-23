# Dell T630 inference host

Latest checked code deployment: `natural20260908a`, September 8, 2026.
See [deployment and recovery record](../../docs/DEPLOYMENT_2026_09_08.md).
The service is running, but Pathos's simulation clock remains paused.

This directory contains the systemd configuration for the commissioned Ubuntu
host. See [INVENTORY.md](INVENTORY.md) for current hardware and storage findings.

## Installed layout

- Ubuntu 26.04 LTS, UEFI, proprietary NVIDIA 580.173.02 driver.
- `/srv/eidos`: deployed working-tree snapshot and Python virtual environment.
- `/var/lib/eidos/observatory.sqlite3`: active SQLite database on the boot SSD.
- `/srv/eidos-data/eidos/models`: shared Ollama model files on the 8 TB HDD.
- `/srv/eidos-data/eidos/backups`: verified daily database snapshots on the HDD.
- `/etc/eidos`: role routing and per-worker GPU/listener configuration.
- `eidos.service`: observatory on loopback port 8767, with supervised cognition.
- `ollama@pathos`, `ollama@world`, `ollama@cognition`: isolated model workers.
- `eidos-backup.timer`: daily online SQLite backup with integrity verification.
- `eidos-gpu.service`: persistent GPU initialization and initial 180 W P40 /
  140 W RTX 3060 power limits, addressed by verified PCI slots.

Ollama 0.33.3 is the initial runtime, using its bundled CUDA 12 support for the
P40s. It provides the existing OpenAI-compatible model boundary without a full
CUDA development toolkit or container stack. A custom llama.cpp build remains a
future benchmarking option. Qwen2.5 14B is assigned to each P40 and Qwen2.5 7B to
the RTX 3060; the two 14B workers share stored weights but have separate GPU
allocations. `warm_model.py` loads the model before a worker reports readiness.

The mount unit is specific to this machine's existing XFS filesystem UUID. The
GPU environment files must match this machine's verified GPU ordering; prefer
UUIDs in the installed copies. These files do not format disks or create arrays.
Model routes are commissioning candidates, not a claim of semantic quality.

Run `python3 infra/dell-t630/smoke_models.py` on the server to exercise all three
workers concurrently with synthetic prompts and measure output throughput.
Run `.venv/bin/python -m eidos --routes-file /etc/eidos/model-routes.json probe-model`
to test the actual role contracts and semantic warning checks without changing
the saved world.
Run `.venv/bin/python infra/dell-t630/smoke_queue.py` to repeat the eight-role
probe through SQLite persistence and supervised workers, using a disposable
queue. Direct endpoint success alone does not verify this deployment boundary.

From a trusted Tailscale-connected computer, forward the observatory with:

```sh
ssh -N -L 127.0.0.1:8767:127.0.0.1:8767 isaac@pathos-server
```

Open `http://127.0.0.1:8767`. The matching port is required by the observatory's
Host/Origin checks. The application starts paused after restart by design;
resuming it is explicit and does not simulate server downtime at high speed.
Backups currently retain every snapshot; monitor free space and add retention
and off-host copies before long-term unattended operation.

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

The Kingston SSD now provides a working boot target. The 1 TB and 2 TB drives are
still unavailable; the older inventory entries document the inconsistent views
that led to that choice. Commissioning proceeds using the two verified disks.

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
