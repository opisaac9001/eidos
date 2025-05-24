# eidos_agent/core/config.py
import os
from typing import Dict, Any, TypedDict, Optional, List, Literal # Literal is used
from pathlib import Path
from dotenv import load_dotenv
import json # <--- IMPORT ADDED HERE

# Define PROJECT_ROOT relative to this file's location
# eidos_agent/core/config.py -> eidos_agent/core -> eidos_agent -> eidos_project
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env file located at PROJECT_ROOT
dotenv_path = PROJECT_ROOT / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path, override=True)
    # print(f"Loaded .env file from: {dotenv_path}") # Keep print for debugging if needed
else:
    print(f".env file not found at {dotenv_path}. Using environment variables or defaults.")

# --- TypedDicts for Configuration Sections ---

class LLMConfig(TypedDict, total=False):
    url: str
    model: Optional[str]
    api_key: Optional[str]
    temperature: Optional[float]
    timeout: Optional[float] # Added timeout
    max_tokens: Optional[int] # Added max_tokens
    # Optional advanced params
    top_p: Optional[float]
    presence_penalty: Optional[float]
    frequency_penalty: Optional[float]
    max_tool_iterations: Optional[int] # For Pathos LLM
    min_tokens_override_limit: Optional[int] # For Pathos LLM max_tokens_override
    max_tokens_override_limit: Optional[int] # For Pathos LLM max_tokens_override


class EthosConfig(TypedDict, total=False):
    memory_db_path: str
    embedding_model_name: str
    embedding_max_text_length: int # New: Max length of text to embed
    reflection_interval_seconds: int
    forgetting_interval_seconds: int # New: Interval for salience decay
    salience_decay_rate_per_day: float # New: Rate of salience decay
    min_salience_for_decay: float # New: Minimum salience to consider for decay
    user_fact_salience_floor: float # New: Minimum salience for user_facts after decay
    mood_decay_rate_per_hour: float
    feedback_salience_boost: float
    text_chunk_size: int
    text_chunk_overlap: int
    hexus_decay_interval_seconds: int
    hexus_decay_rate_per_cycle: float
    hexus_activation_threshold: float
    hexus_curve_k: float
    hexus_feedback_adjustment_step: float
    proactive_greeting_interval_hours: int
    proactive_topic_interval_hours: int
    proactive_engagement_threshold: float
    proactive_engagement_curve_k: float
    proactive_check_interval_seconds: int
    proactive_queued_point_offer_interval_hours: int
    proactive_greeting_chance: float
    proactive_topic_chance: float
    proactive_briefing_chance: float
    proactive_queued_point_chance: float
    # Memory Summarization
    enable_memory_summarization: bool
    summarization_llm_role: str
    summarization_cluster_min_memories: int
    summarization_max_memories_per_cluster: int
    summarization_max_text_length_for_prompt: int
    summarization_max_days_to_consider: int
    # Knowledge Upkeep
    knowledge_upkeep_interval_seconds: int
    knowledge_upkeep_llm_role: str 
    knowledge_upkeep_volatile_tags: List[str] # List of tags that mark facts as needing re-verification
    # Proactive immediate greeting (e.g., on user connect)
    proactive_immediate_greeting_grace_minutes: int
    proactive_immediate_greeting_chance: float
    enable_interaction_log_analysis: bool
    interaction_log_analysis_interval_seconds: int
    interaction_log_analysis_llm_role: str # e.g., "LOGOS_TECHNE"
    interaction_log_analysis_batch_size: int # How many interactions to process at once
    interaction_log_analysis_max_days_lookback: int # How far back to look for unanalyzed interactions


class HomeAssistantConfig(TypedDict, total=False):
    url: str
    token: str
    allowed_domains: List[str]
    timeout: int
    ha_weather_entity_id: Optional[str] # For weather fallback

class VoiceConfig(TypedDict, total=False):
    energy_threshold: int
    default_voice: str
    wake_word: str
    stt_model: Optional[str]

class OneirosConfig(TypedDict, total=False):
    dream_interval_seconds: int
    wildcard_files_dir: str
    stable_diffusion_url: Optional[str]
    dream_llm_role: str # e.g., "PATHOS" or a dedicated "ONEIROS_DREAM_LLM"
    dream_num_source_memories: int
    dream_min_salience_for_source: float
    enable_image_dreams: bool
    image_output_dir: str
    # Optional LLM param overrides for dream generation
    dream_llm_temperature: Optional[float]
    dream_llm_top_p: Optional[float]
    dream_llm_presence_penalty: Optional[float]
    dream_llm_frequency_penalty: Optional[float]
    dream_llm_max_tokens: Optional[int]


