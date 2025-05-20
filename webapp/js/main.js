// webapp/js/main.js

// --- Configuration Constants & Global Settings Variables ---
import {
    EIDOS_API_BASE_URL_KEY, USER_ID_KEY, SYSTEM_PROMPT_KEY,
    WEATHER_LOCATION_KEY, EIDOS_API_KEY_KEY, MODEL_TEMPERATURE_KEY,
    EIDOS_CONTEXT_LENGTH_KEY, LLM_PROVIDER_URL_KEY, SELECTED_MODEL_KEY,
    AUTO_TTS_ENABLED_KEY, // Import the key for auto TTS
    DEFAULT_MODEL_TEMPERATURE, DEFAULT_CONTEXT_LENGTH,
    EIDOS_API_BASE_URL as ConfigApiUrlFromModule,
    updateApiBaseUrl as updateConfigApiBaseUrlFromModule,
    updateWebSocketUrl as updateConfigWsUrlFromModule
} from './config.js';

// --- DOM Element Imports ---
import * as DOM from './dom_elements.js';

// --- Utility Function Imports ---
import { showNotification, autoAdjustTextareaHeight, scrollToBottom } from './utils.js';

// --- UI Layout Function Imports ---
import {
    initCleanInterface, expandChatInterface, removeAttachedDocument,
    showAttachedDocumentIndicator, hideAttachedDocumentIndicator,
    setCloseAllSidePanelsFunction
} from './ui_layout.js';

// --- Persistent Storage Function Imports (and conversationHistory) ---
import {
    conversationHistory, saveCurrentActiveChat, archiveCurrentChatToHistory,
    loadCurrentActiveChatOnStartup, clearAllLocalChatHistory,
    resetChat as resetChatStorage,
    setDisplayMessageFunction as setDisplayMessageForStorage,
    setLayoutFunctions as setLayoutFunctionsForStorage,
    setSelectModelFunction as setSelectModelForStorage
} from './persistent_storage.js';

// --- API Communication Function Imports ---
import {
    fetchModels, sendMessage as sendMessageApi, handleDocumentUploadAPI,
    handleImageUploadClientSide, saveSettingsToBackendAPI,
    clearUserBackendMemoryAPI, clearEidosBackendMemoryAPI, fetchWeatherAPI,
    connectWebSocket as connectWsApi, selectModel,
    setApiCommsDependencies
} from './api_comms.js';

// --- STT Function Imports ---
import { initializeSpeechRecognition, toggleListening as toggleListeningStt } from './stt.js';

// --- Panel Management Function Imports ---
import {
    initializePanelConfigurations, setupPanelEventListeners, closeAllSidePanels
} from './panel_manager.js';

// --- UI Panel Content Function Imports ---
import {
    renderHistoryPanel, fetchAndDisplayLearnings, fetchAndDisplayDreams,
    fetchAndDisplayKnowledgeVerifications, fetchAndDisplayDailyBriefingGUI
} from './ui_panels.js';

// --- UI Chat Function Imports ---
import {
    displayMessage as displayMessageInChat,
    displayProactiveMessageInPanel,
    setExpandChatInterfaceFunction as setExpandChatForUiChat,
    setDisplayMessageFunctionForProactive,
    stopAndClearTTSQueue // Import function to stop TTS
} from './ui_chat.js';

// --- Event Handler Setup ---
import { setupGlobalEventListeners, injectDependencies as injectEventHandlersDeps } from './event_handlers.js';


// --- Globally Accessible State (Managed by main.js) ---
export let currentUserId = "";
export let EIDOS_API_BASE_URL = ConfigApiUrlFromModule;
export let autoTtsEnabled = false; // Default to off

// Make global state available on window
window.isAwaitingResponse = false;
window.attachedDocumentText = null;
window.attachedDocumentName = null;
window.eidosWebSocket = null;
window.speechRecognitionInstance = null;
window.currentUserId = currentUserId;
window.EIDOS_API_BASE_URL = EIDOS_API_BASE_URL;
window.autoTtsEnabled = autoTtsEnabled; // Initialize on window

