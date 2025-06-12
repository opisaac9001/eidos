// webapp/js/main.js

// --- Configuration Constants & Global Settings Variables ---
import {
    EIDOS_API_BASE_URL_KEY, USER_ID_KEY, SYSTEM_PROMPT_KEY,
    WEATHER_LOCATION_KEY, EIDOS_API_KEY_KEY, MODEL_TEMPERATURE_KEY,
    EIDOS_CONTEXT_LENGTH_KEY, LLM_PROVIDER_URL_KEY, SELECTED_MODEL_KEY,
    DEFAULT_MODEL_TEMPERATURE, DEFAULT_CONTEXT_LENGTH, AUTO_TTS_ENABLED_KEY,
    EIDOS_API_BASE_URL as ConfigApiUrlFromModule,
    updateApiBaseUrl as updateConfigApiBaseUrlFromModule,
    updateWebSocketUrl as updateConfigWsUrlFromModule,
    EIDOS_ADMIN_PASSWORD_KEY // NEW: Import admin password key
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
    addPathosEventAPI, // NEW: Import addPathosEventAPI
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
    fetchAndDisplayUserFacts,
    fetchAndDisplayPathosChronosData
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
    isCurrentlyPlayingMainChatTTS // <<<< ENSURE THIS LINE IS PRESENT AND CORRECT
} from './ui_chat.js';

// --- Event Handler Setup ---
import { setupGlobalEventListeners, injectDependencies as injectEventHandlersDeps } from './event_handlers.js';


// --- Globally Accessible State (Managed by main.js) ---
export let currentUserId = "";
export let EIDOS_API_BASE_URL = ConfigApiUrlFromModule;
export let autoTtsEnabled = false; // For the GUI toggle

window.isAwaitingResponse = false; 
window.attachedDocumentText = null;
window.attachedDocumentName = null;
window.eidosWebSocket = null;
window.speechRecognitionInstance = null;
// Make core state accessible on window for convenience if needed by other modules directly (though try to avoid)
window.currentUserId = currentUserId;
window.EIDOS_API_BASE_URL = EIDOS_API_BASE_URL;
window.autoTtsEnabled = autoTtsEnabled;

window.isFirstMessageInSession = true;
window.weatherLocationChangedThisSession = false;


