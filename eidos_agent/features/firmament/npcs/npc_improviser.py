# eidos_agent/features/firmament/npcs/npc_improviser.py
import logging
from typing import Optional, Dict, Any, List
import random # For hardcoded response variation

# Assuming LLMConfig will be imported from a central config location
try:
    # Path relative to this file: firmament/npcs/npc_improviser.py
    # Need to go up to eidos_agent/ then into core/
    from ....core.config import LLMConfig, Config
    # from ....llm_integrations.llm_client import LLMClient # For future use when making actual calls
except ImportError: # Fallback for parsing/testing # pragma: no cover
    print("NPCImproviser: Could not import LLMConfig/Config/LLMClient from ....core.config. Using dummy types.")
    LLMConfig = Dict[str, Any] # type: ignore
    class Config: #type:ignore
        @staticmethod
        def get_firmament_module_config(): return {"firmament_llm_role": "FIRMAMENT_PRIMARY_DUMMY"}
        @staticmethod
        def get_llm_config(role_name):
            if role_name == "FIRMAMENT_PRIMARY_DUMMY":
                return {"role": role_name, "model": "dummy_firmament_model_fallback", "url": "http://dummy"}
            return None
    # class LLMClient: def __init__(self, hc): pass #type:ignore


logger = logging.getLogger(__name__)

