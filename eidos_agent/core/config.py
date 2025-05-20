# eidos_agent/core/config.py
import os
import json
from pathlib import Path
from typing import Literal, TypedDict, Optional, Dict, Any, List, Union
from typing_extensions import TypedDict # For older Python versions if needed, else just use typing.TypedDict
from dotenv import load_dotenv
import logging

# --- Logger Setup ---
# This setup ensures that if config.py is imported before utils.logger,
# basic logging is available. utils.logger.configure_logging will refine it.
try:
    from eidos_agent.utils.logger import configure_logging as util_configure_logging, get_logger as util_get_logger
    # Attempt to configure logging early if possible, but it's mainly done by main.py's import
    if not logging.getLogger().hasHandlers(): # Configure only if not already done
        util_configure_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    _temp_logger_cfg = logging.getLogger(__name__)
    _temp_logger_cfg.warning("eidos_agent.utils.logger not found during config.py import. Using basic logging.")
    def util_get_logger(name): # type: ignore
        return logging.getLogger(name)

logger = util_get_logger(__name__)

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# --- TypedDict Definitions for Configuration Sections ---

class LLMConfig(TypedDict, total=False): # total=False allows for optional keys not always present
    url: Optional[str]
    model: Optional[str]
    temperature: Optional[float]
    timeout: Optional[int]
    api_key: Optional[str]
    max_tokens: Optional[int]
    max_tool_iterations: Optional[int]
    top_p: Optional[float]
    presence_penalty: Optional[float]
    frequency_penalty: Optional[float]

class HomeAssistantConfig(TypedDict, total=False):
    url: Optional[str]
    token: Optional[str]
    allowed_domains: Optional[list[str]]
    timeout: Optional[int]
    ha_weather_entity_id: Optional[str]

class VoiceConfig(TypedDict, total=False): # Not currently used extensively by backend
    energy_threshold: Optional[int]
    default_voice: Optional[Literal['male', 'female']]
    wake_word: Optional[str]
    stt_model: Optional[str]

class EthosConfig(TypedDict, total=False):
    embedding_model_name: Optional[str]
    memory_db_path: Optional[str]
    salience_decay_rate_per_day: Optional[float]
    min_salience_for_decay: Optional[float]
    reflection_interval_seconds: Optional[int]
    forgetting_interval_seconds: Optional[int]
    mood_decay_rate_per_hour: Optional[float]
    feedback_salience_boost: Optional[float]
    text_chunk_size: Optional[int]
    text_chunk_overlap: Optional[int]
    embedding_max_text_length: Optional[int]
    hexus_decay_interval_seconds: Optional[int]
    hexus_decay_rate_per_cycle: Optional[float]
    hexus_activation_threshold: Optional[float]
    hexus_curve_k: Optional[float]
    user_fact_salience_floor: Optional[float]
    proactive_greeting_interval_hours: Optional[int]
    proactive_topic_interval_hours: Optional[int]
    proactive_engagement_threshold: Optional[float]
    proactive_engagement_curve_k: Optional[float]
    proactive_check_interval_seconds: Optional[int]
    proactive_queued_point_offer_interval_hours: Optional[int]
    enable_memory_summarization: Optional[bool]
    summarization_llm_role: Optional[Literal['PATHOS', 'LOGOS_TECHNE', 'LOGOS_DEEP_RESEARCH']]
    summarization_cluster_min_memories: Optional[int]
    summarization_max_memories_per_cluster: Optional[int]
    summarization_max_text_length_for_prompt: Optional[int]
    summarization_max_days_to_consider: Optional[int]
    knowledge_upkeep_interval_seconds: Optional[int]
    knowledge_upkeep_llm_role: Optional[Literal['PATHOS', 'LOGOS_TECHNE', 'LOGOS_DEEP_RESEARCH']]
    knowledge_upkeep_volatile_tags: Optional[List[str]]
    hexus_feedback_adjustment_step: Optional[float]

class OneirosConfig(TypedDict, total=False):
    dream_interval_seconds: Optional[int]
    wildcard_files_dir: Optional[str]
    stable_diffusion_url: Optional[str]
    dream_llm_role: Optional[Literal['PATHOS', 'LOGOS_TECHNE', 'LOGOS_DEEP_RESEARCH']]
    dream_num_source_memories: Optional[int]
    dream_min_salience_for_source: Optional[float]
    enable_image_dreams: Optional[bool]
    image_output_dir: Optional[str]
    dream_llm_temperature: Optional[float]
    dream_llm_top_p: Optional[float]
    dream_llm_presence_penalty: Optional[float]
    dream_llm_frequency_penalty: Optional[float]
    dream_llm_max_tokens: Optional[int]
    dream_llm_timeout: Optional[int]

