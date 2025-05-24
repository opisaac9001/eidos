// webapp/js/event_handlers.js

import * as DOM from './dom_elements.js';
import { EIDOS_API_BASE_URL_KEY, USER_ID_KEY, SYSTEM_PROMPT_KEY, WEATHER_LOCATION_KEY, EIDOS_API_KEY_KEY, MODEL_TEMPERATURE_KEY, EIDOS_CONTEXT_LENGTH_KEY, LLM_PROVIDER_URL_KEY } from './config.js';
import { showNotification, autoAdjustTextareaHeight } from './utils.js';

// --- Injected Dependencies (set by main.js) ---
let _sendMessageUI;
let _handleDocUpload;
let _handleImgUpload;
let _removeAttachedDoc;
let _toggleListening;
let _resetChat;
let _clearAllLocalHistory;
let _saveSettingsToBackend;
let _clearUserMemoryBE;
let _clearEidosMemoryBE;
let _fetchModels;
let _fetchWeather;
let _setupWeather;
let _fetchDailyBriefing;
let _fetchLearnings;
let _fetchDreams;
let _fetchKnowledgeVerifications;
let _fetchUserFacts; // New

// State accessors/mutators injected from main.js
let _currentUserId, _EIDOS_API_BASE_URL_GLOBAL;
let _setCurrentUserId, _setGlobalApiBaseUrl, _setAPIKey, _setLLMProviderUrl,
    _setWeatherLoc, _setSystemPrompt, _setModelTemp, _setContextLen;


export function injectDependencies(dependencies) {
    _sendMessageUI = dependencies.sendMessage;
    _handleDocUpload = dependencies.handleDocumentUploadAPI;
    _handleImgUpload = dependencies.handleImageUploadClientSide;
    _removeAttachedDoc = dependencies.removeAttachedDocument;
    _toggleListening = dependencies.toggleListening;
    _resetChat = dependencies.resetChat;
    _clearAllLocalHistory = dependencies.clearAllLocalChatHistory;
    _saveSettingsToBackend = dependencies.saveSettingsToBackendAPI;
    _clearUserMemoryBE = dependencies.clearUserBackendMemoryAPI;
    _clearEidosMemoryBE = dependencies.clearEidosBackendMemoryAPI;
    _fetchModels = dependencies.fetchModels;
    _fetchWeather = dependencies.fetchWeatherAPI;
    _setupWeather = dependencies.setupWeatherUpdates;
    _fetchDailyBriefing = dependencies.fetchAndDisplayDailyBriefingGUI;
    _fetchLearnings = dependencies.fetchAndDisplayLearnings;
    _fetchDreams = dependencies.fetchAndDisplayDreams;
    _fetchKnowledgeVerifications = dependencies.fetchAndDisplayKnowledgeVerifications;
    _fetchUserFacts = dependencies.fetchAndDisplayUserFacts; // Inject new function

    _currentUserId = dependencies.currentUserId;
    _EIDOS_API_BASE_URL_GLOBAL = dependencies.EIDOS_API_BASE_URL_GLOBAL;
    _setCurrentUserId = dependencies.setCurrentUserId;
    _setGlobalApiBaseUrl = dependencies.setGlobalApiBaseUrl;
    _setAPIKey = dependencies.setAPIKey;
    _setLLMProviderUrl = dependencies.setLLMProviderUrl;
    _setWeatherLoc = dependencies.setWeatherLoc;
    _setSystemPrompt = dependencies.setSystemPrompt;
    _setModelTemp = dependencies.setModelTemp;
    _setContextLen = dependencies.setContextLen;
}


