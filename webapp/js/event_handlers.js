// webapp/js/event_handlers.js

import * as DOM from './dom_elements.js';
import { showNotification } from './utils.js'; // Import showNotification

let _sendMessage, _handleDocumentUploadAPI, _handleImageUploadClientSide, _removeAttachedDocument,
    _toggleListening, _resetChat, _clearAllLocalHistory, _saveSettingsToBackendAPI,
    _clearUserMemoryBE, _clearEidosMemoryBE, _fetchModels, _fetchWeatherAPI, _setupWeatherUpdates,
    _fetchAndDisplayDailyBriefingGUI, _fetchAndDisplayLearnings, _fetchAndDisplayDreams,
    _fetchAndDisplayKnowledgeVerifications, _fetchAndDisplayUserFacts, _fetchUserFacts, _currentUserId,
    _EIDOS_API_BASE_URL_GLOBAL, _setCurrentUserId, _setGlobalApiBaseUrl, _setAPIKey,
    _setLLMProviderUrl, _setWeatherLoc, _setSystemPrompt, _setModelTemp, _setContextLen,
    _addPathosEventAPI, _setAdminPassword; // NEW: For setting admin password

export function injectDependencies(dependencies) {
    _sendMessage = dependencies.sendMessage;
    _handleDocumentUploadAPI = dependencies.handleDocumentUploadAPI;
    _handleImageUploadClientSide = dependencies.handleImageUploadClientSide;
    _removeAttachedDocument = dependencies.removeAttachedDocument;
    _toggleListening = dependencies.toggleListening;
    _resetChat = dependencies.resetChat;
    _clearAllLocalHistory = dependencies.clearAllLocalChatHistory;
    _saveSettingsToBackendAPI = dependencies.saveSettingsToBackendAPI;
    _clearUserMemoryBE = dependencies.clearUserBackendMemoryAPI;
    _clearEidosMemoryBE = dependencies.clearEidosBackendMemoryAPI;
    _fetchModels = dependencies.fetchModels;
    _fetchWeatherAPI = dependencies.fetchWeatherAPI;
    _setupWeatherUpdates = dependencies.setupWeatherUpdates;
    _fetchAndDisplayDailyBriefingGUI = dependencies.fetchAndDisplayDailyBriefingGUI;
    _fetchAndDisplayLearnings = dependencies.fetchAndDisplayLearnings;
    _fetchAndDisplayDreams = dependencies.fetchAndDisplayDreams;
    _fetchAndDisplayKnowledgeVerifications = dependencies.fetchAndDisplayKnowledgeVerifications;
    _fetchAndDisplayUserFacts = dependencies.fetchAndDisplayUserFacts;
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
    _addPathosEventAPI = dependencies.addPathosEventAPI; // NEW: Get the injected function
    _setAdminPassword = dependencies.setAdminPassword; // NEW: Get the injected function
}

