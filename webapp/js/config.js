// webapp/js/config.js

// localStorage Keys
export const CHAT_HISTORY_KEY = 'eidosChatHistoryArchive';
export const CURRENT_CHAT_KEY = 'eidosCurrentActiveChat';
export const USER_ID_KEY = 'eidosUserId';
export const SYSTEM_PROMPT_KEY = 'eidosSystemPrompt';
export const EIDOS_API_BASE_URL_KEY = 'eidosApiBaseUrl'; // Key for localStorage
export const WEATHER_LOCATION_KEY = 'eidosWeatherLocation';
export const EIDOS_API_KEY_KEY = 'eidosApiKey';
export const MODEL_TEMPERATURE_KEY = 'eidosModelTemperature';
export const EIDOS_CONTEXT_LENGTH_KEY = 'eidosContextLength';
export const LLM_PROVIDER_URL_KEY = 'eidosLlmProviderUrl';
export const SELECTED_MODEL_KEY = 'eidosSelectedModel';

// API Base URL
// Provide a sensible default if localStorage is empty
export let EIDOS_API_BASE_URL = localStorage.getItem(EIDOS_API_BASE_URL_KEY) || "http://127.0.0.1:8088/v1";

// WebSocket URL
// Deriving from EIDOS_API_BASE_URL is generally better to keep them in sync.
// Let main.js handle updating this when EIDOS_API_BASE_URL changes.
let initialWsBase = EIDOS_API_BASE_URL.replace(/^http/, 'ws').replace(/\/v1\/?$/, '');
if (!initialWsBase.endsWith('/')) initialWsBase = initialWsBase.replace(/\/ws$/, ''); // Clean up potential /ws suffix
export let EIDOS_WS_URL = `${initialWsBase}/ws`;


// Functions to update URLs from settings
export function updateApiBaseUrl(newUrl) {
    if (newUrl && typeof newUrl === 'string' && newUrl.startsWith('http')) {
        EIDOS_API_BASE_URL = newUrl;
        localStorage.setItem(EIDOS_API_BASE_URL_KEY, newUrl); // <<< --- THIS LINE IS CRITICAL ---
        console.log("config.js: EIDOS_API_BASE_URL updated in module and localStorage to:", EIDOS_API_BASE_URL);

        // Also update WebSocket URL when API base URL changes
        let wsBase = newUrl.replace(/^http/, 'ws').replace(/\/v1\/?$/, '');
        if (!wsBase.endsWith('/')) wsBase = wsBase.replace(/\/ws$/, '');
        updateWebSocketUrl(`${wsBase}/ws`);

    } else {
        console.warn("config.js: Attempted to update API base URL with invalid value:", newUrl);
    }
}

export function updateWebSocketUrl(newWsUrl) {
    if (newWsUrl && typeof newWsUrl === 'string' && newWsUrl.startsWith('ws')) {
        EIDOS_WS_URL = newWsUrl;
        // Optional: Save to localStorage if you want WS URL to be independently configurable,
        // but deriving it is usually safer.
        // localStorage.setItem('eidosWsUrl', newWsUrl);
        console.log("config.js: EIDOS_WS_URL updated in module to:", EIDOS_WS_URL);
    } else {
        console.warn("config.js: Invalid WebSocket URL provided:", newWsUrl);
    }
}

// Constants
export const THINK_TAG_PLACEHOLDER_PREFIX = "<!-- THINK_BLOCK_";
export const THINK_TAG_PLACEHOLDER_SUFFIX = "_END -->";

export const DEFAULT_LOG_FETCH_LIMIT = 20;
export const DEFAULT_MAX_HISTORY_ITEMS = 50;
export const DEFAULT_MODEL_TEMPERATURE = 0.7;
export const DEFAULT_CONTEXT_LENGTH = 4096;
export const MIN_CONTEXT_LENGTH = 256;
export const MAX_CONTEXT_LENGTH = 32000;
export const AUTO_TTS_ENABLED_KEY = 'eidosAutoTtsEnabled';

console.log("config.js loaded. Initial EIDOS_API_BASE_URL from localStorage (or default):", EIDOS_API_BASE_URL);
console.log("config.js loaded. Initial EIDOS_WS_URL derived:", EIDOS_WS_URL);