class AisthesisConfig(TypedDict, total=False): # Not currently used
    mqtt_broker_url: Optional[str]
    mqtt_broker_port: Optional[int]
    mqtt_topic_prefix: Optional[str]
    nodes: Optional[Dict[str, Dict[str, Any]]]

class APIConfig(TypedDict, total=False):
    host: Optional[str]
    port: Optional[int]
    log_level: Optional[str]

class WolframAlphaConfig(TypedDict, total=False):
    app_id: Optional[str]
    api_url: Optional[str]
    timeout: Optional[int]

class NewsApiConfig(TypedDict, total=False):
    enabled: Optional[bool]
    api_key: Optional[str]
    base_url: Optional[str]
    default_locale: Optional[str]
    default_language: Optional[str]
    limit: Optional[int]
    timeout: Optional[int]
    search_keywords: Optional[str]
    categories: Optional[str]
    include_source_ids: Optional[str]
    exclude_source_ids: Optional[str]

class BraveSearchConfig(TypedDict, total=False):
    api_key: Optional[str]
    timeout: Optional[int]
    max_results_per_query: Optional[int]

class OpenWeatherMapConfig(TypedDict, total=False):
    api_key: Optional[str]
    base_url: Optional[str]
    units: Optional[Literal['metric', 'imperial']]
    timeout: Optional[int]

# --- Eidos TTS Config (for external SparkTTS API server) ---
VALID_PITCH_SPEED_VALUES = ["very_low", "low", "moderate", "high", "very_high"]
VALID_GENDER_VALUES = ["female", "male"]

class EidosTTSConfig(TypedDict, total=False):
    api_url: Optional[str]
    default_gender: Optional[Literal["female", "male"]]
    default_pitch_str: Optional[Literal["very_low", "low", "moderate", "high", "very_high"]]
    default_speed_str: Optional[Literal["very_low", "low", "moderate", "high", "very_high"]]
    # timeout_seconds: Optional[int] # For requests Eidos makes TO this server