// --- Global State Setters ---
function setCurrentUserIdGlobal(newId) {
    if (newId && typeof newId === 'string') {
        currentUserId = newId;
        localStorage.setItem(USER_ID_KEY, currentUserId);
        window.currentUserId = currentUserId;
        console.log("Global currentUserId updated to:", currentUserId);
    }
}
function setGlobalApiBaseUrlGlobal(newUrl) {
    if (newUrl && typeof newUrl === 'string' && newUrl.startsWith('http')) {
        EIDOS_API_BASE_URL = newUrl;
        updateConfigApiBaseUrlFromModule(newUrl);
        window.EIDOS_API_BASE_URL = EIDOS_API_BASE_URL;
        let wsBase = newUrl.replace(/^http/, 'ws').replace(/\/v1\/?$/, '');
        if (!wsBase.endsWith('/')) wsBase = wsBase.replace(/\/ws$/, '');
        updateConfigWsUrlFromModule(`${wsBase}/ws`);
        console.log("Global EIDOS_API_BASE_URL updated to:", EIDOS_API_BASE_URL);
    }
}
function getGlobalApiBaseUrlGlobal() { return EIDOS_API_BASE_URL; }
function getApiKeyGlobal() { return localStorage.getItem(EIDOS_API_KEY_KEY) || ""; }
function setApiKeyGlobal(value) { if (value) localStorage.setItem(EIDOS_API_KEY_KEY, value); else localStorage.removeItem(EIDOS_API_KEY_KEY); }
function getLlmProviderUrlGlobal() { return localStorage.getItem(LLM_PROVIDER_URL_KEY) || ""; }
function setLlmProviderUrlGlobal(value) { if (value) localStorage.setItem(LLM_PROVIDER_URL_KEY, value); else localStorage.removeItem(LLM_PROVIDER_URL_KEY); }
function getWeatherLocGlobal() { return localStorage.getItem(WEATHER_LOCATION_KEY) || ""; }
function setWeatherLocGlobal(value) { if (value) localStorage.setItem(WEATHER_LOCATION_KEY, value); else localStorage.removeItem(WEATHER_LOCATION_KEY); }
function getSystemPromptTextGlobal() { return localStorage.getItem(SYSTEM_PROMPT_KEY) || ""; }
function setSystemPromptTextGlobal(value) { localStorage.setItem(SYSTEM_PROMPT_KEY, value); }
function getModelTempGlobal() { return parseFloat(localStorage.getItem(MODEL_TEMPERATURE_KEY) || DEFAULT_MODEL_TEMPERATURE.toString()); }
function setModelTempGlobal(value) { localStorage.setItem(MODEL_TEMPERATURE_KEY, value.toString()); }
function getContextLenGlobal() { const len = localStorage.getItem(EIDOS_CONTEXT_LENGTH_KEY); return len ? parseInt(len, 10) : null; }
function setContextLenGlobal(value) { if (value !== null) localStorage.setItem(EIDOS_CONTEXT_LENGTH_KEY, value.toString()); else localStorage.removeItem(EIDOS_CONTEXT_LENGTH_KEY); }

// --- TTS Toggle Functionality ---
function updateTtsToggleButtonState() {
    if (DOM.ttsToggleButton) {
        const svgElement = DOM.ttsToggleButton.querySelector('svg');
        if (!svgElement) return;

        if (autoTtsEnabled) {
            DOM.ttsToggleButton.classList.add('active');
            DOM.ttsToggleButton.title = "Auto TTS is ON (Click to turn OFF)";
            svgElement.innerHTML = `
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>`;
        } else {
            DOM.ttsToggleButton.classList.remove('active');
            DOM.ttsToggleButton.title = "Auto TTS is OFF (Click to turn ON)";
            svgElement.innerHTML = `
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                <line x1="23" y1="9" x2="17" y2="15"></line>
                <line x1="17" y1="9" x2="23" y2="15"></line>`;
        }
    }
}

function toggleAutoTts() {
    autoTtsEnabled = !autoTtsEnabled;
    localStorage.setItem(AUTO_TTS_ENABLED_KEY, autoTtsEnabled.toString());
    window.autoTtsEnabled = autoTtsEnabled; // Update window property
    updateTtsToggleButtonState();
    showNotification(`Auto TTS ${autoTtsEnabled ? 'Enabled' : 'Disabled'}.`);
    if (!autoTtsEnabled) {
        stopAndClearTTSQueue(); // Call the imported function from ui_chat.js
    }
}
// window.toggleAutoTts = toggleAutoTts; // Not strictly needed if listener is set up in main.js

