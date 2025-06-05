# eidos_agent/modules/oneiros_module.py

from __future__ import annotations

import asyncio

from datetime import datetime
import logging
import random
import re
import pathlib
import httpx
import base64
import json # Added for payload construction if LLM params are in config
from typing import Optional, List, Dict, Any, Sequence # Sequence not used, can remove

from eidos_agent.core.config import Config, OneirosConfig, LLMConfig
# EthosCore imports are already updated to persona_logic in this file
from eidos_agent.persona_logic.ethos_core.core import EthosCore
from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryEntry
from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

WILDCARD_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

class OneirosModule:
    def __init__(self, config: Config, ethos_core: EthosCore):
        self.config = config
        self.oneiros_config: OneirosConfig = config.get_oneiros_config()
        self.ethos_core = ethos_core

        dream_llm_role_str = self.oneiros_config.get('dream_llm_role', 'PATHOS')
        # Ensure dream_llm_role_str is a valid Literal for get_llm_config if it expects strict literals
        # For now, assuming get_llm_config can handle string roles if they match keys in Config.LLM
        self.dream_llm_config: Optional[LLMConfig] = config.get_llm_config(dream_llm_role_str) # type: ignore

        if not self.dream_llm_config:
            logger.error(f"OneirosModule: LLM for role '{dream_llm_role_str}' not configured. Dreaming will be impaired.")

        self.http_client: Optional[httpx.AsyncClient] = None
        if self.dream_llm_config and self.dream_llm_config.get('url'):
            timeout_cfg = self.dream_llm_config.get('timeout', 120) # Default to 120 if not in config
            try: timeout_val = float(timeout_cfg)
            except (ValueError, TypeError): timeout_val = 120.0
            self.http_client = httpx.AsyncClient(timeout=timeout_val)

        self.sd_client = None # Placeholder, actual client for SD would be more complex
        if self.config.ENABLE_ONEIROS and self.oneiros_config.get('stable_diffusion_url') and self.oneiros_config.get('enable_image_dreams'):
            logger.info("OneirosModule: Stable Diffusion URL configured and image dreams enabled.")
        elif self.config.ENABLE_ONEIROS and self.oneiros_config.get('enable_image_dreams') and not self.oneiros_config.get('stable_diffusion_url'):
            logger.warning("OneirosModule: Image dreams enabled but Stable Diffusion URL is NOT configured. Image generation will fail.")


        logger.info("OneirosModule initialized.")

    def _expand_wildcards(self, text: str) -> str:
        wildcard_base_dir_str = self.oneiros_config.get('wildcard_files_dir')
        if not wildcard_base_dir_str:
            logger.warning("Wildcard directory not configured in ONEIROS settings. Wildcard expansion will not work.")
            return text # Return original text if dir not set

        wildcard_base_path = pathlib.Path(wildcard_base_dir_str) # Use configured path

        def repl(match):
            key = match.group(1)
            # Use the WILDCARDS_DIR from Config class which is already a Path object
            path = wildcard_base_path / f"{key}.txt" # Corrected to use wildcard_base_path
            if not path.exists():
                logger.warning(f"Wildcard file not found: {path}")
                return f"{{{{{key}}}}}" # Return placeholder if file not found
            try:
                choices = [ln.strip() for ln in path.read_text(encoding='utf-8').splitlines() if ln.strip()]
                return random.choice(choices) if choices else f"{{{{{key}}}}}" # Return placeholder if file empty
            except Exception as e:
                logger.error(f"Error reading wildcard file {path}: {e}")
                return f"{{{{{key}}}}}" # Return placeholder on error
        return WILDCARD_RE.sub(repl, text)

    async def _call_dream_llm(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        if not self.dream_llm_config or not self.dream_llm_config.get('url') or not self.http_client:
            logger.error("Dream LLM call: URL or HTTP client not configured.")
            return None

        api_url = f"{self.dream_llm_config['url']}/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = self.dream_llm_config.get('api_key')
        if api_key and api_key.lower() not in ['lm-studio', 'ollama', '']:
            headers["Authorization"] = f"Bearer {api_key}"

        # Get LLM parameters from OneirosConfig first, then from dream_llm_config, then defaults
        # This allows specific overrides for the dream LLM in OneirosConfig if desired
        temp = self.oneiros_config.get('dream_llm_temperature', self.dream_llm_config.get('temperature', 1.3))
        top_p_val = self.oneiros_config.get('dream_llm_top_p', self.dream_llm_config.get('top_p', 0.95))
        pres_pen = self.oneiros_config.get('dream_llm_presence_penalty', self.dream_llm_config.get('presence_penalty', 0.8))
        freq_pen = self.oneiros_config.get('dream_llm_frequency_penalty', self.dream_llm_config.get('frequency_penalty', 0.2))
        max_tok = self.oneiros_config.get('dream_llm_max_tokens', self.dream_llm_config.get('max_tokens', 1024))


        payload: Dict[str, Any] = {
            "model": self.dream_llm_config.get('model'), # Model name comes from the role's config
            "messages": messages,
            "temperature": float(temp),
            "max_tokens": int(max_tok)
        }
        # Add optional parameters if they are not None
        if top_p_val is not None: payload["top_p"] = float(top_p_val)
        if pres_pen is not None: payload["presence_penalty"] = float(pres_pen)
        if freq_pen is not None: payload["frequency_penalty"] = float(freq_pen)


        if not payload.get('model'): # Should always have a model from dream_llm_config
            logger.warning("Dream LLM model name is missing from config. Attempting call without model specified.")
            del payload['model'] # Remove if empty, some servers might infer

        try:
            logger.debug(f"Calling Dream LLM: {api_url}, Model: {payload.get('model', 'Server Default')}, Payload: {json.dumps(payload, indent=2)}")
            response = await self.http_client.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            # Robust parsing of response
            if choices := result.get("choices"):
                if choices and isinstance(choices, list) and len(choices) > 0:
                    if message := choices[0].get("message"):
                        if isinstance(message, dict) and (content := message.get("content")):
                            return str(content).strip()
            logger.warning(f"Dream LLM response missing content: {result}")
            return None
        except Exception as e:
            logger.error(f"Error calling Dream LLM: {e}", exc_info=True)
            return None

    async def _generate_dream_image(self, prompt: str) -> Optional[pathlib.Path]:
        sd_url = self.oneiros_config.get('stable_diffusion_url')
        # Also check if image dreams are enabled globally and if http_client is available
        if not sd_url or not self.oneiros_config.get('enable_image_dreams') or not self.http_client:
            if not self.oneiros_config.get('enable_image_dreams'):
                logger.debug("Image dream generation skipped: enable_image_dreams is false.")
            elif not sd_url:
                logger.debug("Image dream generation skipped: Stable Diffusion URL not configured.")
            return None

        image_output_dir_str = self.oneiros_config.get('image_output_dir')
        if not image_output_dir_str:
            logger.error("Cannot generate dream image: ONEIROS_IMAGE_OUTPUT_DIR not configured.")
            return None
        
        image_dir = pathlib.Path(image_output_dir_str) # Use configured path

        try:
            # Ensure the directory exists (Config.setup should handle this, but good to double-check)
            image_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Requesting dream image from Stable Diffusion: {sd_url} with prompt: '{prompt[:100]}...'")
            # Example payload, adjust according to your SD API
            sd_payload = {
                "prompt": prompt,
                "steps": 30,
                "cfg_scale": 7.0,
                "width": 512,
                "height": 512,
                # Add other parameters your SD API supports/requires
            }
            response = await self.http_client.post(
                f"{sd_url.rstrip('/')}/sdapi/v1/txt2img", # Common endpoint for Auto1111
                json=sd_payload,
                timeout=120.0 # Potentially longer timeout for image generation
            )
            response.raise_for_status()
            result = response.json()
            if result.get("images") and isinstance(result["images"], list) and result["images"]:
                # Assuming the first image is the one we want and it's base64 encoded
                image_data_b64 = result["images"][0]
                # Some APIs might include "data:image/png;base64," prefix, remove if present
                if "," in image_data_b64:
                    image_data_b64 = image_data_b64.split(',', 1)[1]
                
                image_data = base64.b64decode(image_data_b64)
                
                # Generate a unique filename
                timestamp_filename_part = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                image_path = image_dir / f"dream_{timestamp_filename_part}.png"
                
                image_path.write_bytes(image_data)
                logger.info(f"Dream image saved to {image_path}")
                return image_path
            else:
                logger.warning(f"Stable Diffusion response did not contain images or in unexpected format: {result}")
        except httpx.TimeoutException as e_timeout:
            logger.error(f"Timeout generating dream image: {e_timeout}")
        except httpx.RequestError as e_req:
            logger.error(f"Network error generating dream image: {e_req}")
        except Exception as e:
            logger.error(f"Error generating dream image: {e}", exc_info=True)
        return None

    async def run_dream_cycle(self):
        if not self.config.ENABLE_ONEIROS or not self.config.ENABLE_CURIOUSITY:
            logger.debug("Dream cycle skipped: Oneiros or Curiosity disabled in config.")
            return
        if not self.dream_llm_config or not self.http_client:
            logger.warning("Dream cycle skipped: Dream LLM or its HTTP client not configured.")
            return
        if not self.ethos_core:
             logger.error("Dream cycle skipped: EthosCore not initialized.")
             return

        logger.info("--- Oneiros: Starting Dream Cycle ---")
        dream_output = None
        try:
            num_source_memories = self.oneiros_config.get('dream_num_source_memories', 3)
            min_salience_source = self.oneiros_config.get('dream_min_salience_for_source', 0.0)

            # Use a broad query to get diverse memories
            candidate_memories: List[MemoryEntry] = await self.ethos_core.retrieve_relevant_memories(
                query="abstract concepts, recent events, user interests, learned facts, unresolved questions, emotions, sensory details", # Broader query
                top_k=num_source_memories * 6, # Fetch more to sample from
                min_salience=min_salience_source,
                allowed_types=['interaction', 'world_knowledge', 'document_chunk', 'context_summary', 'feedback', 'user_fact', 'proactive_action_record', 'queued_discussion_point'] # Include queued_discussion_point as potential seed
            )

            if not candidate_memories or len(candidate_memories) < min(2, num_source_memories):
                logger.info("Oneiros: Not enough diverse/salient memories to seed a meaningful dream.")
                if self.ethos_core.config.ENABLE_PROACTIVE_BEHAVIOR:
                    logger.debug("Dream cycle finished (no seeds), triggering proactive check via EthosCore.")

                    asyncio.create_task(self.ethos_core.run_proactive_check("OneirosDreamCycleNoSeeds"), name="ProactiveCheckAfterOneirosNoSeeds")
                return

            # Weight memories by salience for selection
            # Ensure salience is a float, default to 0.1 if None or invalid
            weights = []
            for m in candidate_memories:
                s = m.get('salience')
                try:
                    weight = float(s if s is not None else 0.1) + 0.1 # Add small base weight
                    weights.append(max(0.01, weight)) # Ensure weight is positive
                except (ValueError, TypeError):
                    weights.append(0.1) # Default low weight for invalid salience

            if not any(w > 0 for w in weights): # If all weights are zero (e.g. all salience was None/invalid)
                logger.warning("All candidate memories for dream have zero or invalid salience. Selecting unweighted.")
                selected_seeds = random.sample(candidate_memories, min(len(candidate_memories), num_source_memories))
            else:
                selected_seeds = random.choices(candidate_memories, weights=weights, k=min(len(candidate_memories), num_source_memories))


            dream_seed_content_parts = []
            for m_idx, m in enumerate(selected_seeds):
                type_label = m.get('type', 'memory').replace('_', ' ').title()
                user_ctx = f" (User: {m.get('metadata',{}).get('user_id','unknown')})" if m.get('metadata',{}).get('user_id') not in [None, "unknown_user", "system_oneiros", "system_document", "system_briefing", "system_reflection", "world_knowledge_store"] else ""
                salience_for_formatting = m.get('salience') if m.get('salience') is not None else 0.0
                dream_seed_content_parts.append(
                    f"Seed {m_idx+1} (Type: {type_label}{user_ctx}, Salience: {salience_for_formatting:.2f}):\n{m.get('content','')[:300]}..."
                )
            dream_seed_content = "\n\n---\n\n".join(dream_seed_content_parts)

            # Use wildcard expansion for system prompt
            dream_system_prompt_template = (
                "You are Pathos, in a dreamlike, reflective, and creative state of mind. Your thoughts are fluid, associative, and insightful. "
                "Consider the following pieces of information, memories, and concepts that have surfaced from your experiences. "
                "Synthesize them into ONE of the following: "
                "1. A novel insight or surprising connection between these concepts. "
                "2. An interesting, open-ended question that these memories provoke, perhaps something to explore further or discuss with a user. "
                "3. A very short, evocative, creative piece (a few lines of poetry, a tiny story fragment, a metaphor, a {{dream_theme_concept}}) inspired by these seeds. "
                "The output should be concise (1-3 sentences typically) and intriguing. "
                "Frame your output naturally, as if it's a thought that just surfaced. Do not explicitly say you are dreaming. "
                "Avoid generic statements; aim for specificity and novelty based on the provided seeds. Your current creative focus is on {{creative_focus_element}}."
            )
            dream_system_prompt = self._expand_wildcards(dream_system_prompt_template)


            # Use wildcard expansion for user prompt template
            dream_user_prompt_template = (
                "Seeds for reflection:\n\n{dream_seed_content}\n\n"
                "Reflect on these seeds, perhaps considering {{abstract_concept}} or {{emotional_tone}}. "
                "Your emergent thought/question/creation (keep it brief and intriguing, like a fleeting dream fragment):"
            )
            # Interpolate dream_seed_content first, then expand wildcards
            formatted_user_prompt = dream_user_prompt_template.format(dream_seed_content=dream_seed_content)
            final_user_prompt = self._expand_wildcards(formatted_user_prompt)


            dream_prompt_messages = [
                {"role": "system", "content": dream_system_prompt},
                {"role": "user", "content": final_user_prompt}
            ]

            dream_output = await self._call_dream_llm(dream_prompt_messages)
            image_path: Optional[pathlib.Path] = None # Ensure type hint

            if dream_output and self.oneiros_config.get('enable_image_dreams'):
                # Generate a more specific image prompt from the dream output if needed
                image_generation_prompt = f"A dreamlike visualization of: {dream_output[:200]}" # Example
                image_path = await self._generate_dream_image(image_generation_prompt)

            if dream_output and self.ethos_core:
                logger.info(f"Oneiros: Dream output generated: {dream_output[:150]}...")
                source_memory_ids = [m.get('id') for m in selected_seeds if m.get('id')]

                user_id_counts: Dict[str, int] = {}
                for m in selected_seeds:
                    uid = m.get('metadata',{}).get('user_id', 'system_oneiros')
                    if uid not in ["system_document", "system_briefing", "world_knowledge_store", "unknown_user", "system_oneiros", "system_reflection", None]:
                        user_id_counts[uid] = user_id_counts.get(uid, 0) + 1

                target_user_id_for_queued_point = "system_oneiros"
                if user_id_counts:
                    max_user = max(user_id_counts, key=user_id_counts.get)
                    if user_id_counts[max_user] >= len(selected_seeds) / 2 and len(user_id_counts) == 1 :
                         target_user_id_for_queued_point = max_user
                    else:
                         logger.debug(f"Dream seeds from mixed users ({user_id_counts}), assigning queued point to system_oneiros.")

                dream_metadata: Dict[str, Any] = { # Define dream_metadata type
                    "user_id": target_user_id_for_queued_point,
                    "source": "oneiros_dream_cycle",
                    "reason_for_queueing": "Generated during dream/reflection based on memory synthesis.",
                    "dream_seed_memory_ids": source_memory_ids,
                    "dream_seed_summary": dream_seed_content[:200] + "...",
                    "status": "pending"
                }
                if image_path:
                    dream_metadata["dream_image_path"] = str(image_path.resolve()) # Store absolute path

                await self.ethos_core.add_memory_entry(
                    entry_data={
                        "type": "queued_discussion_point",
                        "content": dream_output,
                        "metadata": dream_metadata,
                        "salience": random.uniform(0.6, 0.85)
                    },
                    user_id_context=target_user_id_for_queued_point
                )
                logger.info(f"Oneiros: Dream output stored as queued discussion point for user '{target_user_id_for_queued_point}'. Image: {image_path}")
            elif dream_output:
                 logger.error("Oneiros: Dream output generated but EthosCore is not available to store it.")
            else:
                logger.warning("Oneiros: Dream LLM did not produce any output.")

            if self.ethos_core and self.ethos_core.config.ENABLE_PROACTIVE_BEHAVIOR:
                logger.debug("Dream cycle finished, triggering proactive check via EthosCore.")
                # Add the call to trigger_proactive_check_after_event
                asyncio.create_task(self.ethos_core.trigger_proactive_check_after_event("OneirosDreamCycle"), name="ProactiveCheckAfterOneiros")


        except Exception as e:
            logger.error(f"Oneiros: Error during dream cycle: {e}", exc_info=True)
        finally:
            logger.info("--- Oneiros: Dream Cycle Finished ---")

    async def close(self):
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
        # sd_client is not fully implemented, so no close needed yet
        logger.info("OneirosModule resources closed.")