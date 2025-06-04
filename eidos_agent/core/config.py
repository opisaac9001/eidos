# eidos_agent/core/config.py
import os
from typing import Dict, Any, TypedDict, Optional, List, Literal
from pathlib import Path
from dotenv import load_dotenv
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv_path = PROJECT_ROOT / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path, override=True)
else:
    print(f".env file not found at {dotenv_path}. Using environment variables or defaults.")

class LLMConfig(TypedDict, total=False):
    url: str
    model: Optional[str]
    api_key: Optional[str]
    temperature: Optional[float]
    timeout: Optional[float]
    max_tokens: Optional[int]
    top_p: Optional[float]
    presence_penalty: Optional[float]
    frequency_penalty: Optional[float]
    max_tool_iterations: Optional[int]
    min_tokens_override_limit: Optional[int]
    max_tokens_override_limit: Optional[int]
    supports_vision: Optional[bool] # Ensure this is here
    model_name_for_tiktoken: Optional[str]


class EthosConfig(TypedDict, total=False):
    memory_db_path: str
    embedding_model_name: str
    embedding_max_text_length: int
    reflection_interval_seconds: int
    forgetting_interval_seconds: int
    salience_decay_rate_per_day: float
    min_salience_for_decay: float
    user_fact_salience_floor: float
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
    enable_memory_summarization: bool
    summarization_llm_role: str
    interaction_log_analysis_llm_role: str
    knowledge_upkeep_llm_role: str
    aspiration_generation_llm_role: str # From broken
    long_term_planning_llm_role: str # From broken
    scheduler_llm_role: str # From broken (for Chronos)
    summarization_cluster_min_memories: int
    summarization_max_memories_per_cluster: int
    summarization_max_text_length_for_prompt: int
    summarization_max_days_to_consider: int
    knowledge_upkeep_interval_seconds: int
    knowledge_upkeep_volatile_tags: List[str]
    proactive_immediate_greeting_grace_minutes: int
    proactive_immediate_greeting_chance: float
    enable_interaction_log_analysis: bool
    interaction_log_analysis_interval_seconds: int
    interaction_log_analysis_batch_size: int
    interaction_log_analysis_max_days_lookback: int
    pathos_home_timezone: str # From broken
    aspiration_num_seed_memories: int # From broken
    aspiration_min_salience_seed: float # From broken
    long_term_planning_interval_seconds: float # From broken
    long_term_planning_max_aspirations: int # From broken
    long_term_planning_research_depth: int # From broken
    chronos_maintenance_interval_seconds: float # From broken
    curiosity_research_on_learnings_limit: int # From broken
    curiosity_research_on_learnings_interval_hours: int # From broken
    reflection_feedback_llm_role: str # From broken
    dream_curiosity_llm_role: str # From broken
    curiosity_notification_llm_role: str # From broken
    daily_summary_max_memories: Optional[int]
    daily_summary_lookback_hours: Optional[int]


class HomeAssistantConfig(TypedDict, total=False):
    url: str
    token: str
    allowed_domains: List[str]
    timeout: int
    ha_weather_entity_id: Optional[str]

class VoiceConfig(TypedDict, total=False):
    energy_threshold: int
    default_voice: str
    wake_word: str
    stt_model: Optional[str]

class OneirosConfig(TypedDict, total=False):
    dream_interval_seconds: int
    wildcard_files_dir: str
    stable_diffusion_url: Optional[str]
    dream_llm_role: str
    dream_num_source_memories: int
    dream_min_salience_for_source: float
    enable_image_dreams: bool
    image_output_dir: str
    dream_llm_temperature: Optional[float]
    dream_llm_top_p: Optional[float]
    dream_llm_presence_penalty: Optional[float]
    dream_llm_frequency_penalty: Optional[float]
    dream_llm_max_tokens: Optional[int]

class AisthesisConfig(TypedDict, total=False):
    mqtt_broker_url: Optional[str]
    mqtt_broker_port: int
    mqtt_topic_prefix: str
    nodes_json: Optional[Dict[str, Any]]

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
    enabled: bool
    api_key: str
    base_url: str
    default_locale: str
    default_language: str
    limit: int
    timeout: int
    search_keywords: Optional[str]
    categories: Optional[str]
    include_source_ids: Optional[str]
    exclude_source_ids: Optional[str]

class BraveSearchConfig(TypedDict, total=False):
    api_key: str
    timeout: int
    max_results_per_query: int

