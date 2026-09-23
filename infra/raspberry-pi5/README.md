# Pi 5 Murmur worker — commissioning incomplete

The 8GB Pi `pathos-murmur` has Raspberry Pi OS Lite 64-bit (Trixie),
Tailscale, Ollama 0.33.3, and the downloaded `qwen2.5:1.5b` model.
Its Tailscale address is 100.70.223.24. SSH uses keys; do not store private
keys or login passwords in this repository.

Ollama binds only to 127.0.0.1:11434. The Dell's enabled
`eidos-murmur-tunnel.service` exposes it locally at 127.0.0.1:11437 over
SSH and Tailscale. Its dedicated key is restricted on the Pi to forwarding
to 127.0.0.1:11434, with no shell or other forwarding destinations.
The Pi host key was obtained through the already trusted Mac SSH connection.

`ollama-override.conf` is installed as an Ollama systemd override on the Pi.
It limits concurrency to one, retains the model, and requests a 4096-token
context. MemoryHigh/MemoryMax depend on the Pi kernel's memory controller;
enforcement has not been verified.

## Test status, 2026-09-07

- Tailscale connectivity and Mac public-key SSH passed.
- Dell tunnel returned Ollama version 0.33.3.
- Ollama model pull completed, including checksum verification.
- The first durable-queue test did NOT pass. The Pi became unreachable on
  both LAN and Tailscale. Power, cooling, kernel logs, and network state
  require inspection after it returns; the cause is not yet known.
- Waiting for inference also exposed unclosed SQLite job connections on
  the Dell. Explicit transaction cleanup fixes the leak. 24 queue tests
  plus four subtests pass on both Mac and Dell, including close-on-error.
- The live Murmur route remains the Dell RTX 3060 / qwen2.5:7b. No live
  simulation state was advanced by this commissioning test.

## Resume

### September 8 bounded endurance follow-up

The Pi completed 35 sequential generations / 2,344 output tokens in 245.3 seconds
using qwen2.5:1.5b, two CPU threads, a 2,048-token context and an 80-token output cap.
Decode speed was approximately 12.7–13.2 tokens/second. Temperature peaked at
63.1 C. Power/throttle flags remained 0x0, Ollama recorded zero service restarts,
swap stayed unused, and the checked kernel log had no power, OOM or storage errors.
The Dell tunnel responded before and after load. The model was unloaded afterward;
temperature subsequently fell to 53.8 C and available memory returned to 7.6 GiB.

`endurance_probe.py` reproduces this bounded test with two-second health checks and
a conservative 75 C / nonzero-power-flag stop. It reserves the final minute of its
five-minute budget for a pending request. This was not an overnight burn-in, a
full-context test, or the actual durable Murmur-queue acceptance test. The physical
power supply has not been independently confirmed changed.

The simple load prompts often produced repetition, role confusion and unsupported
details; many outputs reached the deliberately small token cap. These were not the
full Eidos thought/dream prompts, so they do not establish final role suitability.
Next evaluate role-specific prompts and candidate models separately: waking thoughts
against supplied subjective context, dreams with clearly marked fictional freedom.
No live model route or saved-world state was changed.

Update after reboot: model blob survived but registration was incomplete;
re-running pull and sync restored the model. A short 24-token generation
completed in 15.45 seconds including 12.55 seconds cold load, approximately
13.3 output tokens/second using two CPU threads. Under the subsequent queue
test, the kernel logged undervoltage twice and get_throttled changed from
0x0 to 0x50000. Ollama was stopped to remove load; Tailscale remains active.
Resolve the power supply/cable issue before restarting inference. No live
route change has been made. Previous boot logs were unavailable.

First inspect Pi uptime, previous-boot logs, undervoltage/throttle flags,
temperature, RAM, and Ollama logs. Test one short inference directly before
running `PYTHONPATH=src .venv/bin/python /home/isaac/smoke_murmur.py` from
`/srv/eidos` on the Dell. This uses a temporary database and actual Murmur
contracts, with no changes to Pathos's saved world. Review prose as well as
contract results, latency, and thermals. Test a sustained load and reboot.

Only after those checks should `/etc/eidos/model-routes.json` change Murmur
to `http://127.0.0.1:11437/v1`, model `qwen2.5:1.5b`. Preserve the old routing
file for rollback. This is not an automatic fallback: failed inference is
reported by the queue, not silently replaced. The Dell remains the sole
owner of simulation time, memory, world state, and scheduling; the Pi
generates bounded thoughts from supplied subjective context.
