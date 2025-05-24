// webapp/js/main.js

// --- Configuration Constants & Global Settings Variables ---
import {
    EIDOS_API_BASE_URL_KEY, USER_ID_KEY, SYSTEM_PROMPT_KEY,
    WEATHER_LOCATION_KEY, EIDOS_API_KEY_KEY, MODEL_TEMPERATURE_KEY,
    EIDOS_CONTEXT_LENGTH_KEY, LLM_PROVIDER_URL_KEY, SELECTED_MODEL_KEY,
    DEFAULT_MODEL_TEMPERATURE, DEFAULT_CONTEXT_LENGTH, AUTO_TTS_ENABLED_KEY,
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

// --- Persistent Storage Function Imports ---
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
    fetchAndDisplayKnowledgeVerifications, fetchAndDisplayDailyBriefingGUI,
    fetchAndDisplayUserFacts
} from './ui_panels.js';

// --- UI Chat Function Imports ---
import {
    displayMessage as displayMessageInChat,
    displayProactiveMessageInPanel,
    setExpandChatInterfaceFunction as setExpandChatForUiChat,
    setDisplayMessageFunctionForProactive,
    stopAndClearTTSQueue,
    addAudioUrlToTTSQueue,
    playNextInTTSQueueIfIdle,
    getLatestAIMessageBubbleForTTS,
} from './ui_chat.js';

// --- Event Handler Setup ---
import { setupGlobalEventListeners, injectDependencies as injectEventHandlersDeps } from './event_handlers.js';


// --- Globally Accessible State (Managed by main.js) ---
export let currentUserId = "";
export let EIDOS_API_BASE_URL = ConfigApiUrlFromModule;
export let autoTtsEnabled = false; // For the GUI toggle

window.isAwaitingResponse = false; // True when waiting for LLM HTTP response
window.attachedDocumentText = null;
window.attachedDocumentName = null;
window.eidosWebSocket = null;
window.speechRecognitionInstance = null;
window.currentUserId = currentUserId;
window.EIDOS_API_BASE_URL = EIDOS_API_BASE_URL;
window.autoTtsEnabled = autoTtsEnabled; // GUI toggle state

// Flags for weather location context
window.isFirstMessageInSession = true;
window.weatherLocationChangedThisSession = false;


// --- Global State Setters ---
function setCurrentUserIdGlobal(newId) {
    if (newId && typeof newId === 'string' && newId.trim() !== "") {
        const normalizedNewId = newId.trim().toLowerCase().replace(/ /g, "_");
        if (normalizedNewId) {
            currentUserId = normalizedNewId;
            localStorage.setItem(USER_ID_KEY, normalizedNewId);
            window.currentUserId = normalizedNewId;
            console.log("Main.js: currentUserId updated to (normalized):", normalizedNewId);
            if (DOM.userIdInput) DOM.userIdInput.value = normalizedNewId;
            if (window.eidosWebSocket && window.eidosWebSocket.readyState === WebSocket.OPEN) {
                console.log("Main.js: User ID changed, re-authenticating WebSocket.");
                window.eidosWebSocket.send(JSON.stringify({ type: "auth", payload: { userId: currentUserId } }));
            }
            return;
        }
    }
    console.warn("Main.js: setCurrentUserIdGlobal - Invalid User ID. Using/keeping previous or default.", newId);
    if (!currentUserId) {
        currentUserId = "unknown_user";
        localStorage.setItem(USER_ID_KEY, currentUserId);
        window.currentUserId = currentUserId;
        if (DOM.userIdInput) DOM.userIdInput.value = currentUserId;
    }
}

