// webapp/js/api_comms.js

import {
    EIDOS_API_BASE_URL,
    EIDOS_API_KEY_KEY,
    LLM_PROVIDER_URL_KEY,
    SELECTED_MODEL_KEY
} from './config.js';
import {
    userInput, sendButton, modelDisplayName, systemPromptInput,
    modelTemperatureInput, imageInput, contextLengthInput,
    llmProviderUrlInput, weatherLocationInput,
    uploadDocumentButton, uploadImageButton,
    resetChatButton, removeAttachedDocumentButton, forceWebSearchButton,
    microphoneButton,
    dropdownContent, modelSelect,
    documentInput
} from './dom_elements.js';
import {
    showNotification,
    autoAdjustTextareaHeight
} from './utils.js';
import {
    conversationHistory,
    saveCurrentActiveChat
} from './persistent_storage.js';

// --- Injected Dependencies (set by main.js) ---
let _displayMessageInChatFunc;
let _displayProactiveMessageInPanelFunc;
let _hideAttachedDocumentIndicatorFunc;
let _expandChatInterfaceFunc;
let _scrollToBottomFunc;
let _chatMessagesAreaFromMain;

export function setApiCommsDependencies(dependencies) {
    _displayMessageInChatFunc = dependencies.displayMessageInChat;
    _displayProactiveMessageInPanelFunc = dependencies.displayProactiveMessageInPanel;
    _hideAttachedDocumentIndicatorFunc = dependencies.hideAttachedDocumentIndicator;
    _expandChatInterfaceFunc = dependencies.expandChatInterface;
    _scrollToBottomFunc = dependencies.scrollToBottom;
    _chatMessagesAreaFromMain = dependencies.chatMessagesArea;
}

// --- Model Fetching and Selection ---
export async function fetchModels() {
    if (!dropdownContent || !modelDisplayName) {
        console.error("fetchModels (api_comms): Crucial DOM elements for model selection not found.");
        return;
    }
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    const dynamicLlmUrl = llmProviderUrlInput ? llmProviderUrlInput.value.trim() : localStorage.getItem(LLM_PROVIDER_URL_KEY);
    const effectiveLlmProviderUrl = (dynamicLlmUrl && dynamicLlmUrl.startsWith('http')) ? dynamicLlmUrl : currentApiBaseUrl;

    const modelsApiUrl = `${effectiveLlmProviderUrl.replace(/\/+$/, '')}/models`;
    console.log(`fetchModels (api_comms): Attempting to fetch models from: ${modelsApiUrl}`);
    dropdownContent.innerHTML = '<div>Loading models...</div>';

    try {
        const response = await fetch(modelsApiUrl);
        if (!response.ok) {
            if (dynamicLlmUrl && dynamicLlmUrl.startsWith('http') && dynamicLlmUrl !== currentApiBaseUrl) {
                 console.warn(`fetchModels (api_comms): Failed from dynamic URL (${response.status}). Fallback to Eidos API.`);
                 const fallbackModelsApiUrl = `${currentApiBaseUrl.replace(/\/+$/, '')}/models`;
                 const fallbackResponse = await fetch(fallbackModelsApiUrl);
                 if (!fallbackResponse.ok) throw new Error(`HTTP error! status: ${fallbackResponse.status} (fallback)`);
                 const fallbackData = await fallbackResponse.json();
                 populateModelSelector(fallbackData.data || [], currentApiBaseUrl);
                 return;
            }
            throw new Error(`HTTP error! status: ${response.status} from ${modelsApiUrl}`);
        }
        const data = await response.json();
        populateModelSelector(data.data || [], effectiveLlmProviderUrl);
    } catch (error) {
        console.error("fetchModels (api_comms): Error fetching models:", error);
        if (dropdownContent) dropdownContent.innerHTML = '<div>Error loading models</div>';
        if (modelDisplayName) modelDisplayName.textContent = 'Error';
        populateModelSelector([{id: "eidos-agent"}], currentApiBaseUrl);
    }
}

