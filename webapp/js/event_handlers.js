import * as DOM from './dom_elements.js';
import { EIDOS_API_BASE_URL_KEY, USER_ID_KEY, SYSTEM_PROMPT_KEY, WEATHER_LOCATION_KEY, EIDOS_API_KEY_KEY, MODEL_TEMPERATURE_KEY, EIDOS_CONTEXT_LENGTH_KEY, LLM_PROVIDER_URL_KEY } from './config.js';
import { showNotification, autoAdjustTextareaHeight } from './utils.js';
// sendMessage, handleDocumentUploadAPI, etc., will be called from window or passed by main.js
// resetChat, clearAllLocalChatHistory from window or passed by main.js
// toggleListening from window or passed by main.js
// Panel fetch functions from window or passed by main.js
// fetchWeatherAPI, setupWeatherUpdates from window or passed by main.js

// These will be set by main.js
let _sendMessage, _handleDocUpload, _handleImgUpload, _removeAttachedDoc, 
    _toggleListening, _resetChat, _clearAllLocalHistory, 
    _saveSettingsToBackend, _clearUserMemoryBE, _clearEidosMemoryBE,
    _fetchModels, _fetchWeather, _setupWeather,
    _fetchDailyBriefing, _fetchLearnings, _fetchDreams, _fetchKnowledgeVerifications;

let _currentUserId, _EIDOS_API_BASE_URL_GLOBAL;
let _setCurrentUserId, _setGlobalApiBaseUrl, _setAPIKey, _setLLMProviderUrl, 
    _setWeatherLoc, _setSystemPrompt, _setModelTemp, _setContextLen;