export function setupGlobalEventListeners() {
    if (!DOM.sendButton) { console.error("setupGlobalEventListeners: DOM not ready."); return; }

    DOM.sendButton.addEventListener('click', () => {
        if (typeof _sendMessageUI === 'function') _sendMessageUI();
        else console.error("Send message function not injected.");
    });

    if (DOM.userInput) {
        DOM.userInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                if (typeof _sendMessageUI === 'function') _sendMessageUI();
                else console.error("Send message function not injected.");
            }
        });
    }

    if (DOM.resetChatButton && typeof _resetChat === 'function') {
        DOM.resetChatButton.addEventListener('click', _resetChat);
    }
    if (DOM.uploadDocumentButton && DOM.documentInput && typeof _handleDocUpload === 'function') {
        DOM.uploadDocumentButton.addEventListener('click', () => DOM.documentInput.click());
        DOM.documentInput.addEventListener('change', (event) => {
            const file = event.target.files[0]; if (file) _handleDocUpload(file);
        });
    }
    if (DOM.uploadImageButton && DOM.imageInput && typeof _handleImgUpload === 'function') {
        DOM.uploadImageButton.addEventListener('click', () => DOM.imageInput.click());
        DOM.imageInput.addEventListener('change', (event) => {
            const file = event.target.files[0]; if (file) _handleImgUpload(file);
        });
    }
    if (DOM.removeAttachedDocumentButton && typeof _removeAttachedDoc === 'function') {
        DOM.removeAttachedDocumentButton.addEventListener('click', _removeAttachedDoc);
    }
    if (DOM.forceWebSearchButton && typeof _sendMessageUI === 'function') {
         DOM.forceWebSearchButton.addEventListener('click', () => _sendMessageUI("[FORCE_WEB_SEARCH] "));
    }
    if (DOM.microphoneButton && typeof _toggleListening === 'function') {
        DOM.microphoneButton.addEventListener('click', _toggleListening);
    }
    if (DOM.getDailyBriefingButton && typeof _fetchDailyBriefing === 'function' && DOM.dailyBriefingPanel) {
        DOM.getDailyBriefingButton.addEventListener('click', () => {
            _fetchDailyBriefing();
            // Also open the panel
            const panelWasOpen = DOM.dailyBriefingPanel.classList.contains('open');
            if (typeof window.closeAllSidePanels === 'function') window.closeAllSidePanels(); // Close others
            if (!panelWasOpen) {
                if (!DOM.dailyBriefingPanel.classList.contains('right-sliding')) DOM.dailyBriefingPanel.classList.add('right-sliding');
                DOM.dailyBriefingPanel.classList.add('open');
            }
        });
    }


    if (DOM.systemPromptSave) {
        DOM.systemPromptSave.addEventListener('click', async () => {
            if (DOM.systemPromptInput && typeof _setSystemPrompt === 'function') {
                _setSystemPrompt(DOM.systemPromptInput.value.trim());
            }
    
            if (DOM.modelTemperatureInput && typeof _setModelTemp === 'function') {
                const temp = parseFloat(DOM.modelTemperatureInput.value);
                if (!isNaN(temp)) _setModelTemp(temp);
            }
    
            let llmChanged = false;
            if (DOM.llmProviderUrlInput && typeof _setLLMProviderUrl === 'function') {
                _setLLMProviderUrl(DOM.llmProviderUrlInput.value.trim());
                llmChanged = true;
            }
    
            let apiChanged = false;
            if (DOM.apiUrlInput && typeof _setGlobalApiBaseUrl === 'function') {
                _setGlobalApiBaseUrl(DOM.apiUrlInput.value.trim());
                apiChanged = true;
            }
    
            if (DOM.apiKeyInput && typeof _setAPIKey === 'function') {
                _setAPIKey(DOM.apiKeyInput.value.trim());
            }
    
            let userChanged = false;
            if (DOM.userIdInput && typeof _setCurrentUserId === 'function') {
                _setCurrentUserId(DOM.userIdInput.value.trim());
                userChanged = true;
            }
    
            let weatherChanged = false;
            if (DOM.weatherLocationInput && typeof _setWeatherLoc === 'function') {
                _setWeatherLoc(DOM.weatherLocationInput.value.trim());
                weatherChanged = true;
                window.weatherLocationChangedThisSession = true;
            }
    
            if (DOM.contextLengthInput && typeof _setContextLen === 'function') {
                const len = parseInt(DOM.contextLengthInput.value, 10);
                if (!isNaN(len)) _setContextLen(len);
            }
    
            const settingsToSyncForBackend = [];
            if (DOM.weatherLocationInput && DOM.weatherLocationInput.value.trim()) {
                settingsToSyncForBackend.push({
                    attribute_name: "preferred_location",
                    attribute_value: DOM.weatherLocationInput.value.trim(),
                    user_statement_context: "User set default weather location via GUI settings."
                });
            }
            if (DOM.systemPromptInput && DOM.systemPromptInput.value.trim()) {
                settingsToSyncForBackend.push({
                    attribute_name: "system_prompt_preference",
                    attribute_value: DOM.systemPromptInput.value.trim(),
                    user_statement_context: "User set system prompt preference via GUI settings."
                });
            }
    
            if (settingsToSyncForBackend.length > 0 && typeof _saveSettingsToBackend === 'function') {
                const payload = { settings: settingsToSyncForBackend };
                await _saveSettingsToBackend(payload);
            }
    
            if (apiChanged || userChanged) {
                // TODO: Reconnect WebSocket if needed
            }
    
            if (llmChanged && typeof _fetchModels === 'function') {
                _fetchModels();
            }
    
            if (weatherChanged && typeof _setupWeather === 'function') {
                _setupWeather();
            }
    
            if (DOM.systemPromptPanel) DOM.systemPromptPanel.classList.remove('open');
            showNotification('Settings saved to browser. Backend sync initiated where applicable.', 'success');
        });
    }

    if (DOM.clearHistoryButton && typeof _clearAllLocalHistory === 'function') { DOM.clearHistoryButton.addEventListener('click', _clearAllLocalHistory); }
    if (DOM.clearUserMemoryButton && typeof _clearUserMemoryBE === 'function') { DOM.clearUserMemoryButton.addEventListener('click', async () => { if (await _clearUserMemoryBE()) { if(typeof _clearAllLocalHistory === 'function') _clearAllLocalHistory(); if(typeof _resetChat === 'function') _resetChat(); }}); }
    if (DOM.clearBackendMemoryButton && typeof _clearEidosMemoryBE === 'function') { DOM.clearBackendMemoryButton.addEventListener('click', async () => { if (await _clearEidosMemoryBE()) { if(typeof _clearAllLocalHistory === 'function') _clearAllLocalHistory(); if(typeof _resetChat === 'function') _resetChat(); }}); }
    if (DOM.weatherCloseButton && DOM.weatherPanel) { DOM.weatherCloseButton.addEventListener('click', () => DOM.weatherPanel.style.display = 'none'); }
    if (DOM.weatherUpdateButton && typeof _fetchWeather === 'function') { /* ... */ }

    if (DOM.refreshDailyBriefingButton && typeof _fetchDailyBriefing === 'function') DOM.refreshDailyBriefingButton.addEventListener('click', _fetchDailyBriefing);
    if (DOM.refreshLearningLogButton && typeof _fetchLearnings === 'function') DOM.refreshLearningLogButton.addEventListener('click', _fetchLearnings);
    if (DOM.clearLearningLogDisplayButton && DOM.learningLogContentArea) DOM.clearLearningLogDisplayButton.addEventListener('click', () => { DOM.learningLogContentArea.innerHTML = '<p style="color: #888;">Display cleared.</p>'; });
    if (DOM.refreshDreamJournalButton && typeof _fetchDreams === 'function') DOM.refreshDreamJournalButton.addEventListener('click', _fetchDreams);
    if (DOM.clearDreamJournalDisplayButton && DOM.dreamJournalContentArea) DOM.clearDreamJournalDisplayButton.addEventListener('click', () => { DOM.dreamJournalContentArea.innerHTML = '<p style="color: #888;">Display cleared.</p>'; });
    if (DOM.refreshKnowledgeLogButton && typeof _fetchKnowledgeVerifications === 'function') DOM.refreshKnowledgeLogButton.addEventListener('click', _fetchKnowledgeVerifications);
    if (DOM.clearKnowledgeLogDisplayButton && DOM.knowledgeLogContentArea) DOM.clearKnowledgeLogDisplayButton.addEventListener('click', () => { DOM.knowledgeLogContentArea.innerHTML = '<p style="color: #888;">Display cleared.</p>'; });
    if (DOM.clearProactiveButton && DOM.proactiveMessagesArea) DOM.clearProactiveButton.addEventListener('click', () => { DOM.proactiveMessagesArea.innerHTML = '<p style="color: #888;">No proactive messages yet.</p>'; showNotification('Proactive display cleared.', 'info'); });
    
    // Listener for the new "Refresh Facts" button
    if (DOM.refreshUserFactsButton && typeof _fetchUserFacts === 'function') {
        DOM.refreshUserFactsButton.addEventListener('click', _fetchUserFacts);
    }

    if (DOM.inputContainer) { /* ... Drag-drop listeners ... */ }
    console.log("Global event listeners set up.");
}
console.log("event_handlers.js loaded.");