// webapp/js/config.js

// --- localStorage Keys ---
export const CHAT_HISTORY_KEY = 'eidosChatHistoryArchive';
export const CURRENT_CHAT_KEY = 'eidosCurrentActiveChat';
export const USER_ID_KEY = 'eidosUserId'; // Key for storing the User ID
export const SYSTEM_PROMPT_KEY = 'eidosSystemPrompt';
export const EIDOS_API_BASE_URL_KEY = 'eidosApiBaseUrl'; // Key for storing Eidos API Base URL
export const WEATHER_LOCATION_KEY = 'eidosWeatherLocation';
export const EIDOS_API_KEY_KEY = 'eidosApiKey';
export const MODEL_TEMPERATURE_KEY = 'eidosModelTemperature';
export const EIDOS_CONTEXT_LENGTH_KEY = 'eidosContextLength';
export const LLM_PROVIDER_URL_KEY = 'eidosLlmProviderUrl';
export const SELECTED_MODEL_KEY = 'eidosSelectedModel';
export const AUTO_TTS_ENABLED_KEY = 'eidosAutoTtsEnabled'; // For TTS toggle persistence

// --- Initial Configuration Values ---

// Eidos API Base URL: Load from localStorage or use a sensible default.
// The default should be what a typical local setup would use.
export let EIDOS_API_BASE_URL = localStorage.getItem(EIDOS_API_BASE_URL_KEY) || "http://127.0.0.1:8088/v1";

// WebSocket URL: Derived from EIDOS_API_BASE_URL for consistency.
let initialWsBase = EIDOS_API_BASE_URL.replace(/^http/, 'ws').replace(/\/v1\/?$/, '');
if (initialWsBase.endsWith('/ws')) { // Avoid double /ws if base URL already somehow includes it
    initialWsBase = initialWsBase.substring(0, initialWsBase.length - 3);
}
if (!initialWsBase.endsWith('/')) { // Ensure it ends with a slash before adding ws
    // This logic might be too aggressive if the base URL is just the host:port
    // Let's simplify: assume base URL is like http://host:port or http://host:port/
    // And we always want ws://host:port/ws
    let wsHostPort = EIDOS_API_BASE_URL.replace(/^http(s?):\/\//, '').replace(/\/v1\/?$/, '');
    initialWsBase = `ws${EIDOS_API_BASE_URL.startsWith('https') ? 's' : ''}://${wsHostPort}`;
}
export let EIDOS_WS_URL = `${initialWsBase.replace(/\/+$/, '')}/ws`;


// --- Functions to Update Configuration Variables (and localStorage where appropriate) ---

export function updateApiBaseUrl(newUrl) {
    if (newUrl && typeof newUrl === 'string' && newUrl.startsWith('http')) {
        EIDOS_API_BASE_URL = newUrl;
        localStorage.setItem(EIDOS_API_BASE_URL_KEY, newUrl); // Persist this change
        console.log("config.js: EIDOS_API_BASE_URL updated in module and localStorage to:", EIDOS_API_BASE_URL);

        // Automatically update WebSocket URL when API base URL changes
        let wsHostPort = newUrl.replace(/^http(s?):\/\//, '').replace(/\/v1\/?$/, '');
        const newWsBase = `ws${newUrl.startsWith('https') ? 's' : ''}://${wsHostPort}`;
        updateWebSocketUrl(`${newWsBase.replace(/\/+$/, '')}/ws`);
    } else {
        console.warn("config.js: Attempted to update API base URL with invalid value:", newUrl);
    }
}

export function updateWebSocketUrl(newWsUrl) {
    if (newWsUrl && typeof newWsUrl === 'string' && newWsUrl.startsWith('ws')) {
        EIDOS_WS_URL = newWsUrl;
        // Optional: If you want WS URL to be independently configurable and persistent:
        // localStorage.setItem('eidosWsUrl', newWsUrl);
        console.log("config.js: EIDOS_WS_URL updated in module to:", EIDOS_WS_URL);
    } else {
        console.warn("config.js: Invalid WebSocket URL provided:", newWsUrl);
    }
}

// --- Other Constants ---
export const THINK_TAG_PLACEHOLDER_PREFIX = "<!-- THINK_BLOCK_";
export const THINK_TAG_PLACEHOLDER_SUFFIX = "_END -->";

export const DEFAULT_LOG_FETCH_LIMIT = 20;
export const DEFAULT_MAX_HISTORY_ITEMS = 50;
export const DEFAULT_MODEL_TEMPERATURE = 0.7;
export const DEFAULT_CONTEXT_LENGTH = 4096; // Default if not set by user
export const MIN_CONTEXT_LENGTH = 256;
export const MAX_CONTEXT_LENGTH = 32000; // Example max, adjust as needed

// --- Initial Log Messages ---
console.log("config.js loaded.");
console.log("  Initial EIDOS_API_BASE_URL (from localStorage or default):", EIDOS_API_BASE_URL);
console.log("  Initial EIDOS_WS_URL (derived):", EIDOS_WS_URL);
const storedUserId = localStorage.getItem(USER_ID_KEY);
console.log("  Initial USER_ID_KEY check in localStorage:", storedUserId ? `Found '${storedUserId}'` : "Not found");