export function populateModelSelector(models, urlUsedForFetching = null) {
    if (!dropdownContent || !modelDisplayName) return;
    if (modelSelect) modelSelect.innerHTML = '';
    dropdownContent.innerHTML = '';

    let finalModels = models;
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;

    if (!finalModels || finalModels.length === 0) {
        finalModels = [{id: "eidos-agent"}];
        urlUsedForFetching = currentApiBaseUrl;
        console.warn("No models from API, defaulting to 'eidos-agent'.");
    }
    const eidosAgentExists = finalModels.some(model => model.id === "eidos-agent");
    if (!eidosAgentExists) finalModels.unshift({id: "eidos-agent"});

    finalModels.forEach(model => {
        if (modelSelect) {
            const option = document.createElement('option');
            option.value = model.id; option.textContent = model.id;
            modelSelect.appendChild(option);
        }
        const dropdownItem = document.createElement('div');
        dropdownItem.textContent = model.id;
        dropdownItem.dataset.modelName = model.id;
        dropdownItem.dataset.providerUrl = model.id === "eidos-agent" ? currentApiBaseUrl : (urlUsedForFetching || currentApiBaseUrl);
        dropdownItem.addEventListener('click', function() {
            selectModel(this.dataset.modelName, this.dataset.providerUrl);
            if(dropdownContent) dropdownContent.style.display = 'none';
        });
        dropdownContent.appendChild(dropdownItem);
    });

    const savedSelectedModel = localStorage.getItem(SELECTED_MODEL_KEY);
    let defaultModelId = "eidos-agent";
    let defaultProviderUrl = currentApiBaseUrl;
    if (savedSelectedModel) {
        const foundModelEntry = dropdownContent.querySelector(`div[data-model-name="${savedSelectedModel}"]`);
        if (foundModelEntry) {
            defaultModelId = savedSelectedModel;
            defaultProviderUrl = foundModelEntry.dataset.providerUrl || currentApiBaseUrl;
        } else {
             console.log(`populateModelSelector (api_comms): Saved model '${savedSelectedModel}' not found. Defaulting.`);
        }
    }
    selectModel(defaultModelId, defaultProviderUrl);
}

export function selectModel(modelName, providerUrl) {
     if (modelSelect) modelSelect.value = modelName;
     if (modelDisplayName) modelDisplayName.textContent = modelName;
     localStorage.setItem(SELECTED_MODEL_KEY, modelName);
     if (dropdownContent) {
        dropdownContent.querySelectorAll('div').forEach(item => {
            item.classList.toggle('selected', item.dataset.modelName === modelName);
        });
     }
     console.log(`selectModel (api_comms): Selected Model: ${modelName}, Provider URL: ${providerUrl}.`);
}