// --- Global State Setters (used by event_handlers.js for settings panel) ---
function setCurrentUserIdGlobal(newId) {
    if (newId && typeof newId === 'string' && newId.trim() !== "") {
        const normalizedNewId = newId.trim().toLowerCase().replace(/ /g, "_");
        if (normalizedNewId) {
            currentUserId = normalizedNewId;
            localStorage.setItem(USER_ID_KEY, normalizedNewId);
            window.currentUserId = normalizedNewId; // Update global window property
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
    if (!currentUserId) { // Initialize if still empty
        currentUserId = "unknown_user";
        localStorage.setItem(USER_ID_KEY, currentUserId);
        window.currentUserId = currentUserId;
        if (DOM.userIdInput) DOM.userIdInput.value = currentUserId;
    }
}

function setGlobalApiBaseUrlGlobal(newUrl) {
    if (newUrl && typeof newUrl === 'string' && newUrl.startsWith('http')) {
        EIDOS_API_BASE_URL = newUrl;
        updateConfigApiBaseUrlFromModule(newUrl); // Update config.js module's variable too
        window.EIDOS_API_BASE_URL = EIDOS_API_BASE_URL; // Update global window property
        console.log("Main.js: Global EIDOS_API_BASE_URL updated to:", EIDOS_API_BASE_URL);
        if (DOM.apiUrlInput) DOM.apiUrlInput.value = EIDOS_API_BASE_URL; // Update settings input if present
        if (window.eidosWebSocket) { // Reconnect WebSocket if API URL changes
            console.log("Main.js: API Base URL changed, reconnecting WebSocket.");
            connectWsApi(); 
        }
    } else {
        console.warn("Main.js: setGlobalApiBaseUrlGlobal - Invalid URL:", newUrl);
    }
}
function getGlobalApiBaseUrlGlobal() { return EIDOS_API_BASE_URL; }

function getApiKeyGlobal() { return localStorage.getItem(EIDOS_API_KEY_KEY) || ""; }
function setApiKeyGlobal(value) { 
    const trimmedValue = value ? value.trim() : ""; 
    if (trimmedValue) localStorage.setItem(EIDOS_API_KEY_KEY, trimmedValue); 
    else localStorage.removeItem(EIDOS_API_KEY_KEY); 
    console.log("Main.js: API Key updated.");
    if (DOM.apiKeyInput) DOM.apiKeyInput.value = trimmedValue;
}

function getLlmProviderUrlGlobal() { return localStorage.getItem(LLM_PROVIDER_URL_KEY) || ""; }
function setLlmProviderUrlGlobal(value) { 
    const trimmedValue = value ? value.trim() : ""; 
    if (trimmedValue) localStorage.setItem(LLM_PROVIDER_URL_KEY, trimmedValue); 
    else localStorage.removeItem(LLM_PROVIDER_URL_KEY); 
    console.log("Main.js: LLM Provider URL updated.");
    if (DOM.llmProviderUrlInput) DOM.llmProviderUrlInput.value = trimmedValue;
}

function getWeatherLocGlobal() { return localStorage.getItem(WEATHER_LOCATION_KEY) || ""; }
function setWeatherLocGlobal(value) { 
    const oldLoc = getWeatherLocGlobal(); 
    const trimmedValue = value ? value.trim() : ""; 
    if (trimmedValue) localStorage.setItem(WEATHER_LOCATION_KEY, trimmedValue); 
    else localStorage.removeItem(WEATHER_LOCATION_KEY); 
    console.log("Main.js: Weather Location updated."); 
    if (DOM.weatherLocationInput) DOM.weatherLocationInput.value = trimmedValue;
    if (oldLoc !== trimmedValue) window.weatherLocationChangedThisSession = true; 
}

function getSystemPromptTextGlobal() { return localStorage.getItem(SYSTEM_PROMPT_KEY) || ""; }
function setSystemPromptTextGlobal(value) { 
    const trimmedValue = value ? value.trim() : "";
    localStorage.setItem(SYSTEM_PROMPT_KEY, trimmedValue); 
    console.log("Main.js: System Prompt updated."); 
    if (DOM.systemPromptInput) DOM.systemPromptInput.value = trimmedValue;
}

function getModelTempGlobal() { return parseFloat(localStorage.getItem(MODEL_TEMPERATURE_KEY) || DEFAULT_MODEL_TEMPERATURE.toString()); }
function setModelTempGlobal(value) { 
    const temp = parseFloat(value);
    if (!isNaN(temp) && temp >= 0.0 && temp <= 2.0) {
        localStorage.setItem(MODEL_TEMPERATURE_KEY, temp.toString()); 
        console.log("Main.js: Model Temperature updated."); 
        if (DOM.modelTemperatureInput) DOM.modelTemperatureInput.value = temp.toString();
    } else {
        console.warn("Main.js: Invalid model temperature value:", value);
    }
}

function getContextLenGlobal() { 
    const lenStr = localStorage.getItem(EIDOS_CONTEXT_LENGTH_KEY); 
    return lenStr ? parseInt(lenStr, 10) : null; 
}
function setContextLenGlobal(value) { 
    const len = parseInt(value, 10);
    if (!isNaN(len) && len > 0) {
        localStorage.setItem(EIDOS_CONTEXT_LENGTH_KEY, len.toString()); 
        console.log("Main.js: Context Length updated."); 
        if (DOM.contextLengthInput) DOM.contextLengthInput.value = len.toString();
    } else if (value === null || value === undefined || value.toString().trim() === "") {
        localStorage.removeItem(EIDOS_CONTEXT_LENGTH_KEY);
        console.log("Main.js: Context Length cleared.");
        if (DOM.contextLengthInput) DOM.contextLengthInput.value = "";
    } else {
         console.warn("Main.js: Invalid context length value:", value);
    }
}

// NEW: Admin Password getter/setter
function getAdminPasswordGlobal() { return localStorage.getItem(EIDOS_ADMIN_PASSWORD_KEY) || ""; }
function setAdminPasswordGlobal(value) {
    const trimmedValue = value ? value.trim() : "";
    if (trimmedValue) {
        localStorage.setItem(EIDOS_ADMIN_PASSWORD_KEY, trimmedValue);
    } else {
        localStorage.removeItem(EIDOS_ADMIN_PASSWORD_KEY);
    }
    console.log("Main.js: Admin Password updated in localStorage.");
    if (DOM.adminPasswordInput) DOM.adminPasswordInput.value = trimmedValue;
}

// --- Weather Panel Specific State & Functions ---
let weatherUpdateIntervalId = null; // Keep this module-scoped
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
window.updateWeatherDisplay = updateWeatherDisplay; // Expose if needed by other modules, though unlikely

function setupWeatherUpdatesGlobal() {
    if (weatherUpdateIntervalId !== null) clearInterval(weatherUpdateIntervalId);
    const location = getWeatherLocGlobal();
    if (location && location.trim()) {
        fetchWeatherAPI(location).then(data => { if (data) updateWeatherDisplay(data); });
        // Optional: Set an interval to refresh weather periodically
        // weatherUpdateIntervalId = setInterval(() => {
        //     fetchWeatherAPI(location).then(data => { if (data) updateWeatherDisplay(data); });
        // }, 15 * 60 * 1000); // Refresh every 15 minutes
    } else {
        if (DOM.weatherPanel) DOM.weatherPanel.style.display = 'none';
    }
}

// --- UI Interaction Orchestration ---
async function handleSendMessageUI(forceSearchPrefix = "") {
    await sendMessageApi(forceSearchPrefix); // From api_comms.js
}

function updateTtsToggleButtonState() {
    if (DOM.ttsToggleButton) {
        const svgElement = DOM.ttsToggleButton.querySelector('svg');
        if (!svgElement) return;
        if (window.autoTtsEnabled) { // Reads global window.autoTtsEnabled
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
    autoTtsEnabled = !autoTtsEnabled; // Toggles module-scoped variable
    localStorage.setItem(AUTO_TTS_ENABLED_KEY, autoTtsEnabled.toString());
    window.autoTtsEnabled = autoTtsEnabled; // Updates global window property
    updateTtsToggleButtonState();
    showNotification(`Auto TTS ${autoTtsEnabled ? 'Enabled' : 'Disabled'}.`);
    if (!autoTtsEnabled) {
        if (typeof stopAndClearTTSQueue === 'function') {
            stopAndClearTTSQueue();
        }
    }
}

// --- WebSocket Message Handler ---
window.handleWebSocketMessage = function(message) { // Attached to window for global access
    // console.debug("Main.js handleWebSocketMessage received:", JSON.stringify(message).substring(0, 300) + "...");

    if (message.type === "unsolicited_message" && message.payload) {
        // console.debug("Main.js: Received unsolicited_message:", JSON.stringify(message.payload).substring(0, 200) + "...");
        if (typeof displayProactiveMessageInPanel === 'function') {
            displayProactiveMessageInPanel(message.payload.content, message.payload.metadata);
        }
        showNotification("New proactive message from Pathos!", "info");
    } else if (message.type === "tts_audio_chunk_ready" && message.payload) {
        console.log(`DEBUG: Main.js: Received tts_audio_chunk_ready. URL: ${message.payload.url}, Seq: ${message.payload.sequence}`);
        
        if (typeof addAudioUrlToTTSQueue === 'function') {
            const chunkUrl = message.payload.url || "";
            const isProactiveAudioChunk = message.payload.is_proactive_audio === true || chunkUrl.includes("/proactive_tts_");
            const isMainChatAudioChunk = !isProactiveAudioChunk && chunkUrl.includes("/chat_tts_");

            let bubbleToAssociateWith = null;
            if (isMainChatAudioChunk) {
                const latestAiBubble = getLatestAIMessageBubbleForTTS ? getLatestAIMessageBubbleForTTS() : null;
                if (latestAiBubble && latestAiBubble.dataset.ttsExpected === 'true') {
                    bubbleToAssociateWith = latestAiBubble;
                }
            }
            
            // Add the chunk to the queue first
            addAudioUrlToTTSQueue(
                message.payload.url,
                message.payload.sequence,
                message.payload.text_for_indicator,
                bubbleToAssociateWith
            );

            // Now, decide if we should try to kick off playback
            if (isMainChatAudioChunk && window.autoTtsEnabled) {
                const mainChatTTSShouldBeActive = isCurrentlyPlayingMainChatTTS();
                console.log(`DEBUG: handleWebSocketMessage (MainChatChunk): autoTtsEnabled=${window.autoTtsEnabled}, isCurrentlyPlayingMainChatTTS()=${mainChatTTSShouldBeActive}`);
                if (mainChatTTSShouldBeActive) {
                    // This implies displayMessage has set the flag expecting these chunks.
                    console.log("DEBUG: handleWebSocketMessage (MainChatChunk): Conditions met, calling playNextInTTSQueueIfIdle().");
                    if (typeof playNextInTTSQueueIfIdle === 'function') {
                        playNextInTTSQueueIfIdle();
                    }
                } else {
                    console.log("DEBUG: handleWebSocketMessage (MainChatChunk): isCurrentlyPlayingMainChatTTS is false, not auto-playing from here. Playback should have been initiated by displayMessage or click.");
                }
            } else if (isProactiveAudioChunk && window.autoTtsEnabled) {
                // For proactive audio, playback is typically initiated by the click handler in ui_chat.js,
                // which sets currentlyPlayingMainChatTTS = true and then calls playNextInTTSQueueIfIdle.
                // So, we usually don't need to call playNextInTTSQueueIfIdle() from here for proactive chunks
                // unless the logic changes to pre-play them under certain conditions.
                // For now, just adding to queue is enough. The click handler will start it.
                console.log("DEBUG: handleWebSocketMessage (ProactiveChunk): Chunk added. Playback initiated by click handler.");
            }
        }
    } else if (message.type === "status" && message.payload && message.payload.message) {
        console.log("Eidos Status via WebSocket:", message.payload.message);
    } else if (message.type === "error" && message.payload && message.payload.message) {
        console.error("Eidos WebSocket Error:", message.payload.message);
        showNotification(`Eidos Error (WS): ${message.payload.message}`, "error");
    }
};

// NEW: Function to populate the Event Type dropdown in the Add Pathos Event panel
function populatePathosEventForm() {
    if (DOM.pathosEventTypeSelect) {
        const eventTypes = [
            'vacation', 'work_trip', 'conference', 'personal_day', 'appointment', 
            'recurring_task', 'holiday', 'social_engagement', 'other_event'
        ];
        // Clear existing options except the placeholder
        while (DOM.pathosEventTypeSelect.options.length > 1) {
            DOM.pathosEventTypeSelect.remove(1);
        }
        eventTypes.forEach(type => {
            const option = document.createElement('option');
            option.value = type;
            option.textContent = type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            DOM.pathosEventTypeSelect.appendChild(option);
        });
    } else {
        console.warn("populatePathosEventForm: pathosEventTypeSelect DOM element not found.");
    }
}

// --- DOMContentLoaded: Main Application Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded. Initializing Eidos GUI (main.js)...");
    
    // Add clipboard paste event handler for the entire document to capture images
    document.addEventListener('paste', (e) => {
        // Only process if we're focused in the chat area or input
        const activeElement = document.activeElement;
        const isInChatArea = DOM.chatMessagesArea && DOM.chatMessagesArea.contains(activeElement);
        const isInputArea = DOM.userInput && (activeElement === DOM.userInput);
        
        if (!isInChatArea && !isInputArea) {
            return; // Only handle pastes in the chat area or input
        }
        
        console.log('Paste event detected');
        
        // Check for image data in clipboard
        if (e.clipboardData && e.clipboardData.items) {
            const items = e.clipboardData.items;
            
            for (let i = 0; i < items.length; i++) {
                const item = items[i];
                
                // Check if the item is an image
                if (item.type.indexOf('image/') === 0) {
                    e.preventDefault(); // Prevent the default paste behavior
                    
                    const file = item.getAsFile();
                    console.log(`Pasted image detected: ${file.type}, size: ${file.size} bytes`);
                    
                    // Process the image file
                    if (typeof handleImageUploadClientSide === 'function') {
                        handleImageUploadClientSide(file);
                    }
                    
                    break; // Only handle the first image
                }
            }
        }
    });

    // Load initial settings from localStorage and apply them
    const savedApiUrl = localStorage.getItem(EIDOS_API_BASE_URL_KEY);
    if (savedApiUrl && savedApiUrl.trim() !== "") setGlobalApiBaseUrlGlobal(savedApiUrl);
    else setGlobalApiBaseUrlGlobal(ConfigApiUrlFromModule); // Default from config.js if nothing in localStorage

    const savedUserId = localStorage.getItem(USER_ID_KEY);
    if (savedUserId && savedUserId.trim() !== "") setCurrentUserIdGlobal(savedUserId);
    else setCurrentUserIdGlobal(`user_${Math.random().toString(36).substring(2, 9)}`); // Generate a random one if none

    if (DOM.apiKeyInput) DOM.apiKeyInput.value = getApiKeyGlobal();
    if (DOM.llmProviderUrlInput) DOM.llmProviderUrlInput.value = getLlmProviderUrlGlobal();
    if (DOM.weatherLocationInput) DOM.weatherLocationInput.value = getWeatherLocGlobal();
    if (DOM.systemPromptInput) DOM.systemPromptInput.value = getSystemPromptTextGlobal();
    if (DOM.modelTemperatureInput) DOM.modelTemperatureInput.value = getModelTempGlobal().toString();
    const savedContextLen = getContextLenGlobal();
    if (DOM.contextLengthInput) { 
        if (savedContextLen !== null && savedContextLen !== undefined) DOM.contextLengthInput.value = savedContextLen.toString(); 
        else DOM.contextLengthInput.value = ""; // Clear if null/undefined
    }

    const savedAutoTts = localStorage.getItem(AUTO_TTS_ENABLED_KEY);
    if (savedAutoTts !== null) autoTtsEnabled = (savedAutoTts === 'true'); // Update module-scoped
    window.autoTtsEnabled = autoTtsEnabled; // Update global
    updateTtsToggleButtonState();
    if (DOM.ttsToggleButton) DOM.ttsToggleButton.addEventListener('click', toggleAutoTts);

    // Load admin password
    if (DOM.adminPasswordInput) DOM.adminPasswordInput.value = getAdminPasswordGlobal();

    // --- Inject Dependencies into other modules ---
    setCloseAllSidePanelsFunction(closeAllSidePanels); 
    setDisplayMessageForStorage(displayMessageInChat);
    setLayoutFunctionsForStorage(initCleanInterface, expandChatInterface, hideAttachedDocumentIndicator);
    setSelectModelForStorage(selectModel); // From api_comms.js
    setApiCommsDependencies({ 
        displayMessageInChat, 
        displayProactiveMessageInPanel, 
        hideAttachedDocumentIndicator, 
        expandChatInterface, 
        scrollToBottom, 
        chatMessagesArea: DOM.chatMessagesArea,
        fetchPathosChronosData: fetchAndDisplayPathosChronosData // Pass this for refreshing Chronos panel
    });
    setExpandChatForUiChat(expandChatInterface);
    setDisplayMessageFunctionForProactive(displayMessageInChat);
    
    injectEventHandlersDeps({
        sendMessage: handleSendMessageUI, // Uses sendMessageApi from api_comms.js
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
        fetchAndDisplayUserFacts: fetchAndDisplayUserFacts,
        addPathosEventAPI: addPathosEventAPI, // NEW: Inject the API function
        setAdminPassword: setAdminPasswordGlobal, // NEW: Inject setter for admin password
        // Pass global state accessors
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

    // --- Initialize UI and Services ---
    if (DOM.userInput) { 
        DOM.userInput.focus(); 
        DOM.userInput.addEventListener('input', () => autoAdjustTextareaHeight(DOM.userInput)); 
        autoAdjustTextareaHeight(DOM.userInput); 

        // --- NEW: Event listener for Enter key ---
        DOM.userInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                if (DOM.sendButton && !DOM.sendButton.disabled) {
                    DOM.sendButton.click();
                } else if (typeof handleSendMessageUI === 'function' && !window.isAwaitingResponse) {
                    console.log("Enter pressed, attempting to send message via function call as button might be disabled.");
                    handleSendMessageUI();
                }
            }
        });
        // --- END NEW Event listener ---
    }

    // --- DRAG AND DROP FILE UPLOAD ---
    function setupDragAndDropHandlers() {
        console.log('Setting up drag and drop handlers');
        
        // Prevent default drag behaviors on window to avoid browser opening files
        window.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
        });
        
        window.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
        });
        
        // Make sure we have the chat area element
        if (!DOM.chatMessagesArea) {
            console.error('chatMessagesArea element not found for drag and drop setup');
            return;
        }
        
        // Function to show/hide drag indicator
        function showDragIndicator(show) {
            if (show) {
                console.log('Showing drag indicator');
                DOM.chatMessagesArea.classList.add('drag-over');
                
                // Force a reflow to ensure CSS animation restart
                void DOM.chatMessagesArea.offsetWidth;
            } else {
                console.log('Hiding drag indicator');
                DOM.chatMessagesArea.classList.remove('drag-over');
            }
        }
        
        // Function to process a dropped file
        function processDroppedFile(file) {
            if (!file) return false;
            
            console.log(`Processing file: ${file.name}, type: ${file.type || 'unknown'}, size: ${file.size} bytes`);
            
            // Determine file type based on MIME type and extension
            const fileExt = file.name.split('.').pop().toLowerCase();
            
            if (
                file.type === 'application/pdf' || 
                fileExt === 'pdf' ||
                file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' || 
                fileExt === 'docx' ||
                file.type === 'text/plain' || 
                fileExt === 'txt'
            ) {
                // Process document
                console.log('Processing as document');
                handleDocumentUploadAPI(file);
                return true;
            } else if (
                file.type.startsWith('image/') || 
                ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(fileExt)
            ) {
                // Process image
                console.log('Processing as image');
                handleImageUploadClientSide(file);
                return true;
            } else {
                console.log(`Unsupported file type: ${file.type}, extension: ${fileExt}`);
                showNotification('Only PDF, DOCX, TXT, or image files are supported for upload.', 'error');
                return false;
            }
        }
        
        // Setup dragenter handler to immediately show visual feedback
        DOM.chatMessagesArea.addEventListener('dragenter', function(e) {
            console.log('Dragenter event detected');
            e.preventDefault();
            e.stopPropagation();
            
            // Show visual indicator immediately on dragenter
            showDragIndicator(true);
        });
        
        // Setup dragover handler
        DOM.chatMessagesArea.addEventListener('dragover', function(e) {
            // Note: Not logging every dragover event to reduce console spam
            e.preventDefault();
            e.stopPropagation();
            
            // Always set copy effect to indicate it can be dropped
            e.dataTransfer.dropEffect = 'copy';
            
            // Visual indicator is set in dragenter and maintained here
            showDragIndicator(true);
        });
        
        // Setup dragleave handler
        DOM.chatMessagesArea.addEventListener('dragleave', function(e) {
            console.log('Dragleave event detected');
            e.preventDefault();
            e.stopPropagation();
            
            // Only remove class if we're actually leaving the chat area, not entering a child
            const rect = DOM.chatMessagesArea.getBoundingClientRect();
            if (
                e.clientX <= rect.left ||
                e.clientX >= rect.right ||
                e.clientY <= rect.top ||
                e.clientY >= rect.bottom
            ) {
                showDragIndicator(false);
            }
        });
        
        // Setup drop handler
        DOM.chatMessagesArea.addEventListener('drop', function(e) {
            console.log('Drop event detected');
            e.preventDefault();
            e.stopPropagation();
            
            // Remove visual feedback
            showDragIndicator(false);
            
            try {
                // Check if we have files in the drop
                const files = e.dataTransfer.files;
                if (!files || files.length === 0) {
                    console.log('No files in drop event');
                    showNotification('No files found in drop', 'error');
                    return;
                }
                
                // Process the first file
                const file = files[0];
                processDroppedFile(file);
                
            } catch (error) {
                console.error('Error handling file drop:', error);
                showNotification(`Error processing file: ${error.message || 'Unknown error'}`, 'error');
            }
        });
        
        // Also handle paste events for the whole document (already added)
        
        console.log('Drag and drop handlers setup complete');
    }
    
    // Call the setup function to initialize drag and drop
    setupDragAndDropHandlers();
    // --- END DRAG AND DROP ---

    const chatWasLoaded = loadCurrentActiveChatOnStartup();
    if (!chatWasLoaded) initCleanInterface(); 
    else expandChatInterface();
    
    initializePanelConfigurations({ 
        renderHistoryPanel, 
        fetchLearnings: fetchAndDisplayLearnings, 
        fetchDreams: fetchAndDisplayDreams, 
        fetchKnowledgeVerifications: fetchAndDisplayKnowledgeVerifications, 
        fetchDailyBriefing: fetchAndDisplayDailyBriefingGUI, 
        fetchUserFacts: fetchAndDisplayUserFacts,
        fetchPathosChronosData: fetchAndDisplayPathosChronosData,
        populatePathosEventForm: populatePathosEventForm // NEW: Pass the populating function
    });
    
    setupPanelEventListeners(); // From panel_manager.js
    
    console.log("DEBUG: About to call setupGlobalEventListeners from event_handlers.js"); // DEBUG LINE
    setupGlobalEventListeners(); // From event_handlers.js
    
    // Add event listener for Chronos panel refresh button (already added in your provided main.js)
    if (DOM.refreshChronosPanelButton && typeof fetchAndDisplayPathosChronosData === 'function') {
        DOM.refreshChronosPanelButton.addEventListener('click', fetchAndDisplayPathosChronosData);
    } else if (!DOM.refreshChronosPanelButton) {
        console.warn("refreshChronosPanelButton not found in DOM.");
    } else if (typeof fetchAndDisplayPathosChronosData !== 'function') {
        console.warn("fetchAndDisplayPathosChronosData function not available for refreshChronosPanelButton.");
    }


    fetchModels(); // From api_comms.js
    window.speechRecognitionInstance = initializeSpeechRecognition(); // From stt.js
    connectWsApi(); // From api_comms.js
    window.connectWebSocket = connectWsApi; // Expose for potential re-connects
    setupWeatherUpdatesGlobal(); // In main.js

    // Prism.js autoloader path (if using CDN version)
    if (typeof Prism !== 'undefined' && Prism.plugins && Prism.plugins.autoloader) {
        Prism.plugins.autoloader.languages_path = 'https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/';
    } else {
        console.warn("Prism autoloader not found. Code syntax highlighting might be limited.");
    }

    // Expose some functions to window for easier debugging or specific interop if absolutely needed
    window.displayMessageInChat = displayMessageInChat; // From ui_chat.js
    window.showNotification = showNotification; // From utils.js
    window.renderHistoryPanel = renderHistoryPanel; // From ui_panels.js
    window.showAttachedDocumentIndicator = showAttachedDocumentIndicator; // From ui_layout.js

    console.log("Eidos GUI Initialization complete (main.js).");
});

window.addEventListener('beforeunload', saveCurrentActiveChat); // From persistent_storage.js
console.log("main.js loaded and executing.");