function setGlobalApiBaseUrlGlobal(newUrl) {
    if (newUrl && typeof newUrl === 'string' && newUrl.startsWith('http')) {
        EIDOS_API_BASE_URL = newUrl;
        updateConfigApiBaseUrlFromModule(newUrl);
        window.EIDOS_API_BASE_URL = EIDOS_API_BASE_URL;
        console.log("Main.js: Global EIDOS_API_BASE_URL updated to:", EIDOS_API_BASE_URL);
        if (window.eidosWebSocket) {
            console.log("Main.js: API Base URL changed, reconnecting WebSocket.");
            connectWsApi();
        }
    } else {
        console.warn("Main.js: setGlobalApiBaseUrlGlobal - Invalid URL:", newUrl);
    }
}
function getGlobalApiBaseUrlGlobal() { return EIDOS_API_BASE_URL; }
function getApiKeyGlobal() { return localStorage.getItem(EIDOS_API_KEY_KEY) || ""; }
function setApiKeyGlobal(value) { const trimmedValue = value ? value.trim() : ""; if (trimmedValue) localStorage.setItem(EIDOS_API_KEY_KEY, trimmedValue); else localStorage.removeItem(EIDOS_API_KEY_KEY); console.log("Main.js: API Key updated.");}
function getLlmProviderUrlGlobal() { return localStorage.getItem(LLM_PROVIDER_URL_KEY) || ""; }
function setLlmProviderUrlGlobal(value) { const trimmedValue = value ? value.trim() : ""; if (trimmedValue) localStorage.setItem(LLM_PROVIDER_URL_KEY, trimmedValue); else localStorage.removeItem(LLM_PROVIDER_URL_KEY); console.log("Main.js: LLM Provider URL updated.");}
function getWeatherLocGlobal() { return localStorage.getItem(WEATHER_LOCATION_KEY) || ""; }
function setWeatherLocGlobal(value) { const oldLoc = getWeatherLocGlobal(); const trimmedValue = value ? value.trim() : ""; if (trimmedValue) localStorage.setItem(WEATHER_LOCATION_KEY, trimmedValue); else localStorage.removeItem(WEATHER_LOCATION_KEY); console.log("Main.js: Weather Location updated."); if (oldLoc !== trimmedValue) window.weatherLocationChangedThisSession = true; }
function getSystemPromptTextGlobal() { return localStorage.getItem(SYSTEM_PROMPT_KEY) || ""; }
function setSystemPromptTextGlobal(value) { localStorage.setItem(SYSTEM_PROMPT_KEY, value ? value.trim() : ""); console.log("Main.js: System Prompt updated."); }
function getModelTempGlobal() { return parseFloat(localStorage.getItem(MODEL_TEMPERATURE_KEY) || DEFAULT_MODEL_TEMPERATURE.toString()); }
function setModelTempGlobal(value) { localStorage.setItem(MODEL_TEMPERATURE_KEY, value.toString()); console.log("Main.js: Model Temperature updated."); }
function getContextLenGlobal() { const len = localStorage.getItem(EIDOS_CONTEXT_LENGTH_KEY); return len ? parseInt(len, 10) : null; }
function setContextLenGlobal(value) { if (value !== null && value !== undefined && value.toString().trim() !== "") localStorage.setItem(EIDOS_CONTEXT_LENGTH_KEY, value.toString()); else localStorage.removeItem(EIDOS_CONTEXT_LENGTH_KEY); console.log("Main.js: Context Length updated.");}

