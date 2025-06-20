import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union

# Attempt to import Config for type hinting, define a dummy if import fails
try:
    # Assuming Config is in core.config relative to this file's eventual location
    from ...core.config import Config, EthosConfig
except ImportError:
    # Define a minimal dummy Config for type hinting if standalone or import issues
    class Config: # type: ignore
        pass
    class EthosConfig(Dict[str, Any]): # type: ignore
        pass

logger = logging.getLogger(__name__)

# Define a default path for traits file, can be overridden by config
DEFAULT_TRAITS_FILENAME = "pathos_traits.json"
# This path would ideally be relative to a known config directory,
# e.g., PROJECT_ROOT / "persona" / DEFAULT_TRAITS_FILENAME
# For now, the engine will expect a full path or load from data.

class TraitsEngine:
    def __init__(self, config: Optional[Config] = None, traits_file_path: Optional[Union[str, Path]] = None):
        """
        Initializes the TraitsEngine.

        Args:
            config (Optional[Config]): The main Eidos agent configuration object.
                                       Can be used to find default traits file path.
            traits_file_path (Optional[Union[str, Path]]): Specific path to a traits JSON file.
                                                           If provided, overrides any path from config.
        """
        self.config = config
        self._traits: Dict[str, Any] = {}

        path_to_load_str: Optional[str] = None

        if traits_file_path:
            path_to_load_str = str(traits_file_path)
            logger.info(f"TraitsEngine: Using explicit traits_file_path: {path_to_load_str}")
        elif self.config:
            # Assuming self.config.ETHOS is the EthosConfig dict
            ethos_config_dict = getattr(self.config, 'ETHOS', None)
            if isinstance(ethos_config_dict, dict):
                path_to_load_str = ethos_config_dict.get('persona_traits_file_path')
                if path_to_load_str:
                    logger.info(f"TraitsEngine: Using traits_file_path from config.ETHOS: {path_to_load_str}")
                else:
                    logger.info("TraitsEngine: 'persona_traits_file_path' not found in config.ETHOS. No default traits file will be loaded by path.")
            else:
                logger.warning("TraitsEngine: Config object provided, but config.ETHOS is not a dictionary or not found. Cannot determine default traits file path.")
        else:
            logger.info("TraitsEngine: No config and no explicit traits_file_path provided. Traits will be empty unless loaded manually.")

        if path_to_load_str:
            final_path_to_load = Path(path_to_load_str)
            if self.load_traits_from_file(final_path_to_load):
                logger.info(f"TraitsEngine successfully loaded traits from: {final_path_to_load}")
            else:
                logger.warning(f"TraitsEngine: Failed to load traits from {final_path_to_load}. Traits might be empty or from a prior state if any.")
        else:
            logger.info("TraitsEngine: No traits file path resolved. Initializing with empty traits.")
            self._traits = {}

        # The load_traits_from_file method already logs success/failure and count.

    def load_traits_from_data(self, traits_data: Dict[str, Any]):
        """
        Loads traits from a dictionary. Overwrites any existing traits.
        """
        if not isinstance(traits_data, dict):
            logger.error("Failed to load traits: data is not a dictionary.")
            return

        self._traits = traits_data.copy() # Make a copy
        logger.info(f"Traits loaded from data. {len(self._traits)} traits now set.")

    def load_traits_from_file(self, file_path: Union[str, Path]) -> bool:
        """
        Loads traits from a JSON file. Overwrites any existing traits.

        Args:
            file_path: Path to the JSON file containing traits.

        Returns:
            True if loading was successful, False otherwise.
        """
        try:
            traits_path = Path(file_path)
            if not traits_path.is_file():
                logger.error(f"Traits file not found: {file_path}")
                return False

            with open(traits_path, 'r', encoding='utf-8') as f:
                traits_data = json.load(f)

            if not isinstance(traits_data, dict):
                logger.error(f"Traits file content is not a dictionary: {file_path}")
                self._traits = {} # Clear existing if file is invalid
                return False

            self.load_traits_from_data(traits_data) # Use the data loading method
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from traits file {file_path}: {e}")
            self._traits = {}
            return False
        except Exception as e:
            logger.error(f"Failed to load traits from file {file_path}: {e}", exc_info=True)
            self._traits = {}
            return False

    def get_trait(self, trait_name: str) -> Optional[Any]:
        """
        Retrieves the value of a specific trait.

        Args:
            trait_name: The name of the trait to retrieve.

        Returns:
            The value of the trait, or None if the trait is not found.
        """
        return self._traits.get(trait_name)

    def get_all_traits(self) -> Dict[str, Any]:
        """
        Retrieves all current traits as a dictionary.

        Returns:
            A copy of the internal traits dictionary.
        """
        return self._traits.copy()

    def set_trait(self, trait_name: str, value: Any):
        """
        Sets or updates a specific trait.
        (Future: Could have more validation or eventing here)
        """
        logger.info(f"Setting trait '{trait_name}' to '{value}'.")
        self._traits[trait_name] = value
        # Consider saving to file if persistence is desired after programmatic changes.
        # For now, changes are in-memory.

    def get_descriptive_trait_summary(self) -> str:
        """
        Generates a human-readable summary of key personality traits for LLM prompts.
        """
        if not self._traits:
            return "Pathos has a generally adaptive personality profile." # Default if no traits loaded

        descriptions = []

        # Define mappings for numeric traits (e.g., Big Five on a 0-1 scale)
        # These trait names should match keys in the loaded traits data.
        numeric_trait_definitions = {
            "openness": {
                "name": "Openness",
                "bands": [(0.3, "Low (Practical, prefers routine)"), (0.7, "Moderate"), (1.0, "High (Imaginative, curious, open to new experiences)")],
                "elaboration": " (Tendency to be creative and open to new ideas vs. conventional and preferring routine)"
            },
            "conscientiousness": {
                "name": "Conscientiousness",
                "bands": [(0.3, "Low (Spontaneous, can be disorganized)"), (0.7, "Moderate"), (1.0, "High (Organized, dependable, self-disciplined)")],
                "elaboration": " (Tendency to be organized and dependable vs. easy-going and spontaneous)"
            },
            "extraversion": {
                "name": "Extraversion",
                "bands": [(0.3, "Low (Introverted, prefers solitude or small groups)"), (0.7, "Moderate"), (1.0, "High (Extraverted, outgoing, enjoys social interaction)")],
                "elaboration": " (Tendency to be outgoing and sociable vs. reserved and preferring solitude)"
            },
            "agreeableness": {
                "name": "Agreeableness",
                "bands": [(0.3, "Low (Competitive, can be challenging)"), (0.7, "Moderate"), (1.0, "High (Cooperative, empathetic, kind)")],
                "elaboration": " (Tendency to be compassionate and cooperative vs. analytical and detached)"
            },
            "neuroticism": { # Often framed as Emotional Stability (inverse of Neuroticism)
                "name": "Emotional Stability (low Neuroticism)",
                "bands": [(0.3, "Low (Prone to stress, experiences mood swings - High Neuroticism)"), (0.7, "Moderate"), (1.0, "High (Calm, emotionally stable, resilient - Low Neuroticism)")],
                "elaboration": " (Tendency to be calm and emotionally stable vs. prone to stress and negative emotions)"
            }
        }

        # Process numeric traits
        for trait_key, definition in numeric_trait_definitions.items():
            if trait_key in self._traits:
                value = self._traits[trait_key]
                if isinstance(value, (int, float)):
                    desc = ""
                    for threshold, band_desc in definition["bands"]:
                        if value <= threshold:
                            desc = f"{definition['name']}: {band_desc}"
                            break
                    if desc: # Add elaboration if you want, or keep it concise
                        # desc += definition.get("elaboration","")
                        descriptions.append(desc)
                else:
                    logger.warning(f"Trait '{trait_key}' expected numeric, got {type(value)}. Skipping for summary.")

        # Process categorical traits (example)
        categorical_traits = {
            "verbosity_preference": "Verbosity Preference",
            "humor_style": "Humor Style",
            "primary_motivation": "Primary Motivation"
            # Add other known categorical traits here
        }
        for trait_key, display_name in categorical_traits.items():
            if trait_key in self._traits:
                value = self._traits[trait_key]
                if isinstance(value, str):
                    descriptions.append(f"{display_name}: {value.capitalize()}")
                # Can add handling for other types if needed

        if not descriptions:
            return "Pathos has a generally adaptive personality profile." # Fallback if no processable traits found

        summary_prefix = "Pathos's key personality characteristics include: "
        return summary_prefix + "; ".join(descriptions) + "."

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger_main = logging.getLogger(__name__ + ".__main__")
    logger_main.info("--- Testing TraitsEngine ---")

    # Test 1: Initialize without a file (should be empty or have defaults if we add them)
    engine1 = TraitsEngine()
    logger_main.info(f"Engine 1 (no file) traits: {engine1.get_all_traits()}")
    assert not engine1.get_all_traits(), "Engine initialized without file should be empty."

    # Test 2: Load from data
    sample_traits_data = {
        "openness": 0.75,
        "conscientiousness": 0.8,
        "extraversion": 0.6,
        "agreeableness": 0.7,
        "neuroticism": 0.3,
        "curiosity_level": "high",
        "verbosity_preference": "moderate"
    }
    engine1.load_traits_from_data(sample_traits_data)
    logger_main.info(f"Engine 1 (after load_traits_from_data) traits: {engine1.get_all_traits()}")
    assert engine1.get_trait("openness") == 0.75
    assert engine1.get_trait("curiosity_level") == "high"
    assert engine1.get_trait("non_existent_trait") is None

    # Test 3: Load from an explicitly provided dummy file path
    explicit_dummy_file_path = Path("./temp_explicit_traits.json")
    explicit_dummy_content = {
        "openness": 0.6,
        "verbosity_preference": "concise",
        "primary_motivation": "knowledge_seeking"
    }
    with open(explicit_dummy_file_path, 'w', encoding='utf-8') as f:
        json.dump(explicit_dummy_content, f, indent=2)

    engine2 = TraitsEngine(traits_file_path=explicit_dummy_file_path)
    logger_main.info(f"Engine 2 (from explicit file path) traits: {engine2.get_all_traits()}")
    assert engine2.get_trait("openness") == 0.6
    assert engine2.get_trait("primary_motivation") == "knowledge_seeking"
    assert engine2.get_trait("conscientiousness") is None

    engine2.set_trait("conscientiousness", 0.9)
    assert engine2.get_trait("conscientiousness") == 0.9
    logger_main.info(f"Engine 2 (after set_trait) traits: {engine2.get_all_traits()}")

    if explicit_dummy_file_path.exists():
        explicit_dummy_file_path.unlink()

    # Test 4: Load from config default path
    class MockConfig:
        PROJECT_ROOT = Path(".")
        ETHOS: EthosConfig = { # type: ignore
            "persona_traits_file_path": str(PROJECT_ROOT / "persona" / "test_default_traits.json")
        }

    default_traits_file_full_path = Path(MockConfig.ETHOS["persona_traits_file_path"])
    default_traits_dir = default_traits_file_full_path.parent
    default_traits_dir.mkdir(parents=True, exist_ok=True)
    default_traits_content = {"default_trait": "from_config_default_path", "openness": 0.55}
    with open(default_traits_file_full_path, 'w', encoding='utf-8') as f:
        json.dump(default_traits_content, f)

    engine_from_config = TraitsEngine(config=MockConfig()) # type: ignore
    logger_main.info(f"Engine from Config traits: {engine_from_config.get_all_traits()}")
    assert engine_from_config.get_trait("default_trait") == "from_config_default_path"
    assert engine_from_config.get_trait("openness") == 0.55

    if default_traits_file_full_path.exists():
        default_traits_file_full_path.unlink()
    if default_traits_dir.exists() and not any(default_traits_dir.iterdir()):
        try: # Attempt to remove, but don't fail test if it has other hidden files etc.
            default_traits_dir.rmdir()
        except OSError:
            logger_main.warning(f"Could not remove temp persona dir {default_traits_dir}, it might not be empty.")

    logger_main.info("TraitsEngine basic tests passed.")