export function setupGlobalEventListeners() {
    if (DOM.sendButton && typeof _sendMessage === 'function') {
        DOM.sendButton.addEventListener('click', () => _sendMessage());
    }

    if (DOM.uploadDocumentButton && typeof _handleDocumentUploadAPI === 'function') {
        DOM.uploadDocumentButton.addEventListener('click', () => {
            if (DOM.documentInput) DOM.documentInput.click();
        });
        if (DOM.documentInput) {
            DOM.documentInput.addEventListener('change', () => _handleDocumentUploadAPI(DOM.documentInput.files[0]));
        }
    }    if (DOM.uploadImageButton && typeof _handleImageUploadClientSide === 'function') {
        DOM.uploadImageButton.addEventListener('click', () => {
            if (DOM.imageInput) DOM.imageInput.click();
        });
        if (DOM.imageInput) {
            DOM.imageInput.addEventListener('change', () => _handleImageUploadClientSide(DOM.imageInput.files[0]));
        }
    }
    
    // Handle the new file upload button in chat input area
    if (DOM.fileUploadButton && DOM.fileInput) {
        DOM.fileUploadButton.addEventListener('click', () => {
            if (DOM.fileInput) DOM.fileInput.click();
        });
        
        if (DOM.fileInput) {
            DOM.fileInput.addEventListener('change', () => {
                const file = DOM.fileInput.files[0];
                if (!file) return;
                
                console.log(`File selected via button: ${file.name}, type: ${file.type}`);
                
                // Process based on file type
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
                    if (typeof _handleDocumentUploadAPI === 'function') {
                        _handleDocumentUploadAPI(file);
                    }
                } else if (
                    file.type.startsWith('image/') || 
                    ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(fileExt)
                ) {
                    // Process image
                    if (typeof _handleImageUploadClientSide === 'function') {
                        _handleImageUploadClientSide(file);
                    }
                } else {
                    showNotification('Only PDF, DOCX, TXT, or image files are supported for upload.', 'error');
                }
                
                // Reset the file input
                DOM.fileInput.value = '';
            });
        }
    }

    if (DOM.removeAttachedDocumentButton && typeof _removeAttachedDocument === 'function') {
        DOM.removeAttachedDocumentButton.addEventListener('click', () => _removeAttachedDocument());
    }

    if (DOM.microphoneButton && typeof _toggleListening === 'function') {
        DOM.microphoneButton.addEventListener('click', () => _toggleListening());
    }

    if (DOM.resetChatButton && typeof _resetChat === 'function') {
        DOM.resetChatButton.addEventListener('click', () => _resetChat());
    }

    if (DOM.clearHistoryButton && typeof _clearAllLocalHistory === 'function') {
        console.log("Attaching listener to clearHistoryButton");
        DOM.clearHistoryButton.addEventListener('click', () => {
            console.log("clearHistoryButton CLICKED");
            _clearAllLocalHistory();
        });
    } else {
        console.error("Failed to attach listener to clearHistoryButton. Button exists:", !!DOM.clearHistoryButton, "Function exists:", typeof _clearAllLocalHistory);
    }

    if (DOM.clearUserMemoryButton && typeof _clearUserMemoryBE === 'function') {
        console.log("Attaching listener to clearUserMemoryButton");
        DOM.clearUserMemoryButton.addEventListener('click', async () => {
            console.log("clearUserMemoryButton CLICKED");
            if (await _clearUserMemoryBE()) {
                if (typeof _clearAllLocalHistory === 'function') _clearAllLocalHistory();
                if (typeof _resetChat === 'function') _resetChat();
            }
        });
    } else {
        console.error("Failed to attach listener to clearUserMemoryButton. Button exists:", !!DOM.clearUserMemoryButton, "Function exists:", typeof _clearUserMemoryBE);
    }

    if (DOM.clearBackendMemoryButton && typeof _clearEidosMemoryBE === 'function') {
        console.log("Attaching listener to clearBackendMemoryButton");
        DOM.clearBackendMemoryButton.addEventListener('click', async () => {
            console.log("clearBackendMemoryButton CLICKED");
            if (await _clearEidosMemoryBE()) {
                if (typeof _clearAllLocalHistory === 'function') _clearAllLocalHistory();
                if (typeof _resetChat === 'function') _resetChat();
            }
        });
    } else {
        console.error("Failed to attach listener to clearBackendMemoryButton. Button exists:", !!DOM.clearBackendMemoryButton, "Function exists:", typeof _clearEidosMemoryBE);
    }

    if (DOM.systemPromptSave && typeof _saveSettingsToBackendAPI === 'function') {
        DOM.systemPromptSave.addEventListener('click', () => {
            // Call existing setters for other settings
            if (DOM.apiUrlInput && typeof _setGlobalApiBaseUrl === 'function') _setGlobalApiBaseUrl(DOM.apiUrlInput.value);
            if (DOM.apiKeyInput && typeof _setAPIKey === 'function') _setAPIKey(DOM.apiKeyInput.value);
            if (DOM.llmProviderUrlInput && typeof _setLLMProviderUrl === 'function') _setLLMProviderUrl(DOM.llmProviderUrlInput.value);
            if (DOM.userIdInput && typeof _setCurrentUserId === 'function') _setCurrentUserId(DOM.userIdInput.value);
            if (DOM.weatherLocationInput && typeof _setWeatherLoc === 'function') _setWeatherLoc(DOM.weatherLocationInput.value);
            if (DOM.modelTemperatureInput && typeof _setModelTemp === 'function') _setModelTemp(parseFloat(DOM.modelTemperatureInput.value));
            if (DOM.contextLengthInput && typeof _setContextLen === 'function') _setContextLen(DOM.contextLengthInput.value ? parseInt(DOM.contextLengthInput.value, 10) : null);
            if (DOM.systemPromptInput && typeof _setSystemPrompt === 'function') _setSystemPrompt(DOM.systemPromptInput.value);

            // NEW: Save Admin Password
            if (DOM.adminPasswordInput && typeof _setAdminPassword === 'function') {
                _setAdminPassword(DOM.adminPasswordInput.value);
            }

            showNotification("Settings saved to browser's local storage.", "success");

            // Prepare payload for backend sync (if needed)
            const settingsToSync = [];
            if (DOM.weatherLocationInput && DOM.weatherLocationInput.value.trim()) {
                settingsToSync.push({
                    attribute_name: "preferred_location",
                    attribute_value: DOM.weatherLocationInput.value.trim(),
                    user_statement_context: "User set preferred weather location via GUI settings."
                });
            }
            // Add other settings to sync to backend if necessary

            if (settingsToSync.length > 0 && typeof _saveSettingsToBackendAPI === 'function') {
                _saveSettingsToBackendAPI({ settings: settingsToSync });
            }
        });
    }

    if (DOM.refreshDailyBriefingButton && typeof _fetchAndDisplayDailyBriefingGUI === 'function') {
        DOM.refreshDailyBriefingButton.addEventListener('click', () => _fetchAndDisplayDailyBriefingGUI());
    }

    if (DOM.refreshLearningLogButton && typeof _fetchAndDisplayLearnings === 'function') {
        DOM.refreshLearningLogButton.addEventListener('click', () => _fetchAndDisplayLearnings());
    }

    if (DOM.refreshDreamJournalButton && typeof _fetchAndDisplayDreams === 'function') {
        DOM.refreshDreamJournalButton.addEventListener('click', () => _fetchAndDisplayDreams());
    }

    if (DOM.refreshKnowledgeLogButton && typeof _fetchAndDisplayKnowledgeVerifications === 'function') {
        DOM.refreshKnowledgeLogButton.addEventListener('click', () => _fetchAndDisplayKnowledgeVerifications());
    }

    if (DOM.refreshUserFactsButton && typeof _fetchUserFacts === 'function') {
        DOM.refreshUserFactsButton.addEventListener('click', _fetchUserFacts);
    }

    if (DOM.weatherUpdateButton && typeof _setupWeatherUpdates === 'function') {
        DOM.weatherUpdateButton.addEventListener('click', () => _setupWeatherUpdates());
    }

    if (DOM.weatherCloseButton && DOM.weatherPanel) {
        DOM.weatherCloseButton.addEventListener('click', () => {
            DOM.weatherPanel.style.display = 'none';
        });
    }

    if (DOM.apiUrlInput) {
        DOM.apiUrlInput.addEventListener('change', () => _setGlobalApiBaseUrl(DOM.apiUrlInput.value));
    }

    if (DOM.apiKeyInput) {
        DOM.apiKeyInput.addEventListener('change', () => _setAPIKey(DOM.apiKeyInput.value));
    }

    if (DOM.llmProviderUrlInput) {
        DOM.llmProviderUrlInput.addEventListener('change', () => _setLLMProviderUrl(DOM.llmProviderUrlInput.value));
    }

    if (DOM.weatherLocationInput) {
        DOM.weatherLocationInput.addEventListener('change', () => _setWeatherLoc(DOM.weatherLocationInput.value));
    }

    if (DOM.systemPromptInput) {
        DOM.systemPromptInput.addEventListener('change', () => _setSystemPrompt(DOM.systemPromptInput.value));
    }

    if (DOM.modelTemperatureInput) {
        DOM.modelTemperatureInput.addEventListener('change', () => _setModelTemp(parseFloat(DOM.modelTemperatureInput.value)));
    }

    if (DOM.contextLengthInput) {
        DOM.contextLengthInput.addEventListener('change', () => _setContextLen(parseInt(DOM.contextLengthInput.value, 10)));
    }

    if (DOM.userIdInput) {
        DOM.userIdInput.addEventListener('change', () => _setCurrentUserId(DOM.userIdInput.value));
    }

    // NEW: Event listener for saving Pathos event
    if (DOM.savePathosEventButton && typeof _addPathosEventAPI === 'function') {
        DOM.savePathosEventButton.addEventListener('click', async () => {
            const title = DOM.pathosEventTitleInput.value.trim();
            const startDate = DOM.pathosEventStartDateInput.value;
            const endDate = DOM.pathosEventEndDateInput.value;
            const eventType = DOM.pathosEventTypeSelect.value;
            const description = DOM.pathosEventDescriptionInput.value.trim();
            const location = DOM.pathosEventLocationInput.value.trim();
            const activityTheme = DOM.pathosEventThemeInput.value.trim();
            const tasksInput = DOM.pathosEventTasksInput.value.trim();

            const plannedSitesOrTasks = tasksInput ? tasksInput.split('\n').map(task => task.trim()).filter(task => task) : null;

            // Basic Validation
            if (!title) { showNotification("Event Title is required.", "error"); DOM.pathosEventTitleInput.focus(); return; }
            if (!startDate) { showNotification("Start Date is required.", "error"); DOM.pathosEventStartDateInput.focus(); return; }
            if (!endDate) { showNotification("End Date is required.", "error"); DOM.pathosEventEndDateInput.focus(); return; }
            if (new Date(endDate) < new Date(startDate)) { showNotification("End Date cannot be before Start Date.", "error"); DOM.pathosEventEndDateInput.focus(); return; }
            if (!eventType) { showNotification("Event Type is required.", "error"); DOM.pathosEventTypeSelect.focus(); return; }

            const eventData = {
                title: title,
                start_date: startDate,
                end_date: endDate,
                event_type: eventType,
                description: description || null,
                location: location || null,
                details: {
                    activity_theme: activityTheme || null,
                    planned_sites_or_tasks: plannedSitesOrTasks
                }
            };
            // Remove null details if empty
            if (eventData.details && !eventData.details.activity_theme && (!eventData.details.planned_sites_or_tasks || eventData.details.planned_sites_or_tasks.length === 0)) {
                eventData.details = null;
            }
            if (eventData.details && eventData.details.planned_sites_or_tasks === null) delete eventData.details.planned_sites_or_tasks;
            if (eventData.details && eventData.details.activity_theme === null) delete eventData.details.activity_theme;

            const success = await _addPathosEventAPI(eventData);
            if (success) {
                // Optionally clear form and close panel
                DOM.pathosEventTitleInput.value = '';
                DOM.pathosEventStartDateInput.value = '';
                DOM.pathosEventEndDateInput.value = '';
                DOM.pathosEventTypeSelect.value = '';
                DOM.pathosEventDescriptionInput.value = '';
                DOM.pathosEventLocationInput.value = '';
                DOM.pathosEventThemeInput.value = '';
                DOM.pathosEventTasksInput.value = '';
                if (DOM.addPathosEventPanel && typeof window.closeAllSidePanels === 'function') {
                    DOM.addPathosEventPanel.classList.remove('open');
                }
            }
        });
    } else {
        console.warn("Save Pathos Event button or API function not available.");
    }

    console.log("Global event listeners set up (with Admin Password handling in settings).");
}
console.log("event_handlers.js loaded (with Add Pathos Event).");