// --- Weather Panel Specific State & Functions ---
let weatherUpdateIntervalId = null;
function updateWeatherDisplay(weatherData) {
    if (!DOM.weatherPanel || !weatherData) return;
    DOM.weatherPanel.style.display = 'flex';
    if (DOM.weatherLocationDisplay) DOM.weatherLocationDisplay.textContent = weatherData.location || "N/A";
    if (DOM.weatherDescriptionDisplay) DOM.weatherDescriptionDisplay.textContent = weatherData.description || 'N/A';
    if (DOM.weatherTemperatureDisplay) DOM.weatherTemperatureDisplay.textContent = weatherData.temperature !== undefined && weatherData.temperature !== null ? `${weatherData.temperature}${weatherData.unit || '°'}` : 'N/A';
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
async function handleSendMessageUI(forceSearchPrefix = "") {
    await sendMessageApi(forceSearchPrefix);
}

function updateTtsToggleButtonState() {
    if (DOM.ttsToggleButton) {
        const svgElement = DOM.ttsToggleButton.querySelector('svg');
        if (!svgElement) return;
        if (window.autoTtsEnabled) {
            DOM.ttsToggleButton.classList.add('active');
            DOM.ttsToggleButton.title = "Auto TTS is ON (Click to turn OFF)";
            svgElement.innerHTML = `<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>`;
        } else {
            DOM.ttsToggleButton.classList.remove('active');
            DOM.ttsToggleButton.title = "Auto TTS is OFF (Click to turn ON)";
            svgElement.innerHTML = `<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line>`;
        }
    }
}

function toggleAutoTts() {
    autoTtsEnabled = !autoTtsEnabled;
    localStorage.setItem(AUTO_TTS_ENABLED_KEY, autoTtsEnabled.toString());
    window.autoTtsEnabled = autoTtsEnabled;
    updateTtsToggleButtonState();
    showNotification(`Auto TTS ${autoTtsEnabled ? 'Enabled' : 'Disabled'}.`);
    if (!autoTtsEnabled) {
        if (typeof stopAndClearTTSQueue === 'function') {
            stopAndClearTTSQueue();
        }
    }
}

// --- WebSocket Message Handler ---
window.handleWebSocketMessage = function(message) {
    console.log("Main.js handleWebSocketMessage received:", JSON.stringify(message).substring(0, 300) + "...");

    if (message.type === "unsolicited_message" && message.payload) {
        console.log("Main.js: Received unsolicited_message:", JSON.stringify(message.payload).substring(0, 200) + "...");
        if (typeof displayProactiveMessageInPanel === 'function') {
            displayProactiveMessageInPanel(message.payload.content, message.payload.metadata);
        }
        showNotification("New proactive message from Pathos!", "info");
    } else if (message.type === "tts_audio_chunk_ready" && message.payload) {
        console.log("Main.js: Received tts_audio_chunk_ready. URL:", message.payload.url, "Seq:", message.payload.sequence, "Text:", message.payload.text_for_indicator);
        
        if (typeof addAudioUrlToTTSQueue === 'function') {
            const chunkUrl = message.payload.url || "";
            // Check for prefixes set by the backend
            const isProactiveAudioChunk = message.payload.is_proactive_audio === true || chunkUrl.includes("/proactive_tts_"); // Use new flag from payload first
            const isMainChatAudioChunk = !isProactiveAudioChunk && chunkUrl.includes("/chat_tts_"); // If not proactive and has chat prefix

            let playThisChunkNow = false;
            let bubbleToAssociateWith = null;
            const latestAiBubble = getLatestAIMessageBubbleForTTS ? getLatestAIMessageBubbleForTTS() : null;

            if (isMainChatAudioChunk) {
                if (latestAiBubble && latestAiBubble.dataset.ttsExpected === 'true') {
                    bubbleToAssociateWith = latestAiBubble;
                } else {
                    console.warn("tts_audio_chunk_ready (main chat): No latest AI bubble marked ttsExpected. Chunk will be queued without specific bubble association for indicator initially.");
                }
                if (window.autoTtsEnabled) {
                    playThisChunkNow = true; 
                    // window.currentlyPlayingMainChatTTS is set by displayMessage or proactive click handler when initiating
                    console.log("tts_audio_chunk_ready: Marked for potential immediate play (main chat, autoTts ON).");
                } else {
                    console.log("tts_audio_chunk_ready: Queued for main chat, but autoTts OFF, no immediate play.");
                }
            } else if (isProactiveAudioChunk) {
                bubbleToAssociateWith = null; 
                playThisChunkNow = false; 
                console.log("tts_audio_chunk_ready: Queued proactive audio chunk. No immediate play from here.");
            } else {
                bubbleToAssociateWith = null;
                playThisChunkNow = false;
                console.log("tts_audio_chunk_ready: Chunk URL prefix not recognized or not for active TTS. Queued, no immediate play.");
            }

            addAudioUrlToTTSQueue(
                message.payload.url,
                message.payload.sequence,
                message.payload.text_for_indicator,
                bubbleToAssociateWith
            );

            if (playThisChunkNow && typeof playNextInTTSQueueIfIdle === 'function') {
                console.log("tts_audio_chunk_ready: Calling playNextInTTSQueueIfIdle() for main chat chunk.");
                playNextInTTSQueueIfIdle();
            }
        }
    } else if (message.type === "status" && message.payload && message.payload.message) {
        console.log("Eidos Status via WebSocket:", message.payload.message);
    } else if (message.type === "error" && message.payload && message.payload.message) {
        console.error("Eidos WebSocket Error:", message.payload.message);
        showNotification(`Eidos Error (WS): ${message.payload.message}`, "error");
    }
};


// --- DOMContentLoaded: Main Application Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded. Initializing Eidos GUI (main.js)...");

    const savedApiUrl = localStorage.getItem(EIDOS_API_BASE_URL_KEY);
    if (savedApiUrl && savedApiUrl.trim() !== "") setGlobalApiBaseUrlGlobal(savedApiUrl);
    else setGlobalApiBaseUrlGlobal(ConfigApiUrlFromModule);
    if (DOM.apiUrlInput) DOM.apiUrlInput.value = EIDOS_API_BASE_URL;

    const savedUserId = localStorage.getItem(USER_ID_KEY);
    if (savedUserId && savedUserId.trim() !== "") setCurrentUserIdGlobal(savedUserId);
    else setCurrentUserIdGlobal(`user_${Math.random().toString(36).substring(2, 9)}`);

    if (DOM.apiKeyInput) DOM.apiKeyInput.value = getApiKeyGlobal();
    if (DOM.llmProviderUrlInput) DOM.llmProviderUrlInput.value = getLlmProviderUrlGlobal();
    if (DOM.weatherLocationInput) DOM.weatherLocationInput.value = getWeatherLocGlobal();
    if (DOM.systemPromptInput) DOM.systemPromptInput.value = getSystemPromptTextGlobal();
    if (DOM.modelTemperatureInput) DOM.modelTemperatureInput.value = getModelTempGlobal().toString();
    const savedContextLen = getContextLenGlobal();
    if (DOM.contextLengthInput) { if (savedContextLen !== null) DOM.contextLengthInput.value = savedContextLen.toString(); }

    const savedAutoTts = localStorage.getItem(AUTO_TTS_ENABLED_KEY);
    if (savedAutoTts !== null) autoTtsEnabled = (savedAutoTts === 'true');
    window.autoTtsEnabled = autoTtsEnabled;
    updateTtsToggleButtonState();
    if (DOM.ttsToggleButton) DOM.ttsToggleButton.addEventListener('click', toggleAutoTts);

    // --- Inject Dependencies ---
    setDisplayMessageForStorage(displayMessageInChat);
    setLayoutFunctionsForStorage(initCleanInterface, expandChatInterface, hideAttachedDocumentIndicator);
    setSelectModelForStorage(selectModel);
    setApiCommsDependencies({ displayMessageInChat, displayProactiveMessageInPanel, hideAttachedDocumentIndicator, expandChatInterface, scrollToBottom, chatMessagesArea: DOM.chatMessagesArea });
    setCloseAllSidePanelsFunction(closeAllSidePanels);
    setExpandChatForUiChat(expandChatInterface);
    setDisplayMessageFunctionForProactive(displayMessageInChat);
    injectEventHandlersDeps({
        sendMessage: handleSendMessageUI, handleDocumentUploadAPI, handleImageUploadClientSide,
        removeAttachedDocument, toggleListening: toggleListeningStt, resetChat: resetChatStorage,
        clearAllLocalChatHistory, saveSettingsToBackendAPI, clearUserBackendMemoryAPI,
        clearEidosBackendMemoryAPI, fetchModels, fetchWeatherAPI, setupWeatherUpdates: setupWeatherUpdatesGlobal,
        fetchAndDisplayDailyBriefingGUI, fetchAndDisplayLearnings, fetchAndDisplayDreams,
        fetchAndDisplayKnowledgeVerifications, fetchAndDisplayUserFacts,
        currentUserId: () => currentUserId, EIDOS_API_BASE_URL_GLOBAL: getGlobalApiBaseUrlGlobal,
        setCurrentUserId: setCurrentUserIdGlobal, setGlobalApiBaseUrl: setGlobalApiBaseUrlGlobal,
        setAPIKey: setApiKeyGlobal, setLLMProviderUrl: setLlmProviderUrlGlobal,
        setWeatherLoc: setWeatherLocGlobal, setSystemPrompt: setSystemPromptTextGlobal,
        setModelTemp: setModelTempGlobal, setContextLen: setContextLenGlobal
    });

    // --- Initialize UI and Services ---
    if (DOM.userInput) { DOM.userInput.focus(); DOM.userInput.addEventListener('input', () => autoAdjustTextareaHeight(DOM.userInput)); autoAdjustTextareaHeight(DOM.userInput); }
    const chatWasLoaded = loadCurrentActiveChatOnStartup();
    if (!chatWasLoaded) initCleanInterface(); else expandChatInterface();
    initializePanelConfigurations({ renderHistoryPanel, fetchLearnings: fetchAndDisplayLearnings, fetchDreams: fetchAndDisplayDreams, fetchKnowledgeVerifications: fetchAndDisplayKnowledgeVerifications, fetchDailyBriefing: fetchAndDisplayDailyBriefingGUI, fetchUserFacts: fetchAndDisplayUserFacts });
    setupPanelEventListeners();
    setupGlobalEventListeners();
    fetchModels();
    window.speechRecognitionInstance = initializeSpeechRecognition();
    connectWsApi();
    window.connectWebSocket = connectWsApi;
    setupWeatherUpdatesGlobal();

    if (typeof Prism !== 'undefined' && Prism.plugins && Prism.plugins.autoloader) Prism.plugins.autoloader.languages_path = 'https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/';
    else console.warn("Prism autoloader not found.");

    window.displayMessageInChat = displayMessageInChat;
    window.showNotification = showNotification;
    window.renderHistoryPanel = renderHistoryPanel;
    window.openResponseEditor = (text, bubble) => { console.log("Response editor called for:", text, "on bubble:", bubble); showNotification("Edit & Resubmit feature coming soon!", "info"); };
    window.showAttachedDocumentIndicator = showAttachedDocumentIndicator;

    console.log("Eidos GUI Initialization complete (main.js).");
});

window.addEventListener('beforeunload', saveCurrentActiveChat);
console.log("main.js loaded and executing.");