// --- Chat Messaging ---
export async function sendMessage(forceSearchPrefix = "") {
    if (!userInput || !sendButton || !modelDisplayName || !systemPromptInput || !modelTemperatureInput || !imageInput || !contextLengthInput || !llmProviderUrlInput || !weatherLocationInput) {
        console.error("sendMessage (api_comms): Critical DOM elements for request building missing.");
        showNotification("Error: UI components not ready.", "error");
        return { success: false, content: "[Error: UI components not ready]", metadata: {} };
    }

    const rawMessageText = userInput.value.trim();
    const messageText = forceSearchPrefix + rawMessageText;
    const selectedModelForAPI = modelDisplayName.textContent;
    const systemPromptText = systemPromptInput.value.trim();
    const attachedImageBase64 = imageInput.dataset.attachedImageBase64;
    const documentTextToSend = window.attachedDocumentText;
    const contextLengthOverrideValue = contextLengthInput.value ? parseInt(contextLengthInput.value, 10) : null;
    const llmProviderUrlOverrideValue = llmProviderUrlInput.value ? llmProviderUrlInput.value.trim() : null;

    if ((!rawMessageText && !forceSearchPrefix) && !attachedImageBase64 && !documentTextToSend || !selectedModelForAPI || window.isAwaitingResponse) {
         if ((!rawMessageText && !forceSearchPrefix) && !attachedImageBase64 && !documentTextToSend) {
            showNotification("Please enter a message, attach an image, or upload a document.", "info");
         }
         return { success: false, content: "[No input provided or awaiting response]", metadata: {} };
    }

    if (messageText || attachedImageBase64 || documentTextToSend) {
        if (typeof _expandChatInterfaceFunc === 'function') _expandChatInterfaceFunc();
    }

    window.isAwaitingResponse = true;
    if (sendButton) sendButton.disabled = true;
    if (userInput) userInput.disabled = true;
    if (uploadDocumentButton) uploadDocumentButton.disabled = true;
    if (uploadImageButton) uploadImageButton.disabled = true;
    if (resetChatButton) resetChatButton.disabled = true;
    if (removeAttachedDocumentButton) removeAttachedDocumentButton.disabled = true;
    if (forceWebSearchButton) forceWebSearchButton.disabled = true;
    if (microphoneButton) microphoneButton.disabled = true;

    const userMessageContent = [];
    if (messageText) userMessageContent.push({ type: "text", text: messageText });
    if (attachedImageBase64) userMessageContent.push({ type: "image_url", image_url: { url: `data:image/jpeg;base64,${attachedImageBase64}` } });
    if (documentTextToSend) {
         const formattedDocumentContent = `--- Uploaded Document Content ---\n${documentTextToSend}\n--- End Uploaded Document Content ---`;
         userMessageContent.push({ type: "text", text: formattedDocumentContent });
    }

    if (userMessageContent.length > 0) {
        if (typeof _displayMessageInChatFunc === 'function') _displayMessageInChatFunc("User", userMessageContent);
        conversationHistory.push({ role: "user", content: userMessageContent });
    } else if (conversationHistory.length > 0 && conversationHistory[conversationHistory.length-1].metadata?.injected_proactive) {
        const placeholderUserContent = "[Acknowledged Pathos's thought]";
        if (typeof _displayMessageInChatFunc === 'function') _displayMessageInChatFunc("User", placeholderUserContent);
        conversationHistory.push({ role: "user", content: placeholderUserContent });
    }

    if (userInput) userInput.value = '';
    if (typeof autoAdjustTextareaHeight === 'function' && userInput) autoAdjustTextareaHeight(userInput);
    if (imageInput) imageInput.dataset.attachedImageBase64 = '';
    window.attachedDocumentText = null;
    window.attachedDocumentName = null;
    if (typeof _hideAttachedDocumentIndicatorFunc === 'function') _hideAttachedDocumentIndicatorFunc();

    const messagesForApi = [];
    if (systemPromptText) messagesForApi.push({ role: "system", content: systemPromptText });
    messagesForApi.push(...conversationHistory);

    let apiResult;

    try {
        const requestBodyMetadata = {
            weather_location: weatherLocationInput.value ? weatherLocationInput.value.trim() : null,
            user_id: window.currentUserId
        };
        if (llmProviderUrlOverrideValue && llmProviderUrlOverrideValue.startsWith('http')) requestBodyMetadata.llm_provider_url_override = llmProviderUrlOverrideValue;
        if (contextLengthOverrideValue && !isNaN(contextLengthOverrideValue) && contextLengthOverrideValue > 0) requestBodyMetadata.max_tokens_override = contextLengthOverrideValue;
        if (selectedModelForAPI) requestBodyMetadata.pathos_model_override = selectedModelForAPI;

        if (conversationHistory.length >= 2) {
            const secondLastMessage = conversationHistory[conversationHistory.length - 2];
            const lastMessage = conversationHistory[conversationHistory.length - 1];
            if (secondLastMessage.role === 'assistant' && secondLastMessage.metadata?.injected_proactive === true && secondLastMessage.metadata?.proactive_utterance_id && lastMessage.role === 'user') {
                requestBodyMetadata.engaged_proactive_id = secondLastMessage.metadata.proactive_utterance_id;
                console.log("sendMessage (api_comms): Detected reply to injected proactive. Sending engaged_proactive_id:", requestBodyMetadata.engaged_proactive_id);
            }
        }

        const requestBody = {
            model: selectedModelForAPI, messages: messagesForApi,
            temperature: parseFloat(modelTemperatureInput.value), stream: false,
            user: window.currentUserId, metadata: requestBodyMetadata
        };
        const apiKey = localStorage.getItem(EIDOS_API_KEY_KEY);
        const headers = { 'Content-Type': 'application/json', 'X-User-Id': window.currentUserId };
        if (apiKey) headers['X-API-Key'] = apiKey;

        const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
        const response = await fetch(`${currentApiBaseUrl}/chat/completions`, { method: 'POST', headers: headers, body: JSON.stringify(requestBody) });
        const result = await response.json();
        console.log("Eidos API Response (api_comms):", result);

        let aiResponseContent = "[Error: No content from AI]";
        let responseMetadata = null;
        let responseUsage = result.usage;
        let toolCalls = null;

        if (result.choices?.[0]?.message) {
             const message = result.choices[0].message;
             responseMetadata = message.metadata;
             toolCalls = message.tool_calls;
             aiResponseContent = message.content || (toolCalls ? "[AI requested tool use]" : aiResponseContent);

             if (typeof _displayMessageInChatFunc === 'function') {
                _displayMessageInChatFunc("AI", aiResponseContent, {
                    usage: responseUsage,
                    hexus_scores: responseMetadata?.hexus_scores,
                    vision_llm_output: responseMetadata?.vision_llm_output,
                    mood_at_response: responseMetadata?.mood_at_response,
                    tool_calls_from_pathos: toolCalls
                });
             }
             conversationHistory.push({ role: "assistant", content: aiResponseContent, tool_calls: toolCalls, metadata: responseMetadata });
             apiResult = { success: true, content: aiResponseContent, metadata: responseMetadata };
        } else {
             if (typeof _displayMessageInChatFunc === 'function') {
                _displayMessageInChatFunc("AI", aiResponseContent, { usage: responseUsage });
             }
             conversationHistory.push({ role: "assistant", content: aiResponseContent });
             apiResult = { success: false, content: aiResponseContent, metadata: { usage: responseUsage } };
        }
        saveCurrentActiveChat();
    } catch (error) {
        console.error("Error sending message to Eidos (api_comms):", error);
        const errorMessage = `**Error:** ${error.message || "Unknown API call error."}`;
        if (typeof _displayMessageInChatFunc === 'function') {
            _displayMessageInChatFunc("AI", errorMessage, { usage: null });
        }
        conversationHistory.push({ role: "assistant", content: errorMessage });
        saveCurrentActiveChat();
        apiResult = { success: false, content: errorMessage, metadata: { usage: null } };
    } finally {
        window.isAwaitingResponse = false;
        if (sendButton) sendButton.disabled = false;
        if (userInput) userInput.disabled = false;
        if (uploadDocumentButton) uploadDocumentButton.disabled = false;
        if (uploadImageButton) uploadImageButton.disabled = false;
        if (resetChatButton) resetChatButton.disabled = false;
        if (removeAttachedDocumentButton) removeAttachedDocumentButton.disabled = false;
        if (forceWebSearchButton) forceWebSearchButton.disabled = false;
        if (microphoneButton) microphoneButton.disabled = false;

        if (window.proactiveReplyContextDisplay) window.proactiveReplyContextDisplay.style.display = 'none';
        if (userInput) userInput.placeholder = "How can I help you today?";
        if (userInput) userInput.focus();
        if (typeof _scrollToBottomFunc === 'function' && _chatMessagesAreaFromMain) {
            _scrollToBottomFunc(_chatMessagesAreaFromMain);
        }
    }
    return apiResult;
}

