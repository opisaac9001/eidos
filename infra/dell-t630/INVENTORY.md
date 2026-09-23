# Dell T630 inventory and commissioning record

Last inspected through iDRAC: September 7, 2026.

This file deliberately omits service tags, serial numbers, MAC addresses, login
details, and management-network addresses. It records only deployment-relevant
hardware facts observed through iDRAC and Ubuntu. The later commissioning work
installed Ubuntu on the Kingston SSD; the earlier read-only findings below are
historical and are superseded by the current commissioning state.

## Current commissioning state — September 7, 2026

- Ubuntu 26.04 LTS installed on the 240 GB Kingston SATA SSD, UEFI confirmed.
- Kernel 7.0.0-31-generic; hostname `pathos-server`; Tailscale SSH verified.
- Linux reports 247 GiB usable RAM (256 GB installed).
- PCI inventory confirms one RTX 3060 12 GB and two Tesla P40 24 GB cards.
- Installer selected NVIDIA 595 open modules, which did not bind the P40s.
  Replaced with Ubuntu's proprietary 580.173.02 driver and prebuilt kernel modules.
- HGST 8 TB XFS disk mounted at `/srv/eidos-data`. It contains approximately
  6.7 TiB of existing files; these were preserved. About 659 GiB was free before
  model downloads. New project files live only under its `eidos/` directory.
- Active database and application live on the SSD; model files and verified
  daily database backups live on the separate HDD.
- Both disks passed SMART health and fresh short self-tests. No logged ATA errors,
  pending sectors, or interface CRC errors were reported. The SSD is used hardware
  (36,719 power-on hours); the HDD has 69,784 hours. Short tests are not full burn-in.
- The 1 TB and 2 TB disks are still unavailable to Linux. The PERC passthrough
  scan could not complete INQUIRY for device IDs 4 and 7. Do not assign them data
  until their controller/physical condition is resolved.
- Automatic suspend/hibernate is disabled for continuous server availability.
- Ollama 0.33.3 archive verified against the release SHA-256 before installation.
- Model endpoints and the observatory bind to loopback only; use Tailscale SSH
  forwarding for access. No public model or dashboard listener is configured.

### Commissioning verification

- Reboot completed in approximately 4.5 minutes. All three GPUs appeared under
  NVIDIA 580; data mount and enabled services started. Worker discovery then
  required an additional configuration correction: disable Vulkan and select
  `cuda_v12` explicitly. Each installed worker is pinned by GPU UUID.
- Corrected workers and observatory successfully started under systemd.
- Concurrent synthetic inference: P40 workers measured 25.50 and 25.24 output
  tokens/second with Qwen2.5 14B; RTX 3060 measured 63.18 with Qwen2.5 7B.
  Three further concurrent runs completed; highest sampled GPU temperature was
  55°C. No NVIDIA Xid or disk I/O errors were found. This is a short functional
  exercise, not a sustained thermal burn-in.
- Read-only direct-I/O sequential samples: SSD 377.75 MiB/s, HDD 195.74 MiB/s,
  with zero fio errors. These are 10-second reads, not random-write benchmarks.
- Direct and durable-queue probes both completed all eight narrative roles.
  The queue probe exposed a real MappingProxyType schema serialization defect;
  fixed at the HTTP boundary and covered by a failing-then-passing regression.
- Model prose still triggers semantic warnings (especially first-person thought
  and reflection voice). Contract success does not approve unattended simulation.
- Mac full suite before the commissioning fixes: 683 tests and 68 subtests passed.
  Linux non-month selection: 673 passed, one timing-test failure, nine deselected.
  Corrected the timing test to observe completed work instead of racing a 30 ms
  sleep and snapshot publication. After both fixes, the affected HTTP, durable
  queue, supervisor, jobs, and web suites passed on both hosts: 45 tests, 4 subtests.
- Migrated a verified snapshot with 4,056 events and 163 cognition jobs. The
  original Mac database remains separate. Server UI is on loopback port 8767,
  uses the real model routes, and intentionally starts paused in real-time mode.
- Daily backup timer and a manual post-boot backup both verified successfully.

## Verified hardware

- Dell PowerEdge T630, system revision I
- Two Intel Xeon E5-2680 v3 processors at 2.50 GHz
- 12 cores and 24 threads per processor; 24 cores and 48 threads total
- 256 GB DDR4-2133 multi-bit ECC memory
- Eight populated slots, each with one 32 GB Samsung quad-rank DIMM
- PERC H730 RAID adapter in PCI slot 8, firmware 25.4.0.0017
- Integrated Intel I350 dual-port gigabit Ethernet
- Two 1100 W output / 1232 W input AC power supplies are inventoried
- PS1 is present; PS2 is present but reports `Input lost | Input lost or out-of-range`
- BIOS 2.18.2; iDRAC and Lifecycle Controller 2.85.85.85
- iDRAC Enterprise license and HTML5 virtual-console support
- Three discrete video controllers are inventoried in PCIe slots 3, 6, and 7.
  This is consistent with the owner's Tesla P40 description, although iDRAC labels
  the devices generically rather than exposing the model in this view.
- A physical Ubuntu Server installer USB is reported by the owner; boot visibility
  remains to be verified. The iDRAC removable-media page only describes virtual
  media, and the first-boot page does not enumerate attached physical USB devices.

## Storage

iDRAC Redfish now detects four healthy SATA devices behind the PERC H730. All
reported `State: Enabled`, `Health: OK`, and `FailurePredicted: false`:

- Bay 1: HGST HUH728080AL, 8 TB SATA HDD, negotiated link 6 Gbps
- Bay 2: KINGSTON SA400S3, 240 GB SATA SSD, negotiated link 6 Gbps
- Bay 4: ST1000LX015 1U71, 1 TB SATA HDD, negotiated link 6 Gbps
- Bay 7: TEAM T2532TB, 2 TB SATA SSD, negotiated link 6 Gbps

Redfish exposes four `RawDevice` volumes that correspond one-to-one with the
physical disks above. No RAID array virtual disk was reported during this
read-only check.

## Ubuntu OS view

Ubuntu SSH was reached through Tailscale as the `isaac` host on September 7,
2026. The installed system reports UEFI boot mode and `/` mounted from the 2 TB
TEAM SSD:

- USB installer: SanDisk 3, 115 GB, mounted as Ubuntu 26.04 installer media
- 8 TB HGST HDD: visible as XFS data partition
- 240 GB Kingston SSD: visible with EFI and LVM member partitions
- 1 TB Seagate HDD: visible to Linux as `offline` with 0 B capacity
- 2 TB TEAM SSD: visible with EFI partition mounted at `/boot/efi` and ext4 root
  mounted at `/`

The 1 TB Seagate should be rechecked before using it because iDRAC reported it
healthy while Ubuntu reported it offline.

## Commissioning sequence

1. Re-run the full iDRAC inventory and export a private machine-readable copy.
2. Verify both power feeds, cooling health, GPU count, and PCIe topology.
3. Decide whether Ubuntu should keep using raw disks or whether the intended boot
   and data layout requires explicit RAID virtual disks.
4. Confirm the installed Ubuntu Server boot is UEFI and identify which disk hosts
   the operating system.
5. Enable OpenSSH and encrypted secrets.
6. Install and verify the NVIDIA driver before adding a model runtime.
7. Burn in every P40 independently, then together, while monitoring temperature and
   power.
8. Benchmark the Pascal-compatible llama.cpp path before assigning Eidos roles.
9. Deploy Eidos behind the private network boundary, restore a verified database
   backup, and run the routed acceptance suite.