# --- Main Config Class ---
class Config:
    LLM: Dict[Literal['PATHOS', 'LOGOS_VISION_CONTEXT', 'LOGOS_TECHNE', 'LOGOS_DEEP_RESEARCH'], LLMConfig] = {
        'PATHOS': {
            'url': os.getenv('LLM_PATHOS_URL'), 'model': os.getenv('LLM_PATHOS_MODEL'),
            'temperature': float(os.getenv('LLM_PATHOS_TEMP', '0.7')),
            'timeout': int(os.getenv('LLM_PATHOS_TIMEOUT', '300')), # Increased default
            'api_key': os.getenv('LLM_PATHOS_API_KEY'),
            'max_tokens': int(os.getenv('LLM_PATHOS_MAX_TOKENS', '4096')),
            'max_tool_iterations': int(os.getenv('LLM_PATHOS_MAX_TOOL_ITERATIONS', '3')),
        },
        'LOGOS_TECHNE': {
            'url': os.getenv('LLM_LOGOS_TECHNE_URL'), 'model': os.getenv('LLM_LOGOS_TECHNE_MODEL'),
            'temperature': float(os.getenv('LLM_LOGOS_TECHNE_TEMP', '0.2')),
            'timeout': int(os.getenv('LLM_LOGOS_TECHNE_TIMEOUT', '300')),
            'api_key': os.getenv('LLM_LOGOS_TECHNE_API_KEY'),
            'max_tokens': int(os.getenv('LLM_LOGOS_TECHNE_MAX_TOKENS', '2048')),
        },
        'LOGOS_VISION_CONTEXT': {
            'url': os.getenv('LLM_LOGOS_VISION_URL'), 'model': os.getenv('LLM_LOGOS_VISION_MODEL'),
            'temperature': float(os.getenv('LLM_LOGOS_VISION_TEMP', '0.2')),
            'timeout': int(os.getenv('LLM_LOGOS_VISION_TIMEOUT', '60')),
            'api_key': os.getenv('LLM_LOGOS_VISION_API_KEY'),
            'max_tokens': int(os.getenv('LLM_LOGOS_VISION_MAX_TOKENS', '1024')),
        },
        'LOGOS_DEEP_RESEARCH': {
            'url': os.getenv('LLM_LOGOS_RESEARCH_URL'), 'model': os.getenv('LLM_LOGOS_RESEARCH_MODEL'),
            'temperature': float(os.getenv('LLM_LOGOS_RESEARCH_TEMP', '0.5')),
            'timeout': int(os.getenv('LLM_LOGOS_RESEARCH_TIMEOUT', '180')),
            'api_key': os.getenv('LLM_LOGOS_RESEARCH_API_KEY'),
            'max_tokens': int(os.getenv('LLM_LOGOS_RESEARCH_MAX_TOKENS', '4096')),
        },
    }
    # Optional LLM params (can be added to each LLMConfig dict above if needed)
    for role_key in LLM:
        role_str = str(role_key) # To satisfy type checker for os.getenv
        if val := os.getenv(f'LLM_{role_str}_TOP_P'): Config.LLM[role_key]['top_p'] = float(val)
        if val := os.getenv(f'LLM_{role_str}_PRESENCE_PENALTY'): Config.LLM[role_key]['presence_penalty'] = float(val)
        if val := os.getenv(f'LLM_{role_str}_FREQUENCY_PENALTY'): Config.LLM[role_key]['frequency_penalty'] = float(val)


    ENABLE_AISTHESIS = os.getenv('ENABLE_AISTHESIS', 'False').lower() == 'true'
    ENABLE_AMBIENT_AUDIO = os.getenv('ENABLE_AMBIENT_AUDIO', 'False').lower() == 'true'
    ENABLE_VISION_PROCESSING = os.getenv('ENABLE_VISION_PROCESSING', 'True').lower() == 'true'
    ENABLE_DAILY_CONTEXT = os.getenv('ENABLE_DAILY_CONTEXT', 'True').lower() == 'true'
    ENABLE_ONEIROS = os.getenv('ENABLE_ONEIROS', 'True').lower() == 'true'
    ENABLE_PROACTIVE_BEHAVIOR = os.getenv('ENABLE_PROACTIVE_BEHAVIOR', 'True').lower() == 'true'
    ENABLE_MOOD_SIMULATION = os.getenv('ENABLE_MOOD_SIMULATION', 'True').lower() == 'true'
    ENABLE_MANAGED_FORGETTING = os.getenv('ENABLE_MANAGED_FORGETTING', 'True').lower() == 'true'
    ENABLE_LEARNING_FROM_FEEDBACK = os.getenv('ENABLE_LEARNING_FROM_FEEDBACK', 'True').lower() == 'true'
    ENABLE_CURIOUSITY = os.getenv('ENABLE_CURIOUSITY', 'True').lower() == 'true'
    ENABLE_WOLFRAM_ALPHA = os.getenv('ENABLE_WOLFRAM_ALPHA', 'True').lower() == 'true'
    ENABLE_WEB_SEARCH = os.getenv('ENABLE_WEB_SEARCH', 'True').lower() == 'true'
    ENABLE_KNOWLEDGE_UPKEEP = os.getenv('ENABLE_KNOWLEDGE_UPKEEP', 'True').lower() == 'true' # Defaulted to True

    HOME_ASSISTANT: Optional[HomeAssistantConfig] = None
    ETHOS: EthosConfig = {} # type: ignore
    ONEIROS: OneirosConfig = {} # type: ignore
    AISTHESIS: AisthesisConfig = {} # type: ignore
    API: APIConfig = {} # type: ignore
    WOLFRAM_ALPHA: Optional[WolframAlphaConfig] = None
    NEWS_API: NewsApiConfig = {} # type: ignore
    BRAVE_SEARCH: Optional[BraveSearchConfig] = None
    OPENWEATHERMAP: Optional[OpenWeatherMapConfig] = None
    EIDOS_TTS: Optional[EidosTTSConfig] = None # For external TTS API

    EIDOS_ADMIN_PASSWORD: Optional[str] = os.getenv('EIDOS_ADMIN_PASSWORD')
    MAX_CONCURRENT_TASKS = int(os.getenv('MAX_CONCURRENT_TASKS', '5'))

    MEMORY_DIR = PROJECT_ROOT / 'eidos_memories'
    LOGS_DIR = PROJECT_ROOT / 'logs'
    CACHE_DIR = PROJECT_ROOT / '.cache'
    WILDCARDS_DIR: Path
    IMAGE_OUTPUT_DIR: Path

    _initialized = False
    _logging_configured = False # To track if our custom logging has run

    @classmethod
    def setup(cls):
        global logger
        if not cls._logging_configured:
            # This ensures logging is configured if config.py is the first module to use it.
            # main.py also calls configure_logging(), so this might be redundant but safe.
            try:
                # Check if handlers are already present (e.g., if main.py imported this after configuring logging)
                if not logging.getLogger().hasHandlers():
                    util_configure_logging()
                cls._logging_configured = True
                logger = util_get_logger(__name__) # Re-assign logger after configuration
                logger.info("Logging configured via Config.setup or confirmed existing.")
            except Exception as e_log_setup:
                logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s (basicConfig from Config.setup except)')
                logger = logging.getLogger(__name__)
                logger.error(f"CRITICAL: Failed to configure custom logging in Config.setup: {e_log_setup}. Using basicConfig.", exc_info=True)


        if cls._initialized:
            logger.debug("Config already initialized.")
            return

        logger.info("Running Config attribute setup and validation...")

        # Home Assistant
        _ha_url = os.getenv('HA_URL')
        _ha_token = os.getenv('HA_TOKEN')
        if _ha_url and _ha_token:
            try:
                allowed_domains_json = os.getenv('HA_ALLOWED_DOMAINS', '["light", "switch", "climate", "media_player", "automation", "sensor", "binary_sensor", "timer", "persistent_notification", "scene", "lock", "fan", "weather"]')
                cls.HOME_ASSISTANT = {
                    'url': _ha_url, 'token': _ha_token,
                    'allowed_domains': json.loads(allowed_domains_json),
                    'timeout': int(os.getenv('HA_TIMEOUT', '15')),
                    'ha_weather_entity_id': os.getenv('HA_WEATHER_ENTITY_ID')
                }
            except json.JSONDecodeError:
                logger.error(f"Failed to parse HA_ALLOWED_DOMAINS. Using default for Home Assistant.")
                cls.HOME_ASSISTANT = {
                    'url': _ha_url, 'token': _ha_token,
                    'allowed_domains': ["light", "switch", "climate", "media_player", "automation", "sensor", "binary_sensor", "timer", "persistent_notification", "scene", "lock", "fan", "weather"],
                    'timeout': int(os.getenv('HA_TIMEOUT', '15')),
                    'ha_weather_entity_id': os.getenv('HA_WEATHER_ENTITY_ID')
                }
        else: cls.HOME_ASSISTANT = None

        # Ethos
        cls.ETHOS = {
            'embedding_model_name': os.getenv('ETHOS_EMBEDDING_MODEL', 'all-MiniLM-L6-v2'),
            'memory_db_path': os.getenv('ETHOS_MEMORY_DB_PATH', str(cls.MEMORY_DIR / 'memory.sqlite')),
            'salience_decay_rate_per_day': float(os.getenv('ETHOS_SALIENCE_DECAY_RATE_PER_DAY', '0.01')),
            'min_salience_for_decay': float(os.getenv('ETHOS_MIN_SALIENCE_FOR_DECAY', '0.01')),
            'reflection_interval_seconds': int(os.getenv('ETHOS_REFLECTION_INTERVAL_SECONDS', '86400')),
            'forgetting_interval_seconds': int(os.getenv('ETHOS_FORGETTING_INTERVAL_SECONDS', '43200')),
            'mood_decay_rate_per_hour': float(os.getenv('ETHOS_MOOD_DECAY_RATE_PER_HOUR', '0.05')),
            'feedback_salience_boost': float(os.getenv('ETHOS_FEEDBACK_SALIENCE_BOOST', '0.5')),
            'text_chunk_size': int(os.getenv('ETHOS_TEXT_CHUNK_SIZE', '1000')),
            'text_chunk_overlap': int(os.getenv('ETHOS_TEXT_CHUNK_OVERLAP', '150')),
            'embedding_max_text_length': int(os.getenv('ETHOS_EMBEDDING_MAX_TEXT_LENGTH', '2560')),
            'hexus_decay_interval_seconds': int(os.getenv('ETHOS_HEXUS_DECAY_INTERVAL_SECONDS', '3600')),
            'hexus_decay_rate_per_cycle': float(os.getenv('ETHOS_HEXUS_DECAY_RATE_PER_CYCLE', '0.005')),
            'hexus_activation_threshold': float(os.getenv('ETHOS_HEXUS_ACTIVATION_THRESHOLD', '0.1')),
            'hexus_curve_k': float(os.getenv('ETHOS_HEXUS_CURVE_K', '2.0')),
            'user_fact_salience_floor': float(os.getenv('ETHOS_USER_FACT_SALIENCE_FLOOR', '1.0')),
            'proactive_greeting_interval_hours': int(os.getenv('ETHOS_PROACTIVE_GREETING_INTERVAL_HOURS', '4')),
            'proactive_topic_interval_hours': int(os.getenv('ETHOS_PROACTIVE_TOPIC_INTERVAL_HOURS', '12')),
            'proactive_engagement_threshold': float(os.getenv('ETHOS_PROACTIVE_ENGAGEMENT_THRESHOLD', '0.1')),
            'proactive_engagement_curve_k': float(os.getenv('ETHOS_PROACTIVE_ENGAGEMENT_CURVE_K', '2.5')),
            'proactive_check_interval_seconds': int(os.getenv('ETHOS_PROACTIVE_CHECK_INTERVAL_SECONDS', '60')),
            'proactive_queued_point_offer_interval_hours': int(os.getenv('ETHOS_PROACTIVE_QUEUED_POINT_OFFER_INTERVAL_HOURS', '24')),
            'enable_memory_summarization': os.getenv('ETHOS_ENABLE_MEMORY_SUMMARIZATION', 'True').lower() == 'true',
            'summarization_llm_role': os.getenv('ETHOS_SUMMARIZATION_LLM_ROLE', 'LOGOS_TECHNE'), # type: ignore
            'summarization_cluster_min_memories': int(os.getenv('ETHOS_SUMMARIZATION_CLUSTER_MIN_MEMORIES', '5')),
            'summarization_max_memories_per_cluster': int(os.getenv('ETHOS_SUMMARIZATION_MAX_MEMORIES_PER_CLUSTER', '15')),
            'summarization_max_text_length_for_prompt': int(os.getenv('ETHOS_SUMMARIZATION_MAX_TEXT_LENGTH_FOR_PROMPT', '10000')),
            'summarization_max_days_to_consider': int(os.getenv('ETHOS_SUMMARIZATION_MAX_DAYS_TO_CONSIDER', '30')),
            'knowledge_upkeep_interval_seconds': int(os.getenv('ETHOS_KNOWLEDGE_UPKEEP_INTERVAL_SECONDS', '86400')),
            'knowledge_upkeep_llm_role': os.getenv('ETHOS_KNOWLEDGE_UPKEEP_LLM_ROLE', 'LOGOS_TECHNE'), # type: ignore
            'knowledge_upkeep_volatile_tags': json.loads(os.getenv('ETHOS_KNOWLEDGE_UPKEEP_VOLATILE_TAGS', '["current events", "statistics", "rankings", "records", "technology", "world leaders", "company information", "scientific discoveries", "product releases"]')),
            'hexus_feedback_adjustment_step': float(os.getenv('ETHOS_HEXUS_FEEDBACK_ADJUSTMENT_STEP', '0.05')),
        }

        # Oneiros
        cls.ONEIROS = {
            'dream_interval_seconds': int(os.getenv('ONEIROS_DREAM_INTERVAL_SECONDS', '21600')),
            'wildcard_files_dir': os.getenv('ONEIROS_WILDCARD_FILES_DIR', str(PROJECT_ROOT / 'wildcards')),
            'stable_diffusion_url': os.getenv('ONEIROS_STABLE_DIFFUSION_URL'),
            'dream_llm_role': os.getenv('ONEIROS_DREAM_LLM_ROLE', 'PATHOS'), # type: ignore
            'dream_num_source_memories': int(os.getenv('ONEIROS_DREAM_NUM_SOURCE_MEMORIES', '5')),
            'dream_min_salience_for_source': float(os.getenv('ONEIROS_DREAM_MIN_SALIENCE_FOR_SOURCE', '0.0')), # Changed default
            'enable_image_dreams': os.getenv('ONEIROS_ENABLE_IMAGE_DREAMS', 'True').lower() == 'true', # Defaulted to True
            'image_output_dir': os.getenv('ONEIROS_IMAGE_OUTPUT_DIR', str(PROJECT_ROOT / 'eidos_dream_images')),
        }
        if val := os.getenv('ONEIROS_DREAM_LLM_TEMPERATURE'): cls.ONEIROS['dream_llm_temperature'] = float(val)
        if val := os.getenv('ONEIROS_DREAM_LLM_TOP_P'): cls.ONEIROS['dream_llm_top_p'] = float(val)
        if val := os.getenv('ONEIROS_DREAM_LLM_PRESENCE_PENALTY'): cls.ONEIROS['dream_llm_presence_penalty'] = float(val)
        if val := os.getenv('ONEIROS_DREAM_LLM_FREQUENCY_PENALTY'): cls.ONEIROS['dream_llm_frequency_penalty'] = float(val)
        if val := os.getenv('ONEIROS_DREAM_LLM_MAX_TOKENS'): cls.ONEIROS['dream_llm_max_tokens'] = int(val)
        if val := os.getenv('ONEIROS_DREAM_LLM_TIMEOUT'): cls.ONEIROS['dream_llm_timeout'] = int(val)


        # Aisthesis
        cls.AISTHESIS = {
            'mqtt_broker_url': os.getenv('AISTHESIS_MQTT_BROKER_URL'),
            'mqtt_broker_port': int(os.getenv('AISTHESIS_MQTT_BROKER_PORT', '1883')),
            'mqtt_topic_prefix': os.getenv('AISTHESIS_MQTT_TOPIC_PREFIX', 'eidos/sensor/'),
            'nodes': {}
        }
        if _nodes_json := os.getenv('AISTHESIS_NODES_JSON'):
            try: cls.AISTHESIS['nodes'] = json.loads(_nodes_json)
            except json.JSONDecodeError: logger.error("Failed to parse AISTHESIS_NODES_JSON from .env")

        # API
        cls.API = {
            'host': os.getenv('API_HOST', '0.0.0.0'),
            'port': int(os.getenv('API_PORT', '8088')),
            'log_level': os.getenv('API_LOG_LEVEL', 'info').lower()
        }

        # Wolfram Alpha
        _wa_app_id = os.getenv('WOLFRAM_ALPHA_APP_ID')
        if _wa_app_id:
            cls.WOLFRAM_ALPHA = {
                'app_id': _wa_app_id,
                'api_url': os.getenv('WOLFRAM_ALPHA_API_URL', 'http://api.wolframalpha.com/v2/query'),
                'timeout': int(os.getenv('WOLFRAM_ALPHA_TIMEOUT', '25')) # Increased default
            }
        else: cls.WOLFRAM_ALPHA = None

        # News API
        cls.NEWS_API = {
            'enabled': os.getenv('NEWS_API_ENABLED', 'True').lower() == 'true',
            'api_key': os.getenv('NEWS_API_KEY'),
            'base_url': os.getenv('NEWS_API_BASE_URL', 'https://api.thenewsapi.com'),
            'default_locale': os.getenv('NEWS_API_DEFAULT_LOCALE', 'us'),
            'default_language': os.getenv('NEWS_API_DEFAULT_LANGUAGE', 'en'),
            'limit': int(os.getenv('NEWS_API_LIMIT', '5')), # Increased default
            'timeout': int(os.getenv('NEWS_API_TIMEOUT', '20')), # Increased default
            'search_keywords': os.getenv('NEWS_API_SEARCH_KEYWORDS'),
            'categories': os.getenv('NEWS_API_CATEGORIES'),
            'include_source_ids': os.getenv('NEWS_API_INCLUDE_SOURCE_IDS'),
            'exclude_source_ids': os.getenv('NEWS_API_EXCLUDE_SOURCE_IDS')
        }

        # Brave Search
        _brave_api_key = os.getenv('BRAVE_API_KEY')
        if _brave_api_key:
            cls.BRAVE_SEARCH = {
                'api_key': _brave_api_key,
                'timeout': int(os.getenv('BRAVE_SEARCH_TIMEOUT', '15')),
                'max_results_per_query': int(os.getenv('BRAVE_SEARCH_MAX_RESULTS', '3'))
            }
        else: cls.BRAVE_SEARCH = None

        # OpenWeatherMap
        _owm_api_key = os.getenv('OWM_API_KEY')
        if _owm_api_key:
            cls.OPENWEATHERMAP = {
                'api_key': _owm_api_key,
                'base_url': os.getenv('OWM_BASE_URL', 'https://api.openweathermap.org'),
                'units': os.getenv('OWM_UNITS', 'imperial').lower(), # type: ignore
                'timeout': int(os.getenv('OWM_TIMEOUT', '10'))
            }
            if cls.OPENWEATHERMAP['units'] not in ['metric', 'imperial']:
                 logger.warning(f"Invalid OWM_UNITS '{cls.OPENWEATHERMAP['units']}'. Defaulting to 'imperial'.")
                 cls.OPENWEATHERMAP['units'] = 'imperial'
        else: cls.OPENWEATHERMAP = None

        # Eidos TTS (External SparkTTS API)
        _eidos_tts_api_url = os.getenv('SPARK_TTS_API_URL')
        if _eidos_tts_api_url:
            gender = os.getenv('EIDOS_TTS_DEFAULT_GENDER', 'female').lower()
            if gender not in VALID_GENDER_VALUES: gender = 'female'

            pitch_str_env = os.getenv('EIDOS_TTS_DEFAULT_PITCH_STR', 'moderate').lower()
            if pitch_str_env not in VALID_PITCH_SPEED_VALUES: pitch_str_env = 'moderate'

            speed_str_env = os.getenv('EIDOS_TTS_DEFAULT_SPEED_STR', 'moderate').lower()
            if speed_str_env not in VALID_PITCH_SPEED_VALUES: speed_str_env = 'moderate'

            cls.EIDOS_TTS = {
                'api_url': _eidos_tts_api_url,
                'default_gender': gender, # type: ignore
                'default_pitch_str': pitch_str_env, # type: ignore
                'default_speed_str': speed_str_env, # type: ignore
            }
            logger.info(f"Eidos TTS (via external API) configured. API URL: {_eidos_tts_api_url}")
        else:
            logger.info("SPARK_TTS_API_URL not set. External TTS service will be disabled.")
            cls.EIDOS_TTS = None


        # Set derived directory paths
        cls.WILDCARDS_DIR = Path(cls.ONEIROS.get('wildcard_files_dir', str(PROJECT_ROOT / 'wildcards')))
        cls.IMAGE_OUTPUT_DIR = Path(cls.ONEIROS.get('image_output_dir', str(PROJECT_ROOT / 'eidos_dream_images')))


        # Ensure directories exist
        try:
            cls.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
            cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            if cls.ENABLE_ONEIROS:
                if cls.WILDCARDS_DIR: cls.WILDCARDS_DIR.mkdir(parents=True, exist_ok=True)
                if cls.ONEIROS and cls.ONEIROS.get('enable_image_dreams') and cls.IMAGE_OUTPUT_DIR:
                    cls.IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Ensured image output directory exists: {cls.IMAGE_OUTPUT_DIR}")
        except OSError as e:
            logger.error(f"Error creating project directories: {e}", exc_info=True)

        # Final validation checks
        if cls.HOME_ASSISTANT is None: logger.info("Home Assistant configuration not found or inactive.")
        else: logger.info("Home Assistant configuration found.")
        if cls.ENABLE_WOLFRAM_ALPHA and cls.WOLFRAM_ALPHA is None:
            logger.warning("ENABLE_WOLFRAM_ALPHA is True but WOLFRAM_ALPHA_APP_ID not set. Wolfram Alpha dependent tools will be disabled.")
        if cls.NEWS_API.get('enabled') and not cls.NEWS_API.get('api_key'):
            logger.warning("News API is enabled but NEWS_API_KEY is missing. News features will be disabled.")
            cls.NEWS_API['enabled'] = False
        if cls.ENABLE_WEB_SEARCH and cls.BRAVE_SEARCH is None:
            logger.warning("ENABLE_WEB_SEARCH is True but BRAVE_API_KEY is not set. Web search tool will be disabled.")
            cls.ENABLE_WEB_SEARCH = False # Update class attribute if dependent config is missing
        if not cls.EIDOS_ADMIN_PASSWORD:
            logger.warning("EIDOS_ADMIN_PASSWORD is not set. 'Clear All Eidos Memory' endpoint is unprotected.")
        if cls.ENABLE_ONEIROS and cls.ONEIROS:
            if not cls.ONEIROS.get('wildcard_files_dir'): logger.warning("ONEIROS_WILDCARD_FILES_DIR not set.")
            if cls.ONEIROS.get('enable_image_dreams'):
                if not cls.ONEIROS.get('stable_diffusion_url'): logger.warning("Image dreams enabled, but ONEIROS_STABLE_DIFFUSION_URL not set.")
                if not cls.ONEIROS.get('image_output_dir'): logger.warning("Image dreams enabled, but ONEIROS_IMAGE_OUTPUT_DIR not set.")
        if cls.ENABLE_KNOWLEDGE_UPKEEP and cls.ETHOS:
            if not isinstance(cls.ETHOS.get('knowledge_upkeep_volatile_tags'), list) or \
               not cls.ETHOS.get('knowledge_upkeep_llm_role'):
                logger.error("Knowledge Upkeep enabled but volatile_tags or llm_role misconfigured. Disabling.")
                cls.ENABLE_KNOWLEDGE_UPKEEP = False
        elif cls.ENABLE_KNOWLEDGE_UPKEEP:
            logger.error("Knowledge Upkeep enabled, but ETHOS config seems missing. Disabling.")
            cls.ENABLE_KNOWLEDGE_UPKEEP = False


        logger.info("Configuration attributes processed and validated.")
        cls._initialized = True

    @classmethod
    def get_llm_config(cls, llm_role: Union[Literal['PATHOS', 'LOGOS_VISION_CONTEXT', 'LOGOS_TECHNE', 'LOGOS_DEEP_RESEARCH'], str]) -> Optional[LLMConfig]:
        if not cls._initialized: cls.setup()
        # Cast llm_role to the Literal type if it's a string that matches one of the keys
        # This is more for type checker satisfaction if llm_role comes as a plain string.
        literal_role: Literal['PATHOS', 'LOGOS_VISION_CONTEXT', 'LOGOS_TECHNE', 'LOGOS_DEEP_RESEARCH']
        if llm_role in ['PATHOS', 'LOGOS_VISION_CONTEXT', 'LOGOS_TECHNE', 'LOGOS_DEEP_RESEARCH']:
            literal_role = llm_role # type: ignore
        else:
            logger.warning(f"LLM role '{llm_role}' not a predefined literal. Config lookup might fail or be less type-safe.")
            # Attempt to use it as a key anyway, but type checker might complain elsewhere
            config_val = cls.LLM.get(llm_role) # type: ignore
            if config_val and config_val.get('url'): return config_val # type: ignore
            logger.debug(f"LLM config for '{llm_role}' not found or URL missing.")
            return None

        config_val = cls.LLM.get(literal_role)
        if config_val and config_val.get('url'):
            return config_val
        logger.debug(f"LLM config for '{literal_role}' not found or URL missing.")
        return None

    @classmethod
    def get_ha_config(cls) -> Optional[HomeAssistantConfig]:
        if not cls._initialized: cls.setup()
        return cls.HOME_ASSISTANT

    @classmethod
    def get_voice_config(cls) -> VoiceConfig: # Not currently used by backend
        if not cls._initialized: cls.setup()
        return cls.VOICE # type: ignore

    @classmethod
    def get_ethos_config(cls) -> EthosConfig:
        if not cls._initialized: cls.setup()
        return cls.ETHOS

    @classmethod
    def get_oneiros_config(cls) -> OneirosConfig:
        if not cls._initialized: cls.setup()
        return cls.ONEIROS

    @classmethod
    def get_aisthesis_config(cls) -> AisthesisConfig: # Not currently used
        if not cls._initialized: cls.setup()
        return cls.AISTHESIS # type: ignore

    @classmethod
    def get_api_config(cls) -> APIConfig:
        if not cls._initialized: cls.setup()
        return cls.API # type: ignore

    @classmethod
    def get_wolfram_alpha_config(cls) -> Optional[WolframAlphaConfig]:
        if not cls._initialized: cls.setup()
        return cls.WOLFRAM_ALPHA if cls.ENABLE_WOLFRAM_ALPHA and cls.WOLFRAM_ALPHA else None

    @classmethod
    def get_news_api_config(cls) -> Optional[NewsApiConfig]:
        if not cls._initialized: cls.setup()
        news_api_dict = cls.NEWS_API
        if news_api_dict.get('enabled') and news_api_dict.get('api_key'):
            return news_api_dict
        return None

    @classmethod
    def get_brave_search_config(cls) -> Optional[BraveSearchConfig]:
        if not cls._initialized: cls.setup()
        return cls.BRAVE_SEARCH if cls.ENABLE_WEB_SEARCH and cls.BRAVE_SEARCH else None

    @classmethod
    def get_openweathermap_config(cls) -> Optional[OpenWeatherMapConfig]:
        if not cls._initialized: cls.setup()
        return cls.OPENWEATHERMAP

    @classmethod
    def get_eidos_tts_config(cls) -> Optional[EidosTTSConfig]: # New getter
        if not cls._initialized: cls.setup()
        return cls.EIDOS_TTS

    @classmethod
    def get_admin_password(cls) -> Optional[str]:
        if not cls._initialized: cls.setup()
        return cls.EIDOS_ADMIN_PASSWORD

# Call setup once when the module is first imported.
# This ensures that Config attributes are populated from .env
# before any other module tries to access them directly (e.g., Config.ETHOS).
Config.setup()