class NPCImproviser:
    """
    Handles LLM-based generation of NPCs from scratch or from fuzzy thoughts/contexts.
    Currently, the LLM call is simulated with a hardcoded response.
    """
    def __init__(self, firmament_llm_role_name: Optional[str] = None):
        """
        Initializes the NPCImproviser.

        Args:
            firmament_llm_role_name (Optional[str]): The specific LLM role defined in Config
                                                     to be used for NPC improvisation.
                                                     If None, will try to get default from Firmament config.
        """
        if firmament_llm_role_name:
            self.llm_role_name = firmament_llm_role_name
        else:
            # Ensure Config and its methods are callable (not dummies from ImportError)
            if hasattr(Config, 'get_firmament_module_config') and callable(Config.get_firmament_module_config):
                fm_module_cfg = Config.get_firmament_module_config()
                self.llm_role_name = fm_module_cfg.get("firmament_llm_role", "FIRMAMENT_PRIMARY")
            else: # pragma: no cover
                self.llm_role_name = "FIRMAMENT_PRIMARY_FALLBACK_NO_CONFIG" # Fallback if Config is a dummy

        if hasattr(Config, 'get_llm_config') and callable(Config.get_llm_config):
            self.llm_config: Optional[LLMConfig] = Config.get_llm_config(self.llm_role_name)
        else: # pragma: no cover
            self.llm_config = None # Fallback if Config is a dummy
            logger.error("NPCImproviser: Config.get_llm_config is not available (likely due to import error).")


        if not self.llm_config: # pragma: no cover
            logger.error(f"NPCImproviser: LLM configuration for role '{self.llm_role_name}' not found. "
                         "Improvisation will rely entirely on hardcoded fallbacks or fail if not implemented.")
        else:
            logger.info(f"NPCImproviser initialized to use LLM role '{self.llm_role_name}' "
                        f"with model '{self.llm_config.get('model', 'N/A')}' at URL '{self.llm_config.get('url', 'N/A')}'.")

        # TODO: Initialize an instance of LLMClient with this config and an httpx.AsyncClient
        # self.http_client = httpx.AsyncClient(timeout=self.llm_config.get('timeout', 15.0)) if self.llm_config else None
        # self.llm_client = LLMClient(http_client=self.http_client) if self.http_client else None
        # logger.info(f"NPCImproviser: LLMClient {'initialized' if self.llm_client else 'NOT initialized due to missing config/client'}.")


    def _build_improvisation_prompt(
        self,
        name_hint: Optional[str],
        subconscious_thought_context: Optional[str],
        scene_context: Dict[str, Any]
    ) -> str:
        """
        Constructs a detailed prompt for the LLM to generate an NPC profile.
        """

        location_description = scene_context.get("location_description", "an unspecified place")
        pathos_mood_state = scene_context.get("pathos_mood_state", "neutral")
        current_activity = scene_context.get("current_activity_name", "not currently specified")
        time_of_day = scene_context.get("time_of_day", "not specified")
        recent_world_events_summary = scene_context.get("recent_world_events_summary", "nothing notable recently.")
        pathos_current_intention = scene_context.get("pathos_current_intention", None)

        prompt_lines = [
            "You are an expert character creator for a life simulation. Your task is to generate a plausible and contextually relevant NPC (Non-Player Character) that Pathos (the main character of the simulation) might encounter or think about.",
            "The NPC should feel like a natural part of the current scene and Pathos's internal state.",
            "---",
            "**Current Scene for Pathos:**",
            f"- Location: {location_description}",
            f"- Time: {time_of_day}",
            f"- Pathos's Current Activity: {current_activity}",
            f"- Pathos's Current Mood: {pathos_mood_state}"
        ]
        if pathos_current_intention:
            prompt_lines.append(f"- Pathos's Current Intention/Goal: {pathos_current_intention}")
        prompt_lines.append(f"- Recent World Events Summary: {recent_world_events_summary}")
        prompt_lines.append("---")

        if name_hint:
            prompt_lines.append(f"**NPC to Improvise (Name Hint: {name_hint}):**")
            prompt_lines.append(f"Pathos is thinking about or might encounter someone named or similar to '{name_hint}'.")
        else:
            prompt_lines.append("**NPC to Improvise (No Name Hint):**")
            prompt_lines.append("Pathos might encounter a new, unprompted character relevant to the scene, or a character might be needed to fulfill a role (e.g., shopkeeper at a shop location).")

        if subconscious_thought_context:
            prompt_lines.append(f"Pathos's recent subconscious thought related to this potential NPC: \"{subconscious_thought_context}\"")
            prompt_lines.append("Consider any emotional tone or implied relationship from this thought (e.g., nostalgia, curiosity, anxiety, a problem to solve).")

        prompt_lines.append("---")
        prompt_lines.append("**Generate the NPC Profile - Output ONLY a valid JSON object with these fields:**")
        prompt_lines.append("- id: (string) A unique, lowercase, snake_case ID for this NPC (e.g., 'john_doe_cafe_stranger', 'lara_croft_archaeologist'). If a name_hint is given, try to base the ID on it.")
        prompt_lines.append("- name: (string) The NPC's full name. If a name_hint was given, try to use or adapt it. If not, invent a plausible one.")
        prompt_lines.append("- appearance: (string) A brief, evocative description (e.g., 'tall with bright red hair and glasses', 'wears a worn leather jacket and a thoughtful expression').")
        prompt_lines.append("- role: (string) The NPC's role or reason for being in this scene/location (e.g., 'Barista at the cafe', 'Fellow customer waiting in line', 'Passerby on the street', 'Old acquaintance from university').")
        prompt_lines.append("- personality: (string) A few key personality traits or a brief summary (e.g., 'gruff but fair with a hidden soft spot', 'nervous and fidgety, avoids eye contact', 'cheerful and talkative, seems to know everyone', 'quiet and observant, with an air of mystery').")
        prompt_lines.append("- relationship_to_pathos: (string) Describe their potential or existing connection to Pathos. (e.g., 'Total stranger', 'Former colleague, vaguely remembered from the old office', 'Childhood friend he hasn't seen in years', 'The barista he sees every morning but doesn't know personally'). If a subconscious thought implies a relationship, use that as a strong hint.")
        prompt_lines.append("- initial_dialogue: (string) A single, characteristic opening line of dialogue this NPC might say to Pathos upon appearing or being interacted with, fitting the context, their personality, and their relationship to Pathos.")
        prompt_lines.append("---")
        prompt_lines.append("Example for a name hint 'Lara' and thought 'I miss Lara':")
        prompt_lines.append("{\"id\": \"lara_croft_cafe_memory\", \"name\": \"Lara Croft\", \"appearance\": \"athletic build, wearing practical explorer gear, a thoughtful look in her eyes\", \"role\": \"A memory or figment of imagination, perhaps a past acquaintance\", \"personality\": \"determined, intelligent, adventurous\", \"relationship_to_pathos\": \"Someone Pathos knew and misses, possibly a former partner in adventure or a close friend\", \"initial_dialogue\": \"Pathos... It's been too long. Still chasing shadows?\"}")

        return "\n".join(prompt_lines)

    def improvise_npc(
        self,
        name_hint: Optional[str] = None,
        subconscious_thought_context: Optional[str] = None,
        scene_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generates an NPC profile based on hints and context using an LLM (simulated for now).

        Args:
            name_hint: Optional name for the NPC (e.g., "Lara").
            subconscious_thought_context: Optional thought from SubconsciousNode (e.g., "I miss Lara").
            scene_context: Dictionary describing the current scene (location, Pathos's mood, etc.).

        Returns:
            A dictionary representing the generated NPC profile, or None if generation fails.
        """
        if scene_context is None:
            scene_context = {} # Default to empty context to avoid errors in _build_improvisation_prompt

        if not self.llm_config: # pragma: no cover
            logger.error("NPCImproviser: Cannot improvise NPC, LLM configuration is missing for role '%s'.", self.llm_role_name)
            return None

        prompt = self._build_improvisation_prompt(name_hint, subconscious_thought_context, scene_context)

        logger.info(f"NPCImproviser: SIMULATING LLM call for NPC improvisation. Role: '{self.llm_role_name}', Model: '{self.llm_config.get('model', 'N/A')}'")
        # The full prompt is logged here for review during this simulation phase:
        logger.debug(f"NPCImproviser: Full prompt that WOULD be sent to LLM:\n------PROMPT START------\n{prompt}\n------PROMPT END------")

        logger.warning("NPCImproviser: Using HARDCODED JSON response structure instead of actual LLM call. "
                       "This is for development and testing of the surrounding system. "
                       "TODO: Replace this with an actual async call to self.llm_client.call_llm_api "
                       "and parse its JSON output.")

        # Determine a name and ID for the hardcoded response
        base_name = name_hint if name_hint else "RandomNPC"
        normalized_base_id = base_name.strip().lower().replace(" ", "_")

        # Specific hardcoded example for "Lara" if hint is given, as per user prompt's example for output
        if name_hint and "Lara" in name_hint:
            final_id = f"lara_improvised_{random.randint(100,999)}"
            final_name = f"Lara {random.choice(['Miller', 'Chen', 'Garcia', '(Improvised)'])}"
            return {
                "id": final_id,
                "name": final_name,
                "appearance": "sharp jaw, buzzed sides with a top knot, wearing a faded band t-shirt under a denim jacket (simulated)",
                "role": "Barista at a nearby, slightly grungy but popular coffee spot (simulated)",
                "personality": "brisk and efficient, but with a dry wit and surprisingly kind eyes (simulated)",
                "relationship_to_pathos": "Possibly a classmate from a past art course Pathos vaguely remembers, or just a familiar face from the neighborhood coffee scene (simulated based on 'Lara' hint and common cafe context).",
                "initial_dialogue": f"{random.choice(['Pathos? No way. It has been forever.', 'Double espresso, right? Or are you changing it up today, Pathos?', 'Hey, Pathos. Long time no see. Still drawing those weird robots?'])} (simulated)"
            }

        # General hardcoded response
        final_id = f"{normalized_base_id}_{random.randint(100,999)}"
        final_name = base_name if base_name != "RandomNPC" else f"Generated NPC {random.randint(100, 999)}"

        return {
            "id": final_id,
            "name": final_name,
            "appearance": f"{random.choice(['Tall', 'Short', 'Average height'])} individual with {random.choice(['dark, curly', 'straight blonde', 'vibrant red', 'unusual blue-streaked'])} hair, often seen wearing a {random.choice(['simple t-shirt and jeans', 'tailored business suit', 'brightly colored artistic jacket', 'worn-out comfortable sweater'])}. (simulated)",
            "role": f"{random.choice(['Local Shopkeeper', 'Fellow Passerby', 'Quiet Resident from down the street', 'Inquisitive Tourist', 'Street Artist sketching nearby'])} (simulated)",
            "personality": f"{random.choice(['Cheerful and always outgoing', 'Quiet, observant, and thoughtful', 'A bit gruff on the surface but genuinely helpful', 'Slightly nervous and endearingly shy', 'Wise and enigmatic, speaks in riddles'])} (simulated)",
            "relationship_to_pathos": f"{random.choice(['Complete stranger to Pathos', 'Someone Pathos might recognize vaguely from the neighborhood', 'A new neighbor Pathos hasn\\'t officially met yet', 'Could be a distant relative of an acquaintance Pathos knows'])} (simulated)",
            "initial_dialogue": f"{random.choice(['Oh, hello there.', 'Can I help you with something?', 'Lovely day for it, isn\\'t it?', 'Excuse me, do you have the time?'])} (simulated)"
        }

if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Test with default LLM role (should pick up FIRMAMENT_PRIMARY from dummy Config if .env isn't set)
    improviser = NPCImproviser()

    if not improviser.llm_config or not improviser.llm_config.get("url"): # Check if a URL is actually set
        print("\nCannot run __main__ test for NPCImproviser: LLM config not properly loaded or URL missing. "
              "Ensure .env is set up for the FIRMAMENT_PRIMARY role or that the dummy Config provides a URL.")
    else:
        print(f"\nNPCImproviser using LLM Role: '{improviser.llm_role_name}', "
              f"Model: '{improviser.llm_config.get('model', 'N/A')}', "
              f"URL: '{improviser.llm_config.get('url')}'")

        print("\n--- Test Case 1: Name hint 'Lara' and subconscious context ---")
        scene1 = {
            "location_description": "a bustling downtown cafe called 'The Grind'",
            "pathos_mood_state": "nostalgic and slightly anxious",
            "current_activity_name": "waiting for a friend who is late",
            "time_of_day": "mid-afternoon, rainy",
            "recent_world_events_summary": "Heard a distant siren a few minutes ago, and the power flickered once.",
            "pathos_current_intention": "Hoping to reconnect with an old friend from art school."
        }
        npc1_profile = improviser.improvise_npc(
            name_hint="Lara",
            subconscious_thought_context="I wonder if Lara still works at a cafe like this. It's been years since that art class. She was so passionate.",
            scene_context=scene1
        )
        if npc1_profile:
            print("\nGenerated NPC Profile 1 (Lara hint):")
            for key, value in npc1_profile.items():
                print(f"  - {key}: {value}")
        else:
            print("Failed to generate NPC Profile 1.")

        print("\n--- Test Case 2: No name hint, scene context implies need for a role (e.g., shopkeeper) ---")
        scene2 = {
            "location_description": "a quiet, slightly dusty antique shop",
            "pathos_mood_state": "curious and a bit pensive",
            "current_activity_name": "browsing antiques, looking for something unique",
            "time_of_day": "late morning on a weekday",
            "recent_world_events_summary": "The city is preparing for a local festival next week."
        }
        npc2_profile = improviser.improvise_npc(
            scene_context=scene2
        )
        if npc2_profile:
            print("\nGenerated NPC Profile 2 (No hint, antique shop):")
            for key, value in npc2_profile.items():
                print(f"  - {key}: {value}")
        else:
            print("Failed to generate NPC Profile 2.")

        print("\n--- Test Case 3: Minimal context, just a location ---")
        scene3 = {"location_description": "a generic, busy street corner"}
        npc3_profile = improviser.improvise_npc(scene_context=scene3)
        if npc3_profile:
            print("\nGenerated NPC Profile 3 (Minimal Context - street corner):")
            for key, value in npc3_profile.items():
                print(f"  - {key}: {value}")

        print("\n--- Test Case 4: Name hint 'Bob', thought about needing help ---")
        scene4 = {
            "location_description": "Pathos's cluttered home office",
            "pathos_mood_state": "frustrated",
            "current_activity_name": "trying to fix a broken gadget",
            "time_of_day": "evening",
        }
        npc4_profile = improviser.improvise_npc(
            name_hint="Bob",
            subconscious_thought_context="This gadget is impossible! I wish Bob was here, he's great with electronics.",
            scene_context=scene4
        )
        if npc4_profile:
            print("\nGenerated NPC Profile 4 (Bob hint, gadget help):")
            for key, value in npc4_profile.items():
                print(f"  - {key}: {value}")

    print("\nNPCImproviser __main__ tests completed.")