class BookshelfConfig(TypedDict, total=False):
    qdrant_host: str
    qdrant_port: int
    qdrant_api_key: Optional[str]
    qdrant_collection_name: str
    embedding_model_name: str
    embedding_dimension: int
    # Potentially add chunk_size, chunk_overlap if they need to be configurable here

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
    lang_code: Optional[str]
    normalization_options: Optional[Dict[str, bool]]


class Config:
    LLM: Dict[str, LLMConfig] = {
        "PATHOS": {
            "url": os.getenv("LLM_PATHOS_URL", "http://localhost:8000/v1"), # Example for VLLM
            "model": os.getenv("LLM_PATHOS_MODEL"),
            "api_key": os.getenv("LLM_PATHOS_API_KEY", "vllm"), # Default for VLLM
            "temperature": float(os.getenv("LLM_PATHOS_TEMP", 0.7)),
            "timeout": float(os.getenv("LLM_PATHOS_TIMEOUT", 300.0)),
            "max_tokens": int(os.getenv("LLM_PATHOS_MAX_TOKENS", 4096)), # Default output limit
            "top_p": float(os.getenv("LLM_PATHOS_TOP_P", 0.95)) if os.getenv("LLM_PATHOS_TOP_P") else None,
            "presence_penalty": float(os.getenv("LLM_PATHOS_PRESENCE_PENALTY", 0.0)) if os.getenv("LLM_PATHOS_PRESENCE_PENALTY") else None,
            "frequency_penalty": float(os.getenv("LLM_PATHOS_FREQUENCY_PENALTY", 0.0)) if os.getenv("LLM_PATHOS_FREQUENCY_PENALTY") else None,
            "max_tool_iterations": int(os.getenv("LLM_PATHOS_MAX_TOOL_ITERATIONS", 5)),
            "min_tokens_override_limit": int(os.getenv("LLM_PATHOS_MIN_TOKENS_OVERRIDE_LIMIT", 256)),
            "max_tokens_override_limit": int(os.getenv("LLM_PATHOS_MAX_TOKENS_OVERRIDE_LIMIT", 32000)),
            "supports_vision": os.getenv("LLM_PATHOS_SUPPORTS_VISION", "False").lower() == "true", # Read from .env
            "model_name_for_tiktoken": os.getenv("LLM_PATHOS_TIKTOKEN_NAME", "cl100k_base")
        },
        "LOGOS_TECHNE": {
            "url": os.getenv("LLM_LOGOS_TECHNE_URL", "http://localhost:1234/v1"),
            "model": os.getenv("LLM_LOGOS_TECHNE_MODEL"),
            "api_key": os.getenv("LLM_LOGOS_TECHNE_API_KEY", "lm-studio"),
            "temperature": float(os.getenv("LLM_LOGOS_TECHNE_TEMP", 0.3)),
            "timeout": float(os.getenv("LLM_LOGOS_TECHNE_TIMEOUT", 300.0)),
            "max_tokens": int(os.getenv("LLM_LOGOS_TECHNE_MAX_TOKENS", 2048)),
            "top_p": float(os.getenv("LLM_LOGOS_TECHNE_TOP_P", 0.95)) if os.getenv("LLM_LOGOS_TECHNE_TOP_P") else None,
            "presence_penalty": float(os.getenv("LLM_LOGOS_TECHNE_PRESENCE_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_TECHNE_PRESENCE_PENALTY") else None,
            "frequency_penalty": float(os.getenv("LLM_LOGOS_TECHNE_FREQUENCY_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_TECHNE_FREQUENCY_PENALTY") else None,
            "model_name_for_tiktoken": os.getenv("LLM_LOGOS_TECHNE_TIKTOKEN_NAME", "cl100k_base") # Added
        },
        "LOGOS_VISION_CONTEXT": { # Kept for potential dedicated image description tool
            "url": os.getenv("LLM_LOGOS_VISION_URL"),
            "model": os.getenv("LLM_LOGOS_VISION_MODEL"),
            "api_key": os.getenv("LLM_LOGOS_VISION_API_KEY", "lm-studio"),
            "temperature": float(os.getenv("LLM_LOGOS_VISION_TEMP", 0.2)),
            "timeout": float(os.getenv("LLM_LOGOS_VISION_TIMEOUT", 60.0)),
            "max_tokens": int(os.getenv("LLM_LOGOS_VISION_MAX_TOKENS", 1024)),
            "top_p": float(os.getenv("LLM_LOGOS_VISION_TOP_P", 0.95)) if os.getenv("LLM_LOGOS_VISION_TOP_P") else None,
            "presence_penalty": float(os.getenv("LLM_LOGOS_VISION_PRESENCE_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_VISION_PRESENCE_PENALTY") else None,
            "frequency_penalty": float(os.getenv("LLM_LOGOS_VISION_FREQUENCY_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_VISION_FREQUENCY_PENALTY") else None,
            "model_name_for_tiktoken": os.getenv("LLM_LOGOS_VISION_TIKTOKEN_NAME", "cl100k_base") # Added
        },
        "LOGOS_DEEP_RESEARCH": {
            "url": os.getenv("LLM_LOGOS_RESEARCH_URL"),
            "model": os.getenv("LLM_LOGOS_RESEARCH_MODEL"),
            "api_key": os.getenv("LLM_LOGOS_RESEARCH_API_KEY", "lm-studio"),
            "temperature": float(os.getenv("LLM_LOGOS_RESEARCH_TEMP", 0.5)),
            "timeout": float(os.getenv("LLM_LOGOS_RESEARCH_TIMEOUT", 180.0)),
            "max_tokens": int(os.getenv("LLM_LOGOS_RESEARCH_MAX_TOKENS", 4096)),
            "top_p": float(os.getenv("LLM_LOGOS_RESEARCH_TOP_P", 0.95)) if os.getenv("LLM_LOGOS_RESEARCH_TOP_P") else None,
            "presence_penalty": float(os.getenv("LLM_LOGOS_RESEARCH_PRESENCE_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_RESEARCH_PRESENCE_PENALTY") else None,
            "frequency_penalty": float(os.getenv("LLM_LOGOS_RESEARCH_FREQUENCY_PENALTY", 0.0)) if os.getenv("LLM_LOGOS_RESEARCH_FREQUENCY_PENALTY") else None,
            "model_name_for_tiktoken": os.getenv("LLM_LOGOS_RESEARCH_TIKTOKEN_NAME", "cl100k_base") # Added
        }
    }

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
    ENABLE_AUTONOMOUS_CURIOSITY_RESEARCH = os.getenv("ENABLE_AUTONOMOUS_CURIOSITY_RESEARCH", "False").lower() == "true"

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
        "interaction_log_analysis_interval_seconds": int(os.getenv("ETHOS_INTERACTION_LOG_ANALYSIS_INTERVAL_SECONDS", 86400)),
        "interaction_log_analysis_llm_role": os.getenv("ETHOS_INTERACTION_LOG_ANALYSIS_LLM_ROLE", "LOGOS_TECHNE"),
        "interaction_log_analysis_batch_size": int(os.getenv("ETHOS_INTERACTION_LOG_ANALYSIS_BATCH_SIZE", 20)),
        "interaction_log_analysis_max_days_lookback": int(os.getenv("ETHOS_INTERACTION_LOG_ANALYSIS_MAX_DAYS_LOOKBACK", 7)),
        "pathos_home_timezone": os.getenv("ETHOS_PATHOS_HOME_TIMEZONE", "UTC"),
        "scheduler_llm_role": os.getenv("ETHOS_SCHEDULER_LLM_ROLE", "LOGOS_TECHNE"),
        "aspiration_generation_llm_role": os.getenv("ETHOS_ASPIRATION_LLM_ROLE", "LOGOS_TECHNE"),
        "aspiration_num_seed_memories": int(os.getenv("ETHOS_ASPIRATION_NUM_SEED_MEMORIES", 5)),
        "aspiration_min_salience_seed": float(os.getenv("ETHOS_ASPIRATION_MIN_SALIENCE_SEED", 0.6)),
        "long_term_planning_llm_role": os.getenv("ETHOS_LONG_TERM_PLANNING_LLM_ROLE", "LOGOS_TECHNE"),
        "long_term_planning_interval_seconds": float(os.getenv("ETHOS_LONG_TERM_PLANNING_INTERVAL_SECONDS", 86400.0 * 3)),
        "long_term_planning_max_aspirations": int(os.getenv("ETHOS_LONG_TERM_PLANNING_MAX_ASPIRATIONS", 2)),
        "long_term_planning_research_depth": int(os.getenv("ETHOS_LONG_TERM_PLANNING_RESEARCH_DEPTH", 2)),
        "chronos_maintenance_interval_seconds": float(os.getenv("ETHOS_CHRONOS_MAINTENANCE_INTERVAL_SECONDS", 21600.0)),
        "curiosity_research_on_learnings_limit": int(os.getenv("ETHOS_CURIOSITY_RESEARCH_ON_LEARNINGS_LIMIT", 2)),
        "curiosity_research_on_learnings_interval_hours": int(os.getenv("ETHOS_CURIOSITY_RESEARCH_ON_LEARNINGS_INTERVAL_HOURS", 24)),
        "reflection_feedback_llm_role": os.getenv("ETHOS_REFLECTION_FEEDBACK_LLM_ROLE", "LOGOS_TECHNE"),
        "dream_curiosity_llm_role": os.getenv("ETHOS_DREAM_CURIOSITY_LLM_ROLE", "LOGOS_TECHNE"),
        "curiosity_notification_llm_role": os.getenv("ETHOS_CURIOSITY_NOTIFICATION_LLM_ROLE", "LOGOS_TECHNE"),
        "daily_summary_max_memories": int(os.getenv("ETHOS_DAILY_SUMMARY_MAX_MEMORIES", "30")),
        "daily_summary_lookback_hours": int(os.getenv("ETHOS_DAILY_SUMMARY_LOOKBACK_HOURS", "18")),
    }

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
            HOME_ASSISTANT = {
                "url": os.environ["HA_URL"],
                "token": os.environ["HA_TOKEN"],
                "allowed_domains": ["light", "switch"],
                "timeout": int(os.getenv("HA_TIMEOUT", 15)),
                "ha_weather_entity_id": os.getenv("HA_WEATHER_ENTITY_ID")
            }

    VOICE: VoiceConfig = {
        "energy_threshold": int(os.getenv("VOICE_ENERGY_THRESHOLD", 300)),
        "default_voice": os.getenv("VOICE_DEFAULT_VOICE", "female"),
        "wake_word": os.getenv("VOICE_WAKE_WORD", "eidos"),
        "stt_model": os.getenv("VOICE_STT_MODEL")
    }

    ONEIROS: OneirosConfig = {
        "dream_interval_seconds": int(os.getenv("ONEIROS_DREAM_INTERVAL_SECONDS", 21600)),
        "wildcard_files_dir": os.getenv("ONEIROS_WILDCARD_FILES_DIR", str(PROJECT_ROOT / "wildcards")),
        "stable_diffusion_url": os.getenv("ONEIROS_STABLE_DIFFUSION_URL"),
        "dream_llm_role": os.getenv("ONEIROS_DREAM_LLM_ROLE", "LOGOS_TECHNE"),
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
    IMAGE_OUTPUT_DIR = Path(ONEIROS["image_output_dir"])

    AISTHESIS: AisthesisConfig = {
        "mqtt_broker_url": os.getenv("AISTHESIS_MQTT_BROKER_URL"),
        "mqtt_broker_port": int(os.getenv("AISTHESIS_MQTT_BROKER_PORT", 1883)),
        "mqtt_topic_prefix": os.getenv("AISTHESIS_MQTT_TOPIC_PREFIX", "eidos/sensor/"),
        "nodes_json": json.loads(os.getenv("AISTHESIS_NODES_JSON", "{}"))
    }

    API: ApiConfig = {
        "host": os.getenv("API_HOST", "0.0.0.0"),
        "port": int(os.getenv("API_PORT", 8088)),
        "log_level": os.getenv("API_LOG_LEVEL", "info").lower()
    }

    OPENWEATHERMAP: Optional[OpenWeatherMapConfig] = None
    if os.getenv("OWM_API_KEY"):
        OPENWEATHERMAP = {
            "api_key": os.environ["OWM_API_KEY"],
            "units": os.getenv("OWM_UNITS", "imperial"), # type: ignore
            "base_url": os.getenv("OWM_BASE_URL", "https://api.openweathermap.org"),
            "timeout": int(os.getenv("OWM_TIMEOUT", 10))
        }

    WOLFRAM_ALPHA: Optional[WolframAlphaConfig] = None
    if os.getenv("WOLFRAM_ALPHA_APP_ID"):
        WOLFRAM_ALPHA = {
            "app_id": os.environ["WOLFRAM_ALPHA_APP_ID"],
            "api_url": os.getenv("WOLFRAM_ALPHA_API_URL", "http://api.wolframalpha.com/v2/query"),
            "timeout": int(os.getenv("WOLFRAM_ALPHA_TIMEOUT", 25))
        }

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

    BRAVE_SEARCH: Optional[BraveSearchConfig] = None
    if os.getenv("BRAVE_API_KEY"):
        BRAVE_SEARCH = {
            "api_key": os.environ["BRAVE_API_KEY"],
            "timeout": int(os.getenv("BRAVE_SEARCH_TIMEOUT", 15)),
            "max_results_per_query": int(os.getenv("BRAVE_SEARCH_MAX_RESULTS", 3))
        }

    EIDOS_TTS: Optional[EidosTTSConfig] = None
    if os.getenv("KOKORO_TTS_API_URL"):
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
        normalization_options_dict = {
            "normalize": True, "unit_normalization": False, "url_normalization": True,
            "email_normalization": True, "optional_pluralization_normalization": True, "phone_normalization": True
        }
        if normalization_options_json:
            try:
                loaded_options = json.loads(normalization_options_json)
                if isinstance(loaded_options, dict): normalization_options_dict = loaded_options
                else: print(f"Warning: KOKORO_TTS_NORMALIZATION_OPTIONS in .env is not a valid JSON object. Using defaults.")
            except json.JSONDecodeError: print(f"Warning: Invalid JSON for KOKORO_TTS_NORMALIZATION_OPTIONS. Using defaults.")
        EIDOS_TTS = {
            "api_url": os.environ["KOKORO_TTS_API_URL"],
            "api_key": os.getenv("KOKORO_TTS_API_KEY"),
            "model_id": os.getenv("KOKORO_TTS_MODEL_ID", "kokoro"),
            "voice_id": os.getenv("KOKORO_TTS_VOICE_ID"),
            "response_format": response_format_val, # type: ignore
            "speed": tts_speed,
            "timeout": int(os.getenv("KOKORO_TTS_TIMEOUT", 60)),
            "lang_code": os.getenv("KOKORO_TTS_LANG_CODE", "en-US"),
            "normalization_options": normalization_options_dict
        }
        if not EIDOS_TTS.get("voice_id"): print("CRITICAL WARNING: KOKORO_TTS_VOICE_ID is not set in .env. TTS will likely fail.")
        print(f"Kokoro TTS Service Configured: URL='{EIDOS_TTS['api_url']}', Model='{EIDOS_TTS.get('model_id')}', Voice='{EIDOS_TTS.get('voice_id')}'")

    MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", 5))
    EIDOS_ADMIN_PASSWORD = os.getenv("EIDOS_ADMIN_PASSWORD")

    BOOKSHELF: Optional[BookshelfConfig] = None
    # Populate Bookshelf config if essential env vars are set
    # Check for QDRANT_HOST as a minimum requirement to enable bookshelf
    if os.getenv("QDRANT_HOST"):
        qdrant_port_str = os.getenv("QDRANT_PORT", "6333")
        embedding_dim_str = os.getenv("BOOKSHELF_EMBEDDING_DIMENSION", "384")
        try:
            qdrant_port_int = int(qdrant_port_str)
            embedding_dim_int = int(embedding_dim_str)
        except ValueError:
            print(f"Warning: Invalid port ('{qdrant_port_str}') or embedding dimension ('{embedding_dim_str}') for Bookshelf. Using defaults.")
            qdrant_port_int = 6333
            embedding_dim_int = 384 # Default for all-MiniLM-L6-v2

        BOOKSHELF = {
            "qdrant_host": os.environ["QDRANT_HOST"], # Use os.environ to ensure it exists if check passed
            "qdrant_port": qdrant_port_int,
            "qdrant_api_key": os.getenv("QDRANT_API_KEY"),
            "qdrant_collection_name": os.getenv("QDRANT_COLLECTION_NAME", "eidos_bookshelf"),
            "embedding_model_name": os.getenv("BOOKSHELF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            "embedding_dimension": embedding_dim_int,
        }
        print(f"Bookshelf feature configured with Qdrant at {BOOKSHELF['qdrant_host']}:{BOOKSHELF['qdrant_port']}")
    else:
        print("Bookshelf feature not configured: QDRANT_HOST environment variable not set.")


    @staticmethod
    def get_llm_config(role: str) -> Optional[LLMConfig]:
        return Config.LLM.get(role)

    @staticmethod
    def get_ethos_config() -> EthosConfig: return Config.ETHOS
    @staticmethod
    def get_ha_config() -> Optional[HomeAssistantConfig]: return Config.HOME_ASSISTANT
    @staticmethod
    def get_voice_config() -> VoiceConfig: return Config.VOICE
    @staticmethod
    def get_oneiros_config() -> OneirosConfig: return Config.ONEIROS
    @staticmethod
    def get_aisthesis_config() -> AisthesisConfig: return Config.AISTHESIS
    @staticmethod
    def get_api_config() -> ApiConfig: return Config.API
    @staticmethod
    def get_openweathermap_config() -> Optional[OpenWeatherMapConfig]: return Config.OPENWEATHERMAP
    @staticmethod
    def get_wolfram_alpha_config() -> Optional[WolframAlphaConfig]: return Config.WOLFRAM_ALPHA
    @staticmethod
    def get_news_api_config() -> Optional[NewsApiConfig]: return Config.NEWS_API
    @staticmethod
    def get_brave_search_config() -> Optional[BraveSearchConfig]: return Config.BRAVE_SEARCH
    @staticmethod
    def get_eidos_tts_config() -> Optional[EidosTTSConfig]: return Config.EIDOS_TTS
    @staticmethod
    def get_admin_password() -> Optional[str]: return Config.EIDOS_ADMIN_PASSWORD
    @staticmethod
    def get_bookshelf_config() -> Optional[BookshelfConfig]: return Config.BOOKSHELF

    @staticmethod
    def setup():
        Path(Config.ETHOS["memory_db_path"]).parent.mkdir(parents=True, exist_ok=True)
        (PROJECT_ROOT / "logs").mkdir(parents=True, exist_ok=True)
        Path(Config.ONEIROS["wildcard_files_dir"]).mkdir(parents=True, exist_ok=True)
        if Config.ONEIROS.get("enable_image_dreams"): Path(Config.ONEIROS["image_output_dir"]).mkdir(parents=True, exist_ok=True)
        
        required_llm_roles = ["PATHOS", "LOGOS_TECHNE"]
        if Config.ENABLE_VISION_PROCESSING: required_llm_roles.append("LOGOS_VISION_CONTEXT")
        if Config.LLM.get("LOGOS_DEEP_RESEARCH") and Config.LLM["LOGOS_DEEP_RESEARCH"].get("url"): required_llm_roles.append("LOGOS_DEEP_RESEARCH")
        
        utility_roles_in_ethos = [
            Config.ETHOS.get('summarization_llm_role'), Config.ETHOS.get('interaction_log_analysis_llm_role'),
            Config.ETHOS.get('knowledge_upkeep_llm_role'), Config.ETHOS.get('aspiration_generation_llm_role'),
            Config.ETHOS.get('long_term_planning_llm_role'), Config.ETHOS.get('scheduler_llm_role'),
            Config.ETHOS.get('reflection_feedback_llm_role'), Config.ETHOS.get('dream_curiosity_llm_role'),
            Config.ETHOS.get('curiosity_notification_llm_role')
        ]
        for role in utility_roles_in_ethos:
            if role and role not in required_llm_roles: required_llm_roles.append(role)
        
        dream_llm_role_name = Config.ONEIROS.get('dream_llm_role')
        if dream_llm_role_name and dream_llm_role_name not in required_llm_roles: required_llm_roles.append(dream_llm_role_name)

        for role in set(required_llm_roles): # Use set to avoid duplicate checks
            llm_conf = Config.get_llm_config(role)
            if not llm_conf or not llm_conf.get("url"): print(f"CRITICAL WARNING: LLM URL for role '{role}' not configured.")
            elif not llm_conf.get("model") and llm_conf.get("api_key", "").lower() in ["lm-studio", "ollama"]: print(f"WARNING: LLM_MODEL for role '{role}' ({llm_conf.get('api_key')}) not set.")

    @staticmethod
    def get_nested_value(data: Dict, keys: List[str], default: Any = None) -> Any:
        for key in keys:
            if isinstance(data, dict) and key in data: data = data[key]
            else: return default
        return data

    @staticmethod
    async def get_llm_config_with_auto_detection(role: str) -> Optional[LLMConfig]:
        from ..utils.model_auto_detection import resolve_model_for_role # Local import
        base_config = Config.get_llm_config(role)
        if not base_config: return None
        if base_config.get("model") and base_config.get("model").lower() == "auto":
            detected_model = await resolve_model_for_role(role)
            if detected_model:
                enhanced_config = base_config.copy(); enhanced_config["model"] = detected_model
                return enhanced_config
        return base_config

Config.setup()