class AisthesisConfig(TypedDict, total=False):
    mqtt_broker_url: Optional[str]
    mqtt_broker_port: int
    mqtt_topic_prefix: str
    nodes_json: Optional[Dict[str, Any]] # Or a path to a JSON file

class ApiConfig(TypedDict, total=False):
    host: str
    port: int
    log_level: str

class OpenWeatherMapConfig(TypedDict, total=False):
    api_key: str
    units: Literal["metric", "imperial"]
    base_url: str
    timeout: int

class WolframAlphaConfig(TypedDict, total=False):
    app_id: str
    api_url: str
    timeout: int

class NewsApiConfig(TypedDict, total=False):
    enabled: bool # Explicitly control if this API is used
    api_key: str
    base_url: str
    default_locale: str
    default_language: str
    limit: int
    timeout: int
    search_keywords: Optional[str] # Comma-separated
    categories: Optional[str]      # Comma-separated
    include_source_ids: Optional[str] # Comma-separated
    exclude_source_ids: Optional[str] # Comma-separated (TheNewsAPI uses exclude_domains)

class BraveSearchConfig(TypedDict, total=False):
    api_key: str
    timeout: int
    max_results_per_query: int

# New: Eidos TTS Configuration (for external SparkTTS API server)
VALID_PITCH_SPEED_VALUES = ["very_low", "low", "moderate", "high", "very_high"]
VALID_GENDER_VALUES = ["female", "male"]

class EidosTTSConfig(TypedDict, total=False):
    api_url: str
    api_key: Optional[str]
    model_id: Optional[str]
    voice_id: str
    response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]
    speed: Optional[float]
    timeout: int
    lang_code: Optional[str] # New
    normalization_options: Optional[Dict[str, bool]] # New