// --- Document and Image Upload API Calls ---
export async function handleDocumentUploadAPI(file) {
    if (!uploadDocumentButton || !documentInput) {
        console.error("handleDocumentUploadAPI: uploadDocumentButton or documentInput not found.");
        return;
    }
    const maxSizeInMB = 50; const maxSizeInBytes = maxSizeInMB * 1024 * 1024;
    if (file.size > maxSizeInBytes) { showNotification(`File too large: ${maxSizeInMB}MB max`, 'error'); documentInput.value = ''; return; }
    const formData = new FormData(); formData.append('file', file);
    uploadDocumentButton.disabled = true; showNotification(`Uploading "${file.name}"...`);
    try {
        const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
        const response = await fetch(`${currentApiBaseUrl}/documents/upload`, { method: 'POST', headers: { 'X-User-Id': window.currentUserId }, body: formData });
        const result = await response.json();
        if (response.ok && result.success && result.extracted_text) {
            window.attachedDocumentText = result.extracted_text; window.attachedDocumentName = file.name;
            if (typeof window.showAttachedDocumentIndicator === 'function') window.showAttachedDocumentIndicator(file.name);
            showNotification(`"${file.name}" processed. Attached to next message.`, 'success');
        } else {
             const errorMsg = result.message || `Failed to process ${file.name}.`;
             showNotification(`Upload failed: ${errorMsg}`, 'error'); console.error("Doc Upload Error:", response.status, result);
        }
    } catch (error) { console.error("Error uploading doc:", error); showNotification(`Error uploading "${file.name}": ${error.message}`, 'error');
    } finally { if (documentInput) documentInput.value = ''; if (uploadDocumentButton) uploadDocumentButton.disabled = false; }
}

