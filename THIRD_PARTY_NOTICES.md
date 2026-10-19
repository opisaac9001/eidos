# Third-Party Notices

Eidos has no third-party runtime dependencies: the engine uses only the Python standard library, and the web interface is plain HTML, CSS and JavaScript shipped inside the package, with no CDN, framework or external font. This file lists the data it redistributes and the services it can connect to.

Redistributions must retain these notices and comply with each license. The Eidos license does not replace them.

## Data redistributed with Eidos

### OpenStreetMap (Frome, Somerset)

- **Files:** `src/eidos/application/frome_v1.json`, built by `tools/build_real_town.py`.
- **What it is:** street geometry, place positions and walking distances in Frome, used to lay out the fictional town of Alderwick.
- **License:** © OpenStreetMap contributors, available under the [Open Database Licence (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/). See <https://www.openstreetmap.org/copyright>.
- **Requirements:** keep this attribution. A database derived from this data that you distribute publicly must be offered under the ODbL.

## Services Eidos can connect to (opt-in, not redistributed)

These are only contacted when you turn them on. Their content is not part of this repository.

| Service | Used for | Terms |
| --- | --- | --- |
| [Open-Meteo](https://open-meteo.com/) | Current weather and daylight for a chosen town | Data under [CC BY 4.0](https://open-meteo.com/en/license); attribution required where shown |
| [BBC News RSS](https://www.bbc.co.uk/news/10628494) | Headlines he reads and forms views on | BBC terms of use; headlines are read live and not redistributed |
| Any RSS feed you configure | A local news feed | The publisher's terms |
| Model providers you configure (Ollama, LM Studio, vLLM, OpenRouter, OpenAI, Anthropic, Gemini, Groq, Mistral, DeepSeek, Together, or any OpenAI-compatible server) | Language for his thoughts, speech and the world | Each provider's and each model's own license and terms |

## Development tools

Installed only with the `dev` extra, and not redistributed:

| Package | License |
| --- | --- |
| [pytest](https://github.com/pytest-dev/pytest) | MIT |
| [mypy](https://github.com/python/mypy) | MIT |
| [ruff](https://github.com/astral-sh/ruff) | MIT |
| [hatchling](https://github.com/pypa/hatch) (build backend) | MIT |
