# Dell T630 inventory and commissioning record

Last inspected through iDRAC: September 6, 2026.

This file deliberately omits service tags, serial numbers, MAC addresses, login
details, and management-network addresses. It records only deployment-relevant
hardware facts that were visible through iDRAC. No RAID, BIOS, firmware, or boot
configuration was changed during inspection.

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

## Blocking storage condition

iDRAC detects exactly one physical disk and no virtual disks:

- TEAM T2532TB, nominally a 2 TB SATA SSD in backplane slot 2
- Controller state: `Failed`
- Reported usable size: `0.00 GB`
- Reported media power: on, negotiated link: 6 Gbps
- No virtual disk exists

The Ubuntu USB can provide installation media, but it cannot provide a safe durable
installation target. Do not initialize RAID, clear foreign state, or ask an installer
to write to this device merely to see whether it works. First reseat or replace the
SSD, then confirm a nonzero capacity and healthy controller state. A replacement
should be endurance-appropriate and large enough to separate the OS, model cache,
Eidos data, and operational logs.

## Commissioning sequence after healthy storage exists

1. Re-run the iDRAC inventory and export a private machine-readable copy.
2. Verify both power feeds, cooling health, GPU count, and PCIe topology.
3. Create the intended virtual disk explicitly and record its RAID policy.
4. Boot the physical Ubuntu Server USB in UEFI mode.
5. Install the selected Ubuntu Server LTS release with OpenSSH and encrypted secrets.
6. Install and verify the NVIDIA driver before adding a model runtime.
7. Burn in every P40 independently, then together, while monitoring temperature and
   power.
8. Benchmark the Pascal-compatible llama.cpp path before assigning Eidos roles.
9. Deploy Eidos behind the private network boundary, restore a verified database
   backup, and run the routed acceptance suite.