export function handleImageUploadClientSide(file) {
     if (!imageInput) return;
     const reader = new FileReader();
     reader.onload = function(e) {
         const base64String = e.target.result.split(',')[1];
         imageInput.dataset.attachedImageBase64 = base64String;
         showNotification(`Image "${file.name}" attached.`, 'info');
     };
     reader.onerror = function() { showNotification('Error reading image.', 'error'); };
     reader.readAsDataURL(file);
}

// --- Other API Calls (Settings, Memory Clear, Weather) ---
export async function saveSettingsToBackendAPI(settingsToSyncPayload) {
    if (!window.currentUserId) {
        showNotification("Cannot save settings: User ID not set.", "error");
        return;
    }
    if (!settingsToSyncPayload || !settingsToSyncPayload.settings || settingsToSyncPayload.settings.length === 0) {
        console.log("No settings provided to sync with backend.");
        return;
    }
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    try {
        const payloadForApi = {
            user_id: window.currentUserId,
            settings: settingsToSyncPayload.settings
        };
        const response = await fetch(`${currentApiBaseUrl}/user/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-User-Id': window.currentUserId },
            body: JSON.stringify(payloadForApi)
        });
        const data = await response.json();
        if (response.ok && data.status === "success") {
            console.log("Settings successfully synced with backend.", data.details);
        } else {
            console.error("Failed to sync settings with backend:", response.status, data);
            showNotification(`Backend settings sync failed: ${data.message || response.statusText}`, 'error');
        }
    } catch (error) {
        console.error("Error sending settings to backend:", error);
        showNotification(`Error saving settings to backend: ${error.message}`, 'error');
    }
}

export async function clearUserBackendMemoryAPI() {
    if (!window.currentUserId) { showNotification("User ID not set.", "error"); return false; }
    if (confirm(`Clear ALL backend memory for user ${window.currentUserId}?`)) {
        showNotification("Requesting user memory clear...");
        try {
            const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
            const response = await fetch(`${currentApiBaseUrl}/memory/clear_user`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-User-Id': window.currentUserId }, body: JSON.stringify({ user_id: window.currentUserId }) });
            if (response.ok) { showNotification(`Backend memory for ${window.currentUserId} cleared.`, "success"); return true; }
            else { const errTxt = await response.text(); showNotification(`Failed to clear user memory: ${response.status}`, 'error'); console.error("User Memory Clear Error:", response.status, errTxt); return false; }
        } catch (error) { console.error("Error calling user memory clear API:", error); showNotification(`Error clearing user memory: ${error.message}`, 'error'); return false; }
    } return false;
}

export async function clearEidosBackendMemoryAPI() {
    const adminPw = prompt("Admin Password for ALL Eidos memory clear:");
    if (adminPw === null) { showNotification("Operation cancelled.", "info"); return false; }
    if (!adminPw) { showNotification("Admin password needed.", "warning"); return false; }
    if (confirm("Sure you want to clear ALL Eidos backend memory? This affects ALL users.")) {
         showNotification("Requesting Eidos memory clear...");
         try {
             const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
             const response = await fetch(`${currentApiBaseUrl}/memory/clear`, { method: 'POST', headers: { 'X-User-Id': window.currentUserId, 'X-Admin-Password': adminPw } });
             if (response.ok) { showNotification("Eidos backend memory cleared.", "success"); return true; }
             else {
                 const errTxt = await response.text(); let detail = `Failed to clear Eidos memory: ${response.status}`;
                 if (response.status === 401 || response.status === 403) detail = "Auth failed. Incorrect admin password?";
                 else { try { detail = JSON.parse(errTxt).detail || detail; } catch (e) {} }
                 showNotification(detail, 'error'); console.error("Backend Memory Clear Error:", response.status, errTxt); return false;
                }
         } catch (error) { console.error("Error calling backend memory clear API:", error); showNotification(`Error clearing Eidos memory: ${error.message}`, 'error'); return false; }
     } return false;
}

export async function fetchWeatherAPI(location) {
    if (!location?.trim()) { console.debug("No weather location for fetchWeatherAPI."); return null; }
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    if (!currentApiBaseUrl) { console.error("API URL not set for weather."); showNotification("API URL not set.", "error"); return null; }
    let baseUrl = currentApiBaseUrl; if (baseUrl.endsWith('/v1')) baseUrl = baseUrl.substring(0, baseUrl.length - 3);
    const weatherApiUrl = `${baseUrl}/v1/weather?location=${encodeURIComponent(location.trim())}`;
    console.log(`Fetching weather for "${location}" from: ${weatherApiUrl}`);
    try {
        const response = await fetch(weatherApiUrl, { method: 'GET', headers: { 'X-User-Id': window.currentUserId } });
        const result = await response.json(); console.log("Weather API Response (fetchWeatherAPI):", result);
        if (response.ok && result.success && result.weather_data) return result.weather_data;
        else { const err = result.message || result.error || `Failed for ${location}.`; console.error("Weather API Error (fetchWeatherAPI):", response.status, result); showNotification(`Weather fetch failed: ${err}`, 'error'); return null; }
    } catch (error) { console.error(`Error fetching weather (fetchWeatherAPI) for ${location}:`, error); showNotification(`Weather fetch error: ${error.message || 'Unknown'}`, 'error'); return null; }
}

// --- WebSocket Connection ---
export function connectWebSocket() {
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    let wsBaseUrl = currentApiBaseUrl.replace(/^http/, 'ws').replace(/\/v1\/?$/, '');
    if (!wsBaseUrl.endsWith('/')) wsBaseUrl = wsBaseUrl.replace(/\/ws$/, '');
    const wsUrl = `${wsBaseUrl}/ws`;

    console.log(`Attempting WebSocket connection to: ${wsUrl}`);

    if (window.eidosWebSocket && window.eidosWebSocket.readyState !== WebSocket.CLOSED && window.eidosWebSocket.readyState !== WebSocket.CLOSING) {
        console.log("Closing existing WebSocket connection before reconnecting.");
        window.eidosWebSocket.close(1000, "Reconnecting");
    }

    try {
        window.eidosWebSocket = new WebSocket(wsUrl);
        window.eidosWebSocket.onopen = function(event) {
            console.log("WebSocket connection opened:", event);
            if (window.currentUserId) {
                window.eidosWebSocket.send(JSON.stringify({ type: "auth", payload: { userId: window.currentUserId } }));
                console.log("Sent user ID over WebSocket:", window.currentUserId);
            } else {
                console.warn("WebSocket opened but currentUserId is not set.");
            }
        };
        window.eidosWebSocket.onmessage = function(event) {
            console.log("WebSocket message received:", event.data);
            try {
                const message = JSON.parse(event.data);
                if (message.type === "unsolicited_message") {
                    if (message.payload && message.payload.content) {
                        console.log("Received unsolicited_message of proactive_type:", message.payload.metadata?.proactive_type);
                        if (typeof _displayProactiveMessageInPanelFunc === 'function') {
                            _displayProactiveMessageInPanelFunc(message.payload.content, message.payload.metadata);
                        }
                        showNotification("New proactive message from Pathos!", "info");
                    }
                } else if (message.type === "status") {
                    if (message.payload && message.payload.message) {
                        console.log("Eidos Status via WebSocket:", message.payload.message);
                    }
                } else if (message.type === "error") {
                    if (message.payload && message.payload.message) {
                        console.error("Eidos WebSocket Error:", message.payload.message);
                        showNotification(`Eidos Error: ${message.payload.message}`, "error");
                    }
                }
            } catch (e) {
                console.error("Failed to parse WebSocket message:", e, event.data);
            }
        };
        window.eidosWebSocket.onclose = function(event) {
            console.log("WebSocket connection closed:", event.code, event.reason);
            window.eidosWebSocket = null;
            if (event.code !== 1000 && event.code !== 1005) {
                console.log(`WebSocket closed unexpectedly (code: ${event.code}). Attempting to reconnect in 5s...`);
                setTimeout(connectWebSocket, 5000);
            } else {
                console.log("WebSocket closed cleanly or as expected.");
            }
        };
        window.eidosWebSocket.onerror = function(event) {
            console.error("WebSocket error event:", event);
        };
    } catch (e) {
        console.error("WebSocket connection attempt failed (exception):", e);
        window.eidosWebSocket = null;
        setTimeout(connectWebSocket, 10000);
    }
}

console.log("api_comms.js loaded.");