# --- Main Config Class ---
class Config:
    # LLM Configurations (ensure keys match .env names for LLM roles)
    LLM: Dict[str, LLMConfig] = {
        "PATHOS": {
            "url": os.getenv("LLM_PATHOS_URL", "http://localhost:1234/v1"),
            "model": os.getenv("LLM_PATHOS_MODEL"),
            "api_key": os.getenv("LLM_PATHOS_API_KEY", "lm-studio"),
            "temperature": float(os.getenv("LLM_PATHOS_TEMP", 0.7)),
            "timeout": float(os.getenv("LLM_PATHOS_TIMEOUT", 300.0)),
            "max_tokens": int(os.getenv("LLM_PATHOS_MAX_TOKENS", 4096)),
            "top_p": float(os.getenv("LLM_PATHOS_TOP_P", 0.95)) if os.getenv("LLM_PATHOS_TOP_P") else None,
            "presence_penalty": float(os.getenv("LLM_PATHOS_PRESENCE_PENALTY", 0.0)) if os.getenv("LLM_PATHOS_PRESENCE_PENALTY") else None,
            "frequency_penalty": float(os.getenv("LLM_PATHOS_FREQUENCY_PENALTY", 0.0)) if os.getenv("LLM_PATHOS_FREQUENCY_PENALTY") else None,
            "max_tool_iterations": int(os.getenv("LLM_PATHOS_MAX_TOOL_ITERATIONS", 3)),
            "min_tokens_override_limit": int(os.getenv("LLM_PATHOS_MIN_TOKENS_OVERRIDE_LIMIT", 256)),
            "max_tokens_override_limit": int(os.getenv("LLM_PATHOS_MAX_TOKENS_OVERRIDE_LIMIT", 32000)),
        },
        "LOGOS_TECHNE": { # For summarization, reflection, knowledge upkeep
            "url": os.getenv("LLM_LOGOS_TECHNE_URL", "http://localhost:1234/v1"),
            "model": os.getenv("LLM_LOGOS_TECHNE_MODEL"),
            "api_key": os.getenv("LLM_LOGOS_TECHNE_API_KEY", "lm-studio"),
            "temperature": float(os.getenv("LLM_LOGOS_TECHNE_TEMP", 0.3)),
            "timeout": float(os.getenv("LLM_LOGOS_TECHNE_TIMEOUT", 300.0)),
            "max_tokens": int(os.getenv("LLM_LOGOS_TECHNE_MAX_TOKENS", 2048)),
            "top_p": float(os.getenv("LLM_LOGOS_TECHNE_TOP_P", 0.95)) if os.getenv("LLM_LOGOS_TECHNE_TOP_P") else None,
            "presence_penalty": float(os.getenv("LLM_LOGOS_TECHNE_PRESENCE_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_TECHNE_PRESENCE_PENALTY") else None,
            "frequency_penalty": float(os.getenv("LLM_LOGOS_TECHNE_FREQUENCY_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_TECHNE_FREQUENCY_PENALTY") else None,
        },
        "LOGOS_VISION_CONTEXT": { # For image description
            "url": os.getenv("LLM_LOGOS_VISION_URL"),
            "model": os.getenv("LLM_LOGOS_VISION_MODEL"),
            "api_key": os.getenv("LLM_LOGOS_VISION_API_KEY", "lm-studio"),
            "temperature": float(os.getenv("LLM_LOGOS_VISION_TEMP", 0.2)),
            "timeout": float(os.getenv("LLM_LOGOS_VISION_TIMEOUT", 60.0)),
            "max_tokens": int(os.getenv("LLM_LOGOS_VISION_MAX_TOKENS", 1024)),
            "top_p": float(os.getenv("LLM_LOGOS_VISION_TOP_P", 0.95)) if os.getenv("LLM_LOGOS_VISION_TOP_P") else None,
            "presence_penalty": float(os.getenv("LLM_LOGOS_VISION_PRESENCE_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_VISION_PRESENCE_PENALTY") else None,
            "frequency_penalty": float(os.getenv("LLM_LOGOS_VISION_FREQUENCY_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_VISION_FREQUENCY_PENALTY") else None,
        },
        "LOGOS_DEEP_RESEARCH": { # For deep research synthesis
            "url": os.getenv("LLM_LOGOS_RESEARCH_URL"),
            "model": os.getenv("LLM_LOGOS_RESEARCH_MODEL"),
            "api_key": os.getenv("LLM_LOGOS_RESEARCH_API_KEY", "lm-studio"),
            "temperature": float(os.getenv("LLM_LOGOS_RESEARCH_TEMP", 0.5)),
            "timeout": float(os.getenv("LLM_LOGOS_RESEARCH_TIMEOUT", 180.0)),
            "max_tokens": int(os.getenv("LLM_LOGOS_RESEARCH_MAX_TOKENS", 4096)),
            "top_p": float(os.getenv("LLM_LOGOS_RESEARCH_TOP_P", 0.95)) if os.getenv("LLM_LOGOS_RESEARCH_TOP_P") else None,
            "presence_penalty": float(os.getenv("LLM_LOGOS_RESEARCH_PRESENCE_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_RESEARCH_PRESENCE_PENALTY") else None,
            "frequency_penalty": float(os.getenv("LLM_LOGOS_RESEARCH_FREQUENCY_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_RESEARCH_FREQUENCY_PENALTY") else None,
        }
        # ONEIROS_DREAM_LLM is handled by get_llm_config using ONEIROS_DREAM_LLM_ROLE
    }

    # Feature Flags
    ENABLE_AISTHESIS = os.getenv("ENABLE_AISTHESIS", "False").lower() == "true"
    ENABLE_AMBIENT_AUDIO = os.getenv("ENABLE_AMBIENT_AUDIO", "False").lower() == "true"
    ENABLE_VISION_PROCESSING = os.getenv("ENABLE_VISION_PROCESSING", "False").lower() == "true"
    ENABLE_DAILY_CONTEXT = os.getenv("ENABLE_DAILY_CONTEXT", "True").lower() == "true"
    ENABLE_ONEIROS = os.getenv("ENABLE_ONEIROS", "True").lower() == "true"
    ENABLE_PROACTIVE_BEHAVIOR = os.getenv("ENABLE_PROACTIVE_BEHAVIOR", "True").lower() == "true"
    ENABLE_MOOD_SIMULATION = os.getenv("ENABLE_MOOD_SIMULATION", "True").lower() == "true"
    ENABLE_MANAGED_FORGETTING = os.getenv("ENABLE_MANAGED_FORGETTING", "True").lower() == "true"
    ENABLE_LEARNING_FROM_FEEDBACK = os.getenv("ENABLE_LEARNING_FROM_FEEDBACK", "True").lower() == "true"
    ENABLE_CURIOUSITY = os.getenv("ENABLE_CURIOUSITY", "True").lower() == "true"
    ENABLE_WOLFRAM_ALPHA = os.getenv("ENABLE_WOLFRAM_ALPHA", "True").lower() == "true"
    ENABLE_WEB_SEARCH = os.getenv("ENABLE_WEB_SEARCH", "True").lower() == "true"
    ENABLE_KNOWLEDGE_UPKEEP = os.getenv("ENABLE_KNOWLEDGE_UPKEEP", "True").lower() == "true"


    # Ethos Core Configuration
    ETHOS: EthosConfig = {
        "memory_db_path": os.getenv("ETHOS_MEMORY_DB_PATH", str(PROJECT_ROOT / "eidos_memories" / "memory.sqlite")),
        "embedding_model_name": os.getenv("ETHOS_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        "embedding_max_text_length": int(os.getenv("ETHOS_EMBEDDING_MAX_TEXT_LENGTH", 2560)),
        "reflection_interval_seconds": int(os.getenv("ETHOS_REFLECTION_INTERVAL_SECONDS", 86400)),
        "forgetting_interval_seconds": int(os.getenv("ETHOS_FORGETTING_INTERVAL_SECONDS", 43200)),
        "salience_decay_rate_per_day": float(os.getenv("ETHOS_SALIENCE_DECAY_RATE_PER_DAY", 0.01)),
        "min_salience_for_decay": float(os.getenv("ETHOS_MIN_SALIENCE_FOR_DECAY", 0.01)),
        "user_fact_salience_floor": float(os.getenv("ETHOS_USER_FACT_SALIENCE_FLOOR", 1.0)),
        "mood_decay_rate_per_hour": float(os.getenv("ETHOS_MOOD_DECAY_RATE_PER_HOUR", 0.05)),
        "feedback_salience_boost": float(os.getenv("ETHOS_FEEDBACK_SALIENCE_BOOST", 0.5)),
        "text_chunk_size": int(os.getenv("ETHOS_TEXT_CHUNK_SIZE", 1000)),
        "text_chunk_overlap": int(os.getenv("ETHOS_TEXT_CHUNK_OVERLAP", 150)),
        "hexus_decay_interval_seconds": int(os.getenv("ETHOS_HEXUS_DECAY_INTERVAL_SECONDS", 3600)),
        "hexus_decay_rate_per_cycle": float(os.getenv("ETHOS_HEXUS_DECAY_RATE_PER_CYCLE", 0.005)),
        "hexus_activation_threshold": float(os.getenv("ETHOS_HEXUS_ACTIVATION_THRESHOLD", 0.1)),
        "hexus_curve_k": float(os.getenv("ETHOS_HEXUS_CURVE_K", 2.0)),
        "hexus_feedback_adjustment_step": float(os.getenv("ETHOS_HEXUS_FEEDBACK_ADJUSTMENT_STEP", 0.05)),
        "proactive_greeting_interval_hours": int(os.getenv("ETHOS_PROACTIVE_GREETING_INTERVAL_HOURS", 4)),
        "proactive_topic_interval_hours": int(os.getenv("ETHOS_PROACTIVE_TOPIC_INTERVAL_HOURS", 12)),
        "proactive_engagement_threshold": float(os.getenv("ETHOS_PROACTIVE_ENGAGEMENT_THRESHOLD", 0.1)),
        "proactive_engagement_curve_k": float(os.getenv("ETHOS_PROACTIVE_ENGAGEMENT_CURVE_K", 2.5)),
        "proactive_check_interval_seconds": int(os.getenv("ETHOS_PROACTIVE_CHECK_INTERVAL_SECONDS", 60)),
        "proactive_queued_point_offer_interval_hours": int(os.getenv("ETHOS_PROACTIVE_QUEUED_POINT_OFFER_INTERVAL_HOURS", 24)),
        "proactive_greeting_chance": float(os.getenv("ETHOS_PROACTIVE_GREETING_CHANCE", 0.3)),
        "proactive_topic_chance": float(os.getenv("ETHOS_PROACTIVE_TOPIC_CHANCE", 0.2)),
        "proactive_briefing_chance": float(os.getenv("ETHOS_PROACTIVE_BRIEFING_CHANCE", 0.4)),
        "proactive_queued_point_chance": float(os.getenv("ETHOS_PROACTIVE_QUEUED_POINT_CHANCE", 0.5)),
        "enable_memory_summarization": os.getenv("ETHOS_ENABLE_MEMORY_SUMMARIZATION", "True").lower() == "true",
        "summarization_llm_role": os.getenv("ETHOS_SUMMARIZATION_LLM_ROLE", "LOGOS_TECHNE"),
        "summarization_cluster_min_memories": int(os.getenv("ETHOS_SUMMARIZATION_CLUSTER_MIN_MEMORIES", 5)),
        "summarization_max_memories_per_cluster": int(os.getenv("ETHOS_SUMMARIZATION_MAX_MEMORIES_PER_CLUSTER", 15)),
        "summarization_max_text_length_for_prompt": int(os.getenv("ETHOS_SUMMARIZATION_MAX_TEXT_LENGTH_FOR_PROMPT", 10000)),
        "summarization_max_days_to_consider": int(os.getenv("ETHOS_SUMMARIZATION_MAX_DAYS_TO_CONSIDER", 30)),
        "knowledge_upkeep_interval_seconds": int(os.getenv("ETHOS_KNOWLEDGE_UPKEEP_INTERVAL_SECONDS", 86400)),
        "knowledge_upkeep_llm_role": os.getenv("ETHOS_KNOWLEDGE_UPKEEP_LLM_ROLE", "LOGOS_TECHNE"),
        "knowledge_upkeep_volatile_tags": json.loads(os.getenv("ETHOS_KNOWLEDGE_UPKEEP_VOLATILE_TAGS", '[]')),
        "proactive_immediate_greeting_grace_minutes": int(os.getenv("ETHOS_PROACTIVE_IMMEDIATE_GREETING_GRACE_MINUTES", 15)),
        "proactive_immediate_greeting_chance": float(os.getenv("ETHOS_PROACTIVE_IMMEDIATE_GREETING_CHANCE", 0.75)),
        "enable_interaction_log_analysis": os.getenv("ETHOS_ENABLE_INTERACTION_LOG_ANALYSIS", "True").lower() == "true",
        "interaction_log_analysis_interval_seconds": int(os.getenv("ETHOS_INTERACTION_LOG_ANALYSIS_INTERVAL_SECONDS", 86400)), # e.g., daily
        "interaction_log_analysis_llm_role": os.getenv("ETHOS_INTERACTION_LOG_ANALYSIS_LLM_ROLE", "LOGOS_TECHNE"),
        "interaction_log_analysis_batch_size": int(os.getenv("ETHOS_INTERACTION_LOG_ANALYSIS_BATCH_SIZE", 20)),
        "interaction_log_analysis_max_days_lookback": int(os.getenv("ETHOS_INTERACTION_LOG_ANALYSIS_MAX_DAYS_LOOKBACK", 7)),
    }

    # Home Assistant Configuration
    HOME_ASSISTANT: Optional[HomeAssistantConfig] = None
    if os.getenv("HA_URL") and os.getenv("HA_TOKEN"):
        try:
            allowed_domains_json = os.getenv("HA_ALLOWED_DOMAINS", '[]')
            allowed_domains_list = json.loads(allowed_domains_json)
            if not isinstance(allowed_domains_list, list) or not all(isinstance(item, str) for item in allowed_domains_list):
                raise ValueError("HA_ALLOWED_DOMAINS must be a JSON string array.")
            HOME_ASSISTANT = {
                "url": os.environ["HA_URL"],
                "token": os.environ["HA_TOKEN"],
                "allowed_domains": allowed_domains_list,
                "timeout": int(os.getenv("HA_TIMEOUT", 15)),
                "ha_weather_entity_id": os.getenv("HA_WEATHER_ENTITY_ID")
            }
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing HA_ALLOWED_DOMAINS: {e}. Home Assistant integration might be limited.")
            # Fallback to minimal config if domains parsing fails but URL/Token exist
            HOME_ASSISTANT = {
                "url": os.environ["HA_URL"],
                "token": os.environ["HA_TOKEN"],
                "allowed_domains": ["light", "switch"], # Minimal safe default
                "timeout": int(os.getenv("HA_TIMEOUT", 15)),
                "ha_weather_entity_id": os.getenv("HA_WEATHER_ENTITY_ID")
            }

    # Voice Interface Configuration
    VOICE: VoiceConfig = {
        "energy_threshold": int(os.getenv("VOICE_ENERGY_THRESHOLD", 300)),
        "default_voice": os.getenv("VOICE_DEFAULT_VOICE", "female"),
        "wake_word": os.getenv("VOICE_WAKE_WORD", "eidos"),
        "stt_model": os.getenv("VOICE_STT_MODEL")
    }

    # Oneiros Module Configuration
    ONEIROS: OneirosConfig = {
        "dream_interval_seconds": int(os.getenv("ONEIROS_DREAM_INTERVAL_SECONDS", 21600)),
        "wildcard_files_dir": os.getenv("ONEIROS_WILDCARD_FILES_DIR", str(PROJECT_ROOT / "wildcards")),
        "stable_diffusion_url": os.getenv("ONEIROS_STABLE_DIFFUSION_URL"),
        "dream_llm_role": os.getenv("ONEIROS_DREAM_LLM_ROLE", "PATHOS"),
        "dream_num_source_memories": int(os.getenv("ONEIROS_DREAM_NUM_SOURCE_MEMORIES", 3)),
        "dream_min_salience_for_source": float(os.getenv("ONEIROS_DREAM_MIN_SALIENCE_FOR_SOURCE", 0.0)),
        "enable_image_dreams": os.getenv("ONEIROS_ENABLE_IMAGE_DREAMS", "False").lower() == "true",
        "image_output_dir": os.getenv("ONEIROS_IMAGE_OUTPUT_DIR", str(PROJECT_ROOT / "eidos_dream_images")),
        "dream_llm_temperature": float(os.getenv("ONEIROS_DREAM_LLM_TEMPERATURE")) if os.getenv("ONEIROS_DREAM_LLM_TEMPERATURE") else None,
        "dream_llm_top_p": float(os.getenv("ONEIROS_DREAM_LLM_TOP_P")) if os.getenv("ONEIROS_DREAM_LLM_TOP_P") else None,
        "dream_llm_presence_penalty": float(os.getenv("ONEIROS_DREAM_LLM_PRESENCE_PENALTY")) if os.getenv("ONEIROS_DREAM_LLM_PRESENCE_PENALTY") else None,
        "dream_llm_frequency_penalty": float(os.getenv("ONEIROS_DREAM_LLM_FREQUENCY_PENALTY")) if os.getenv("ONEIROS_DREAM_LLM_FREQUENCY_PENALTY") else None,
        "dream_llm_max_tokens": int(os.getenv("ONEIROS_DREAM_LLM_MAX_TOKENS")) if os.getenv("ONEIROS_DREAM_LLM_MAX_TOKENS") else None,
    }
    IMAGE_OUTPUT_DIR = Path(ONEIROS["image_output_dir"]) # For direct access if needed

    # Aisthesis Network Configuration
    AISTHESIS: AisthesisConfig = {
        "mqtt_broker_url": os.getenv("AISTHESIS_MQTT_BROKER_URL"),
        "mqtt_broker_port": int(os.getenv("AISTHESIS_MQTT_BROKER_PORT", 1883)),
        "mqtt_topic_prefix": os.getenv("AISTHESIS_MQTT_TOPIC_PREFIX", "eidos/sensor/"),
        "nodes_json": json.loads(os.getenv("AISTHESIS_NODES_JSON", "{}"))
    }

    # API Server Configuration
    API: ApiConfig = {
        "host": os.getenv("API_HOST", "0.0.0.0"),
        "port": int(os.getenv("API_PORT", 8088)),
        "log_level": os.getenv("API_LOG_LEVEL", "info").lower()
    }

    # OpenWeatherMap Configuration
    OPENWEATHERMAP: Optional[OpenWeatherMapConfig] = None
    if os.getenv("OWM_API_KEY"):
        OPENWEATHERMAP = {
            "api_key": os.environ["OWM_API_KEY"],
            "units": os.getenv("OWM_UNITS", "imperial"), # type: ignore
            "base_url": os.getenv("OWM_BASE_URL", "https://api.openweathermap.org"),
            "timeout": int(os.getenv("OWM_TIMEOUT", 10))
        }

    # Wolfram Alpha Configuration
    WOLFRAM_ALPHA: Optional[WolframAlphaConfig] = None
    if os.getenv("WOLFRAM_ALPHA_APP_ID"):
        WOLFRAM_ALPHA = {
            "app_id": os.environ["WOLFRAM_ALPHA_APP_ID"],
            "api_url": os.getenv("WOLFRAM_ALPHA_API_URL", "http://api.wolframalpha.com/v2/query"),
            "timeout": int(os.getenv("WOLFRAM_ALPHA_TIMEOUT", 25))
        }

    # News API Configuration
    NEWS_API: Optional[NewsApiConfig] = None
    if os.getenv("NEWS_API_ENABLED", "False").lower() == "true" and os.getenv("NEWS_API_KEY"):
        NEWS_API = {
            "enabled": True,
            "api_key": os.environ["NEWS_API_KEY"],
            "base_url": os.getenv("NEWS_API_BASE_URL", "https://api.thenewsapi.com"),
            "default_locale": os.getenv("NEWS_API_DEFAULT_LOCALE", "us"),
            "default_language": os.getenv("NEWS_API_DEFAULT_LANGUAGE", "en"),
            "limit": int(os.getenv("NEWS_API_LIMIT", 5)),
            "timeout": int(os.getenv("NEWS_API_TIMEOUT", 20)),
            "search_keywords": os.getenv("NEWS_API_SEARCH_KEYWORDS"),
            "categories": os.getenv("NEWS_API_CATEGORIES"),
            "include_source_ids": os.getenv("NEWS_API_INCLUDE_SOURCE_IDS"),
            "exclude_source_ids": os.getenv("NEWS_API_EXCLUDE_SOURCE_IDS")
        }
    elif os.getenv("NEWS_API_ENABLED", "False").lower() == "true" and not os.getenv("NEWS_API_KEY"):
        print("Warning: NEWS_API_ENABLED is true, but NEWS_API_KEY is not set. News features will be disabled.")
        NEWS_API = {"enabled": False} # type: ignore
    else:
        NEWS_API = {"enabled": False} # type: ignore


    # Brave Search Configuration
    BRAVE_SEARCH: Optional[BraveSearchConfig] = None
    if os.getenv("BRAVE_API_KEY"):
        BRAVE_SEARCH = {
            "api_key": os.environ["BRAVE_API_KEY"],
            "timeout": int(os.getenv("BRAVE_SEARCH_TIMEOUT", 15)),
            "max_results_per_query": int(os.getenv("BRAVE_SEARCH_MAX_RESULTS", 3))
        }

    # Eidos TTS Configuration (for external SparkTTS API server)
    EIDOS_TTS: Optional[EidosTTSConfig] = None
    if os.getenv("KOKORO_TTS_API_URL"): # Check for new Kokoro URL
        tts_speed_str = os.getenv("KOKORO_TTS_SPEED", "1.0")
        try:
            tts_speed = float(tts_speed_str)
            if not (0.25 <= tts_speed <= 4.0):
                print(f"Warning: KOKORO_TTS_SPEED '{tts_speed_str}' out of range (0.25-4.0). Defaulting to 1.0.")
                tts_speed = 1.0
        except ValueError:
            print(f"Warning: Invalid KOKORO_TTS_SPEED '{tts_speed_str}'. Defaulting to 1.0.")
            tts_speed = 1.0

        response_format_val = os.getenv("KOKORO_TTS_RESPONSE_FORMAT", "wav").lower()
        if response_format_val not in ["mp3", "opus", "aac", "flac", "wav", "pcm"]:
            print(f"Warning: Invalid KOKORO_TTS_RESPONSE_FORMAT '{response_format_val}'. Defaulting to 'wav'.")
            response_format_val = "wav"

        normalization_options_json = os.getenv("KOKORO_TTS_NORMALIZATION_OPTIONS")
        normalization_options_dict = { # <<< START WITH THE DEFAULT OBJECT
            "normalize": True,
            "unit_normalization": False,
            "url_normalization": True,
            "email_normalization": True,
            "optional_pluralization_normalization": True,
            "phone_normalization": True
        }
        if normalization_options_json:
            try:
                loaded_options = json.loads(normalization_options_json)
                if isinstance(loaded_options, dict): # Basic check
                    normalization_options_dict = loaded_options # Override with .env if valid
                else:
                    print(f"Warning: KOKORO_TTS_NORMALIZATION_OPTIONS in .env is not a valid JSON object. Using defaults.")
            except json.JSONDecodeError:
                print(f"Warning: Invalid JSON for KOKORO_TTS_NORMALIZATION_OPTIONS. Using defaults.")

        EIDOS_TTS = {
            "api_url": os.environ["KOKORO_TTS_API_URL"],
            "api_key": os.getenv("KOKORO_TTS_API_KEY"),
            "model_id": os.getenv("KOKORO_TTS_MODEL_ID", "kokoro"),
            "voice_id": os.getenv("KOKORO_TTS_VOICE_ID"), 
            "response_format": response_format_val, # type: ignore
            "speed": tts_speed,
            "timeout": int(os.getenv("KOKORO_TTS_TIMEOUT", 60)),
            "lang_code": os.getenv("KOKORO_TTS_LANG_CODE", "en-US"),
            "normalization_options": normalization_options_dict # <<< NOW SENDS THE OBJECT
        }
        if not EIDOS_TTS.get("voice_id"):
            print("CRITICAL WARNING: KOKORO_TTS_VOICE_ID is not set in .env. TTS will likely fail.")
        print(f"Kokoro TTS Service Configured: URL='{EIDOS_TTS['api_url']}', Model='{EIDOS_TTS.get('model_id')}', Voice='{EIDOS_TTS.get('voice_id')}'")


    # System Behavior
    MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", 5))

    # Security
    EIDOS_ADMIN_PASSWORD = os.getenv("EIDOS_ADMIN_PASSWORD")


    @staticmethod
    def get_llm_config(role: str) -> Optional[LLMConfig]:
        # Special handling for dream LLM role, which might be overridden
        if role == Config.ONEIROS.get('dream_llm_role') and role not in Config.LLM:
            # If the dream_llm_role (e.g. "ONEIROS_DREAM_LLM") is custom and not directly in Config.LLM,
            # but its parameters are defined under Config.ONEIROS (like dream_llm_temperature),
            # we might need to construct its config here or ensure it's added to Config.LLM.
            # For now, assume ONEIROS_DREAM_LLM_ROLE points to an existing key in Config.LLM (e.g. "PATHOS" or "LOGOS_TECHNE")
            # or that the specific role (e.g. "ONEIROS_DREAM_LLM") is added to Config.LLM if it has unique URL/model.
            # The current setup implies ONEIROS_DREAM_LLM_ROLE refers to a role defined in Config.LLM.
            pass
        return Config.LLM.get(role)

    @staticmethod
    def get_ethos_config() -> EthosConfig:
        return Config.ETHOS

    @staticmethod
    def get_ha_config() -> Optional[HomeAssistantConfig]:
        return Config.HOME_ASSISTANT

    @staticmethod
    def get_voice_config() -> VoiceConfig:
        return Config.VOICE

    @staticmethod
    def get_oneiros_config() -> OneirosConfig:
        return Config.ONEIROS

    @staticmethod
    def get_aisthesis_config() -> AisthesisConfig:
        return Config.AISTHESIS

    @staticmethod
    def get_api_config() -> ApiConfig:
        return Config.API

    @staticmethod
    def get_openweathermap_config() -> Optional[OpenWeatherMapConfig]:
        return Config.OPENWEATHERMAP

    @staticmethod
    def get_wolfram_alpha_config() -> Optional[WolframAlphaConfig]:
        return Config.WOLFRAM_ALPHA

    @staticmethod
    def get_news_api_config() -> Optional[NewsApiConfig]:
        return Config.NEWS_API

    @staticmethod
    def get_brave_search_config() -> Optional[BraveSearchConfig]:
        return Config.BRAVE_SEARCH

    @staticmethod
    def get_eidos_tts_config() -> Optional[EidosTTSConfig]:
        return Config.EIDOS_TTS

    @staticmethod
    def get_admin_password() -> Optional[str]:
        return Config.EIDOS_ADMIN_PASSWORD

    @staticmethod
    def setup():
        """Performs initial setup like creating directories."""
        # Ensure memory directory exists
        memory_dir = Path(Config.ETHOS["memory_db_path"]).parent
        memory_dir.mkdir(parents=True, exist_ok=True)
        # print(f"Ensured memory directory exists: {memory_dir.resolve()}")

        # Ensure logs directory exists
        logs_dir = PROJECT_ROOT / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        # print(f"Ensured logs directory exists: {logs_dir.resolve()}")

        # Ensure wildcard directory exists
        wildcard_dir = Path(Config.ONEIROS["wildcard_files_dir"])
        wildcard_dir.mkdir(parents=True, exist_ok=True)
        # print(f"Ensured wildcard directory exists: {wildcard_dir.resolve()}")

        # Ensure dream image output directory exists
        if Config.ONEIROS.get("enable_image_dreams"):
            dream_image_dir = Path(Config.ONEIROS["image_output_dir"])
            dream_image_dir.mkdir(parents=True, exist_ok=True)
            # print(f"Ensured dream image output directory exists: {dream_image_dir.resolve()}")

        # Validate essential LLM URLs
        required_llm_roles = ["PATHOS", "LOGOS_TECHNE"]
        if Config.ENABLE_VISION_PROCESSING:
            required_llm_roles.append("LOGOS_VISION_CONTEXT")
        # If perform_deep_research tool is used, its LLM is implicitly required by LogosCore.
        # ONEIROS_DREAM_LLM is checked by OneirosModule itself.

        for role in required_llm_roles:
            llm_conf = Config.get_llm_config(role)
            if not llm_conf or not llm_conf.get("url"):
                print(f"CRITICAL WARNING: LLM URL for essential role '{role}' is not configured in .env. Eidos functionality will be severely impaired.")
            elif not llm_conf.get("model") and llm_conf.get("api_key", "").lower() == "lm-studio":
                 print(f"WARNING: LLM_MODEL for role '{role}' (LM Studio) is not set. Ensure a model is loaded and selected in LM Studio.")
            elif not llm_conf.get("model") and llm_conf.get("api_key", "").lower() == "ollama":
                 print(f"WARNING: LLM_MODEL for role '{role}' (Ollama) is not set. Ensure you specify a model name available in Ollama.")


# Perform setup tasks when Config class is defined (i.e., on import)
Config.setup()