// --- Weather Panel Specific State & Functions ---
let weatherUpdateIntervalId = null;
function updateWeatherDisplay(weatherData) {
    if (!DOM.weatherPanel || !weatherData) return;
    DOM.weatherPanel.style.display = 'flex';
    if (DOM.weatherLocationDisplay) DOM.weatherLocationDisplay.textContent = weatherData.location || "N/A";
    if (DOM.weatherDescriptionDisplay) DOM.weatherDescriptionDisplay.textContent = weatherData.description || 'N/A';
    if (DOM.weatherTemperatureDisplay) {
        let tempText = '--';
        if (weatherData.temperature !== undefined && weatherData.temperature !== null) {
            tempText = `${weatherData.temperature}°`;
            if (weatherData.unit) tempText += weatherData.unit;
        } else if (weatherData.temperature_celsius !== undefined && weatherData.temperature_celsius !== null) {
            tempText = `${weatherData.temperature_celsius}°C`;
        }
        DOM.weatherTemperatureDisplay.textContent = tempText;
    }
    if (DOM.weatherHumidityDisplay) DOM.weatherHumidityDisplay.textContent = weatherData.humidity ? `Humidity: ${weatherData.humidity}` : '';
    if (DOM.weatherWindDisplay) DOM.weatherWindDisplay.textContent = weatherData.wind_speed ? `Wind: ${weatherData.wind_speed}` : '';
    if (DOM.weatherLastUpdatedDisplay) DOM.weatherLastUpdatedDisplay.textContent = `Updated: ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}
window.updateWeatherDisplay = updateWeatherDisplay;

function setupWeatherUpdatesGlobal() {
    if (weatherUpdateIntervalId !== null) clearInterval(weatherUpdateIntervalId);
    const location = getWeatherLocGlobal();
    if (location && location.trim()) {
        fetchWeatherAPI(location).then(data => { if (data) updateWeatherDisplay(data); });
    } else {
        if (DOM.weatherPanel) DOM.weatherPanel.style.display = 'none';
    }
}

// --- UI Interaction Orchestration ---
async function handleSendMessageUI() {
    let tempAiMessageBubble = null;
    if (typeof displayMessageInChat === 'function') {
        tempAiMessageBubble = displayMessageInChat("AI", "Processing...");
    }

    const apiResult = await sendMessageApi();

    if (tempAiMessageBubble && tempAiMessageBubble.parentNode === DOM.chatMessagesArea) {
        DOM.chatMessagesArea.removeChild(tempAiMessageBubble);
    }
    // sendMessageApi now calls displayMessageInChat for the final AI response.
    // We just need to ensure scrolling.
    if (DOM.chatMessagesArea) scrollToBottom(DOM.chatMessagesArea);
}


// --- DOMContentLoaded: Main Application Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded. Initializing Eidos GUI (main.js)...");

    if (DOM.apiUrlInput) DOM.apiUrlInput.value = EIDOS_API_BASE_URL;
    const savedUserId = localStorage.getItem(USER_ID_KEY);
    if (savedUserId) setCurrentUserIdGlobal(savedUserId);
    else setCurrentUserIdGlobal(`user_${Math.random().toString(36).substring(2, 9)}`);
    if (DOM.userIdInput) DOM.userIdInput.value = currentUserId;

    if (DOM.apiKeyInput) DOM.apiKeyInput.value = getApiKeyGlobal();
    if (DOM.llmProviderUrlInput) DOM.llmProviderUrlInput.value = getLlmProviderUrlGlobal();
    if (DOM.weatherLocationInput) DOM.weatherLocationInput.value = getWeatherLocGlobal();
    if (DOM.systemPromptInput) DOM.systemPromptInput.value = getSystemPromptTextGlobal();
    if (DOM.modelTemperatureInput) DOM.modelTemperatureInput.value = getModelTempGlobal().toString();
    const savedContextLen = getContextLenGlobal();
    if (DOM.contextLengthInput) {
        if (savedContextLen !== null) DOM.contextLengthInput.value = savedContextLen.toString();
        else DOM.contextLengthInput.placeholder = `e.g., ${DEFAULT_CONTEXT_LENGTH}`;
    }

    const savedAutoTts = localStorage.getItem(AUTO_TTS_ENABLED_KEY);
    if (savedAutoTts !== null) {
        autoTtsEnabled = (savedAutoTts === 'true');
        window.autoTtsEnabled = autoTtsEnabled; // Ensure window global is also updated
    }
    updateTtsToggleButtonState();

    if (DOM.ttsToggleButton) { // Set up listener for TTS toggle
        DOM.ttsToggleButton.addEventListener('click', toggleAutoTts);
    }

    setDisplayMessageForStorage(displayMessageInChat);
    setLayoutFunctionsForStorage(initCleanInterface, expandChatInterface, hideAttachedDocumentIndicator);
    setSelectModelForStorage(selectModel);
    setApiCommsDependencies({
        displayMessageInChat: displayMessageInChat,
        displayProactiveMessageInPanel: displayProactiveMessageInPanel,
        hideAttachedDocumentIndicator: hideAttachedDocumentIndicator,
        expandChatInterface: expandChatInterface,
        scrollToBottom: scrollToBottom,
        chatMessagesArea: DOM.chatMessagesArea
    });
    setCloseAllSidePanelsFunction(closeAllSidePanels);
    setExpandChatForUiChat(expandChatInterface);
    setDisplayMessageFunctionForProactive(displayMessageInChat);

    injectEventHandlersDeps({
        sendMessage: handleSendMessageUI,
        handleDocumentUploadAPI: handleDocumentUploadAPI,
        handleImageUploadClientSide: handleImageUploadClientSide,
        removeAttachedDocument: removeAttachedDocument,
        toggleListening: toggleListeningStt,
        resetChat: resetChatStorage,
        clearAllLocalChatHistory: clearAllLocalChatHistory,
        saveSettingsToBackendAPI: saveSettingsToBackendAPI,
        clearUserBackendMemoryAPI: clearUserBackendMemoryAPI,
        clearEidosBackendMemoryAPI: clearEidosBackendMemoryAPI,
        fetchModels: fetchModels,
        fetchWeatherAPI: fetchWeatherAPI,
        setupWeatherUpdates: setupWeatherUpdatesGlobal,
        fetchAndDisplayDailyBriefingGUI: fetchAndDisplayDailyBriefingGUI,
        fetchAndDisplayLearnings: fetchAndDisplayLearnings,
        fetchAndDisplayDreams: fetchAndDisplayDreams,
        fetchAndDisplayKnowledgeVerifications: fetchAndDisplayKnowledgeVerifications,
        currentUserId: () => currentUserId,
        EIDOS_API_BASE_URL_GLOBAL: getGlobalApiBaseUrlGlobal,
        setCurrentUserId: setCurrentUserIdGlobal,
        setGlobalApiBaseUrl: setGlobalApiBaseUrlGlobal,
        setAPIKey: setApiKeyGlobal,
        setLLMProviderUrl: setLlmProviderUrlGlobal,
        setWeatherLoc: setWeatherLocGlobal,
        setSystemPrompt: setSystemPromptTextGlobal,
        setModelTemp: setModelTempGlobal,
        setContextLen: setContextLenGlobal
    });

    const chatWasLoaded = loadCurrentActiveChatOnStartup();
    if (!chatWasLoaded) initCleanInterface();
    else expandChatInterface();

    initializePanelConfigurations({
        renderHistoryPanel: renderHistoryPanel,
        fetchLearnings: fetchAndDisplayLearnings,
        fetchDreams: fetchAndDisplayDreams,
        fetchKnowledgeVerifications: fetchAndDisplayKnowledgeVerifications,
        fetchDailyBriefing: fetchAndDisplayDailyBriefingGUI
    });
    setupPanelEventListeners();
    setupGlobalEventListeners();

    fetchModels();
    window.speechRecognitionInstance = initializeSpeechRecognition();

    connectWsApi();
    window.connectWebSocket = connectWsApi;

    setupWeatherUpdatesGlobal();

    if (typeof Prism !== 'undefined') {
        Prism.plugins.autoloader.languages_path = 'https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/';
    }

    window.displayMessageInChat = displayMessageInChat;
    window.showNotification = showNotification;
    window.renderHistoryPanel = renderHistoryPanel;
    window.openResponseEditor = (text, bubble) => {
        console.log("Response editor called for:", text, "on bubble:", bubble);
        showNotification("Edit & Resubmit feature coming soon!", "info");
    };

    console.log("Eidos GUI Initialization complete (main.js).");
});

window.addEventListener('beforeunload', saveCurrentActiveChat);

console.log("main.js loaded and executing.");