export function injectDependencies(dependencies) {
    _sendMessage = dependencies.sendMessage;
    _handleDocUpload = dependencies.handleDocumentUploadAPI;
    _handleImgUpload = dependencies.handleImageUploadClientSide;
    _removeAttachedDoc = dependencies.removeAttachedDocument; // from ui_layout via main
    _toggleListening = dependencies.toggleListening;
    _resetChat = dependencies.resetChat;
    _clearAllLocalHistory = dependencies.clearAllLocalChatHistory;
    _saveSettingsToBackend = dependencies.saveSettingsToBackendAPI;
    _clearUserMemoryBE = dependencies.clearUserBackendMemoryAPI;
    _clearEidosMemoryBE = dependencies.clearEidosBackendMemoryAPI;
    _fetchModels = dependencies.fetchModels;
    _fetchWeather = dependencies.fetchWeatherAPI; // The API call
    _setupWeather = dependencies.setupWeatherUpdates; // The one that calls fetchWeatherAPI and sets interval

    _fetchDailyBriefing = dependencies.fetchAndDisplayDailyBriefingGUI;
    _fetchLearnings = dependencies.fetchAndDisplayLearnings;
    _fetchDreams = dependencies.fetchAndDisplayDreams;
    _fetchKnowledgeVerifications = dependencies.fetchAndDisplayKnowledgeVerifications;

    // State and setters
    _currentUserId = dependencies.currentUserId; // This is the getter/value
    _EIDOS_API_BASE_URL_GLOBAL = dependencies.EIDOS_API_BASE_URL_GLOBAL; // Getter/value

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

    DOM.sendButton.addEventListener('click', () => _sendMessage());
    if (DOM.userInput) {
        DOM.userInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); _sendMessage(); }
        });
        // autoAdjustTextareaHeight is called by sendMessage and STT, no separate listener here needed if covered
    }

    if (DOM.resetChatButton) DOM.resetChatButton.addEventListener('click', _resetChat);
    if (DOM.uploadDocumentButton && DOM.documentInput) {
        DOM.uploadDocumentButton.addEventListener('click', () => DOM.documentInput.click());
        DOM.documentInput.addEventListener('change', (event) => {
            const file = event.target.files[0]; if (file) _handleDocUpload(file);
        });
    }
    if (DOM.uploadImageButton && DOM.imageInput) {
        DOM.uploadImageButton.addEventListener('click', () => DOM.imageInput.click());
        DOM.imageInput.addEventListener('change', (event) => {
            const file = event.target.files[0]; if (file) _handleImgUpload(file);
        });
    }
    if (DOM.removeAttachedDocumentButton) DOM.removeAttachedDocumentButton.addEventListener('click', _removeAttachedDoc);
    if (DOM.forceWebSearchButton) DOM.forceWebSearchButton.addEventListener('click', () => _sendMessage("[FORCE_WEB_SEARCH] "));
    if (DOM.microphoneButton) DOM.microphoneButton.addEventListener('click', _toggleListening);
    
    // getDailyBriefingButton's main click is handled by panel_manager to open panel

    if (DOM.systemPromptSave) {
        DOM.systemPromptSave.addEventListener('click', async () => {
            if (DOM.systemPromptInput) _setSystemPrompt(DOM.systemPromptInput.value.trim());
            if (DOM.modelTemperatureInput) {
                const tempVal = parseFloat(DOM.modelTemperatureInput.value);
                if (!isNaN(tempVal)) _setModelTemp(tempVal); else showNotification('Invalid Temp.', 'error');
            }
            let llmChanged = false;
            if (DOM.llmProviderUrlInput) {
                const newU = DOM.llmProviderUrlInput.value.trim(); const oldU = localStorage.getItem(LLM_PROVIDER_URL_KEY) || "";
                if (newU.startsWith('http')) { if (newU !== oldU) { _setLLMProviderUrl(newU); llmChanged = true; }}
                else if (!newU && oldU) { _setLLMProviderUrl(""); llmChanged = true; }
                else if (newU && !newU.startsWith('http')) { showNotification('Invalid LLM URL.', 'warning'); DOM.llmProviderUrlInput.value = oldU; }
            }
            let apiChanged = false;
            if (DOM.apiUrlInput) {
                const newApiU = DOM.apiUrlInput.value.trim();
                if (newApiU.startsWith('http') && newApiU !== _EIDOS_API_BASE_URL_GLOBAL()) { // Use getter
                    _setGlobalApiBaseUrl(newApiU); apiChanged = true;
                } else if (!newApiU) { showNotification('API URL empty.', 'warning'); DOM.apiUrlInput.value = _EIDOS_API_BASE_URL_GLOBAL(); }
                else if (newApiU && !newApiU.startsWith('http')) { showNotification('Invalid API URL.', 'warning'); DOM.apiUrlInput.value = _EIDOS_API_BASE_URL_GLOBAL(); }
            }
            if (DOM.apiKeyInput) _setAPIKey(DOM.apiKeyInput.value.trim());
            let userChanged = false;
            if (DOM.userIdInput) {
                const newUserId = DOM.userIdInput.value.trim();
                if (newUserId && newUserId !== _currentUserId()) { _setCurrentUserId(newUserId); userChanged = true; }
                else if (!newUserId) { showNotification('User ID empty.', 'warning'); DOM.userIdInput.value = _currentUserId(); }
            }
            let weatherChanged = false;
            if (DOM.weatherLocationInput) {
                const newWeatherLoc = DOM.weatherLocationInput.value.trim(); const oldWeatherLoc = localStorage.getItem(WEATHER_LOCATION_KEY) || "";
                if (newWeatherLoc && newWeatherLoc !== oldWeatherLoc) { _setWeatherLoc(newWeatherLoc); weatherChanged = true; }
                else if (!newWeatherLoc && oldWeatherLoc) { _setWeatherLoc(""); if (DOM.weatherPanel) DOM.weatherPanel.style.display = 'none'; weatherChanged = true; }
            }
            if (DOM.contextLengthInput) {
                const lenStr = DOM.contextLengthInput.value.trim();
                if (lenStr) { const lenVal = parseInt(lenStr, 10); if (!isNaN(lenVal) && lenVal >= 256 && lenVal <= 32000) _setContextLen(lenVal); else showNotification('Invalid Context Len.', 'error'); }
                else _setContextLen(null);
            }
            await _saveSettingsToBackend();
            if (apiChanged || userChanged) { if (window.eidosWebSocket?.readyState !== WebSocket.CLOSED) window.eidosWebSocket.close(1000, "Settings changed"); /* connectWebSocket called by onclose */ }
            if (llmChanged) _fetchModels(); 
            if (weatherChanged) _setupWeather();
            if (DOM.systemPromptPanel) DOM.systemPromptPanel.classList.remove('open');
            showNotification('Settings saved.', 'success');
        });
    }

    if (DOM.clearHistoryButton) DOM.clearHistoryButton.addEventListener('click', _clearAllLocalHistory);
    if (DOM.clearUserMemoryButton) DOM.clearUserMemoryButton.addEventListener('click', async () => { if (await _clearUserMemoryBE()) { _clearAllLocalHistory(); _resetChat(); }});
    if (DOM.clearBackendMemoryButton) DOM.clearBackendMemoryButton.addEventListener('click', async () => { if (await _clearEidosMemoryBE()) { _clearAllLocalHistory(); _resetChat(); }});
    if (DOM.weatherCloseButton && DOM.weatherPanel) DOM.weatherCloseButton.addEventListener('click', () => DOM.weatherPanel.style.display = 'none');
    if (DOM.weatherUpdateButton) DOM.weatherUpdateButton.addEventListener('click', () => {
        const loc = localStorage.getItem(WEATHER_LOCATION_KEY) || "";
        if (loc.trim()) { showNotification('Refreshing weather...', 'info'); _fetchWeather(loc).then(data => { if (data && typeof window.updateWeatherDisplay === 'function') window.updateWeatherDisplay(data); }); }
        else showNotification('Set weather location in Settings.', 'info');
    });

    if (DOM.refreshDailyBriefingButton) DOM.refreshDailyBriefingButton.addEventListener('click', _fetchDailyBriefing);
    if (DOM.refreshLearningLogButton) DOM.refreshLearningLogButton.addEventListener('click', _fetchLearnings);
    if (DOM.clearLearningLogDisplayButton && DOM.learningLogContentArea) DOM.clearLearningLogDisplayButton.addEventListener('click', () => { DOM.learningLogContentArea.innerHTML = '<p style="color: #888;">Display cleared.</p>'; });
    if (DOM.refreshDreamJournalButton) DOM.refreshDreamJournalButton.addEventListener('click', _fetchDreams);
    if (DOM.clearDreamJournalDisplayButton && DOM.dreamJournalContentArea) DOM.clearDreamJournalDisplayButton.addEventListener('click', () => { DOM.dreamJournalContentArea.innerHTML = '<p style="color: #888;">Display cleared.</p>'; });
    if (DOM.refreshKnowledgeLogButton) DOM.refreshKnowledgeLogButton.addEventListener('click', _fetchKnowledgeVerifications);
    if (DOM.clearKnowledgeLogDisplayButton && DOM.knowledgeLogContentArea) DOM.clearKnowledgeLogDisplayButton.addEventListener('click', () => { DOM.knowledgeLogContentArea.innerHTML = '<p style="color: #888;">Display cleared.</p>'; });
    if (DOM.clearProactiveButton && DOM.proactiveMessagesArea) DOM.clearProactiveButton.addEventListener('click', () => { DOM.proactiveMessagesArea.innerHTML = '<p style="color: #888;">No proactive messages yet.</p>'; showNotification('Proactive display cleared.', 'info'); });

    if (DOM.inputContainer) { /* ... (Drag-drop listeners as before, calling _handleDocUpload or _handleImgUpload) ... */ 
        DOM.inputContainer.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); DOM.inputContainer.classList.add('drag-over'); });
        DOM.inputContainer.addEventListener('dragleave', (e) => { e.preventDefault(); e.stopPropagation(); DOM.inputContainer.classList.remove('drag-over'); });
        DOM.inputContainer.addEventListener('drop', (e) => {
            e.preventDefault(); e.stopPropagation(); DOM.inputContainer.classList.remove('drag-over');
            const files = e.dataTransfer.files; if (files.length > 0) { const file = files[0]; const ext = file.name.split('.').pop().toLowerCase();
                if (['pdf', 'docx', 'txt'].includes(ext)) _handleDocUpload(file); else if (file.type.startsWith('image/')) _handleImgUpload(file);
                else showNotification(`Unsupported drop type: .${ext}`, 'warning');
            }
        });
    }
    console.log("Global event listeners set up.");
}
console.log("event_handlers.js loaded.");