// webapp/js/api_comms.js

import {
    EIDOS_API_KEY_KEY,
    LLM_PROVIDER_URL_KEY,
    SELECTED_MODEL_KEY,
    WEATHER_LOCATION_KEY
} from './config.js';

import * as DOM from './dom_elements.js'; 

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
let _chatMessagesAreaFromMain; // This is the actual DOM element from main.js

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
    if (!DOM.dropdownContent || !DOM.modelDisplayName) {
        console.error("fetchModels (api_comms): Crucial DOM elements for model selection not found.");
        return;
    }
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL;
    const dynamicLlmUrl = DOM.llmProviderUrlInput ? DOM.llmProviderUrlInput.value.trim() : localStorage.getItem(LLM_PROVIDER_URL_KEY);
    const effectiveLlmProviderUrl = (dynamicLlmUrl && dynamicLlmUrl.startsWith('http')) ? dynamicLlmUrl : currentApiBaseUrl;

    const modelsApiUrl = `${effectiveLlmProviderUrl.replace(/\/+\$/, '')}/models`;
    console.log(`fetchModels (api_comms): Attempting to fetch models from: ${modelsApiUrl}`);
    DOM.dropdownContent.innerHTML = '<div>Loading models...</div>';

    try {
        const response = await fetch(modelsApiUrl);
        if (!response.ok) {
            if (dynamicLlmUrl && dynamicLlmUrl.startsWith('http') && dynamicLlmUrl !== currentApiBaseUrl) {
                console.warn(`fetchModels (api_comms): Failed from dynamic URL (${response.status}). Attempting fallback to Eidos API /v1/models.`);
                const fallbackModelsApiUrl = `${currentApiBaseUrl.replace(/\/+\$/, '')}/models`;
                const fallbackResponse = await fetch(fallbackModelsApiUrl);
                if (!fallbackResponse.ok) {
                    console.error(`fetchModels (api_comms): Fallback to Eidos /v1/models also failed. Status: ${fallbackResponse.status}`);
                    throw new Error(`HTTP error! status: ${fallbackResponse.status} (fallback to Eidos /v1/models)`);
                }
                const fallbackData = await fallbackResponse.json();
                populateModelSelector(fallbackData.data || [], currentApiBaseUrl);
                return;
            }
            console.error(`fetchModels (api_comms): Initial model fetch failed. Status: ${response.status} from ${modelsApiUrl}`);
            throw new Error(`HTTP error! status: ${response.status} from ${modelsApiUrl}`);
        }
        const data = await response.json();
        populateModelSelector(data.data || [], effectiveLlmProviderUrl);
    } catch (error) {
        console.error("fetchModels (api_comms): Error fetching models:", error);
        DOM.dropdownContent.innerHTML = '<div>Error loading models</div>';
        DOM.modelDisplayName.textContent = 'Error';
        populateModelSelector([{ id: "eidos-agent" }], currentApiBaseUrl);
    }
}

export function populateModelSelector(models, urlUsedForFetching = null) {
    if (!DOM.dropdownContent || !DOM.modelDisplayName) return;
    if (DOM.modelSelect) DOM.modelSelect.innerHTML = '';
    DOM.dropdownContent.innerHTML = '';

    let finalModels = Array.isArray(models) ? models : [];
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL;

    if (finalModels.length === 0) {
        finalModels = [{ id: "eidos-agent" }];
        urlUsedForFetching = currentApiBaseUrl;
        console.warn("populateModelSelector: No models provided or API returned empty, defaulting to 'eidos-agent'.");
    }
    const eidosAgentExists = finalModels.some(model => model.id === "eidos-agent");
    if (!eidosAgentExists) {
        finalModels.unshift({ id: "eidos-agent" });
    }

    finalModels.forEach(model => {
        if (DOM.modelSelect) {
            const option = document.createElement('option');
            option.value = model.id;
            option.textContent = model.id;
            DOM.modelSelect.appendChild(option);
        }
        const dropdownItem = document.createElement('div');
        dropdownItem.textContent = model.id;
        dropdownItem.dataset.modelName = model.id;
        dropdownItem.dataset.providerUrl = model.id === "eidos-agent" ? currentApiBaseUrl : (urlUsedForFetching || currentApiBaseUrl);
        dropdownItem.addEventListener('click', function () {
            selectModel(this.dataset.modelName, this.dataset.providerUrl);
            if (DOM.dropdownContent) DOM.dropdownContent.style.display = 'none';
        });
        DOM.dropdownContent.appendChild(dropdownItem);
    });

    const savedSelectedModel = localStorage.getItem(SELECTED_MODEL_KEY);
    let defaultModelId = "eidos-agent";
    let defaultProviderUrl = currentApiBaseUrl;

    if (savedSelectedModel) {
        const foundModelEntry = DOM.dropdownContent.querySelector(`div[data-model-name="${savedSelectedModel}"]`);
        if (foundModelEntry) {
            defaultModelId = savedSelectedModel;
            defaultProviderUrl = foundModelEntry.dataset.providerUrl || currentApiBaseUrl;
        } else {
            console.log(`populateModelSelector: Saved model '${savedSelectedModel}' not found. Defaulting to 'eidos-agent'.`);
        }
    }
    selectModel(defaultModelId, defaultProviderUrl);
}

export function selectModel(modelName, providerUrl) {
    if (DOM.modelSelect) DOM.modelSelect.value = modelName;
    if (DOM.modelDisplayName) DOM.modelDisplayName.textContent = modelName;
    localStorage.setItem(SELECTED_MODEL_KEY, modelName);

    if (DOM.dropdownContent) {
        DOM.dropdownContent.querySelectorAll('div').forEach(item => {
            item.classList.toggle('selected', item.dataset.modelName === modelName);
        });
    }
    console.log(`selectModel (api_comms): Selected Model: ${modelName}. (Associated fetch URL: ${providerUrl})`);
}


// --- Chat Messaging ---
export async function sendMessage(forceSearchPrefix = "") {
    // Ensure DOM elements are ready (using DOM. prefix for clarity)
    if (!DOM.userInput || !DOM.sendButton || !DOM.modelDisplayName || !DOM.systemPromptInput ||
        !DOM.modelTemperatureInput || !DOM.imageInput || !DOM.contextLengthInput ||
        !DOM.llmProviderUrlInput || !DOM.weatherLocationInput) { // DOM.weatherLocationInput for reading its value
        console.error("sendMessage (api_comms): Critical DOM elements for request building missing.");
        showNotification("Error: UI components not ready.", "error");
        return { success: false, content: "[Error: UI components not ready]", metadata: {} };
    }

    const rawMessageText = DOM.userInput.value.trim();
    const messageText = forceSearchPrefix + rawMessageText;
    const selectedModelForAPI = DOM.modelDisplayName.textContent; // Model selected in GUI
    const systemPromptText = DOM.systemPromptInput.value.trim();
    const attachedImageBase64 = DOM.imageInput.dataset.attachedImageBase64;
    const documentTextToSend = window.attachedDocumentText; // Global from main.js
    const contextLengthOverrideValue = DOM.contextLengthInput.value ? parseInt(DOM.contextLengthInput.value, 10) : null;
    // This is the user-configurable override for Pathos LLM provider URL from settings
    const llmProviderUrlOverrideValue = DOM.llmProviderUrlInput.value ? DOM.llmProviderUrlInput.value.trim() : null;


    if ((!rawMessageText && !forceSearchPrefix) && !attachedImageBase64 && !documentTextToSend) {
         if (window.isAwaitingResponse) { /* Do nothing */ }
         else { showNotification("Please enter a message, attach an image, or upload a document.", "info"); }
         return { success: false, content: "[No input provided or awaiting response]", metadata: {} };
    }
    if (window.isAwaitingResponse) {
        showNotification("Please wait for the current response.", "info");
        return { success: false, content: "[Awaiting previous response]", metadata: {} };
    }

    if (messageText || attachedImageBase64 || documentTextToSend) {
        if (typeof _expandChatInterfaceFunc === 'function') _expandChatInterfaceFunc();
    }

    window.isAwaitingResponse = true;
    // Disable UI elements
    if (DOM.sendButton) DOM.sendButton.disabled = true;
    if (DOM.userInput) DOM.userInput.disabled = true;
    if (DOM.uploadDocumentButton) DOM.uploadDocumentButton.disabled = true;
    if (DOM.uploadImageButton) DOM.uploadImageButton.disabled = true;
    if (DOM.resetChatButton) DOM.resetChatButton.disabled = true;
    if (DOM.removeAttachedDocumentButton) DOM.removeAttachedDocumentButton.disabled = true;
    if (DOM.forceWebSearchButton) DOM.forceWebSearchButton.disabled = true;
    if (DOM.microphoneButton) DOM.microphoneButton.disabled = true;

    const userMessageContent = [];
    if (messageText) userMessageContent.push({ type: "text", text: messageText });
    if (attachedImageBase64) userMessageContent.push({ type: "image_url", image_url: { url: `data:image/jpeg;base64,${attachedImageBase64}` } });
    if (documentTextToSend) userMessageContent.push({ type: "text", text: `--- Uploaded Document Content ---\n${documentTextToSend}\n--- End Uploaded Document Content ---` });

    if (userMessageContent.length > 0) {
        if (typeof _displayMessageInChatFunc === 'function') _displayMessageInChatFunc("User", userMessageContent);
        conversationHistory.push({ role: "user", content: userMessageContent });
        window.isFirstMessageInSession = false;
    } else if (conversationHistory.length > 0 && conversationHistory[conversationHistory.length-1].metadata?.injected_proactive) {
        const placeholderUserContent = "[Acknowledged Pathos's thought]";
        if (typeof _displayMessageInChatFunc === 'function') _displayMessageInChatFunc("User", placeholderUserContent);
        conversationHistory.push({ role: "user", content: placeholderUserContent });
        window.isFirstMessageInSession = false;
    }

    if (DOM.userInput) DOM.userInput.value = '';
    if (typeof autoAdjustTextareaHeight === 'function' && DOM.userInput) autoAdjustTextareaHeight(DOM.userInput);
    if (DOM.imageInput) DOM.imageInput.dataset.attachedImageBase64 = '';
    window.attachedDocumentText = null; window.attachedDocumentName = null;
    if (typeof _hideAttachedDocumentIndicatorFunc === 'function') _hideAttachedDocumentIndicatorFunc();

    const messagesForApi = [];
    if (systemPromptText) messagesForApi.push({ role: "system", content: systemPromptText });
    messagesForApi.push(...conversationHistory);

    let apiResult = { success: false, content: "[Error: API call did not complete]", metadata: {} };

    try {
        const requestBodyMetadata = {
            user_id: window.currentUserId, // Normalized global from main.js
            auto_tts_enabled_for_response: window.autoTtsEnabled, // Global from main.js
            pathos_model_override: selectedModelForAPI // The model selected in the GUI dropdown
        };

        // Weather location from localStorage (set by settings panel)
        const weatherLoc = localStorage.getItem(WEATHER_LOCATION_KEY);
        if (weatherLoc && weatherLoc.trim()) {
            if (window.isFirstMessageInSession || window.weatherLocationChangedThisSession) {
                requestBodyMetadata.weather_location = weatherLoc.trim();
                if (window.weatherLocationChangedThisSession) window.weatherLocationChangedThisSession = false;
            }
        }
        // LLM Provider URL Override from settings input
        if (llmProviderUrlOverrideValue && llmProviderUrlOverrideValue.startsWith('http')) {
            requestBodyMetadata.llm_provider_url_override = llmProviderUrlOverrideValue;
        }
        // Context Length Override from settings input
        if (contextLengthOverrideValue && !isNaN(contextLengthOverrideValue) && contextLengthOverrideValue > 0) {
            requestBodyMetadata.max_tokens_override = contextLengthOverrideValue;
        }
        // Engaged Proactive ID
        const lastHistMessage = conversationHistory.length > 0 ? conversationHistory[conversationHistory.length - 1] : null;
        const secondLastHistMessage = conversationHistory.length > 1 ? conversationHistory[conversationHistory.length - 2] : null;
        if (secondLastHistMessage && lastHistMessage &&
            secondLastHistMessage.role === 'assistant' &&
            secondLastHistMessage.metadata?.injected_proactive === true &&
            secondLastHistMessage.metadata?.proactive_utterance_id &&
            lastHistMessage.role === 'user') {
            requestBodyMetadata.engaged_proactive_id = secondLastHistMessage.metadata.proactive_utterance_id;
        }

        const requestBody = {
            model: selectedModelForAPI, // This is what Open WebUI expects at top level
            messages: messagesForApi,
            temperature: parseFloat(DOM.modelTemperatureInput.value),
            stream: false, // Main HTTP response for GUI text is NOT streamed
            user: window.currentUserId, // OpenAI compatible user field
            metadata: requestBodyMetadata // Eidos-specific nested metadata
        };

        const apiKey = localStorage.getItem(EIDOS_API_KEY_KEY);
        const headers = {
            'Content-Type': 'application/json',
            'X-User-Id': window.currentUserId // Eidos custom header
        };
        // For other API providers if Eidos were to proxy them, or if Eidos itself used this key
        // if (apiKey && apiKey.toLowerCase() !== 'lm-studio' && apiKey.toLowerCase() !== 'ollama' && apiKey.toLowerCase() !== 'vllm' && apiKey.toLowerCase() !== 'none') {
        //     headers['Authorization'] = `Bearer ${apiKey}`;
        // }
        // The backend's LLM calling logic handles API keys for specific LLM providers.
        // The X-API-Key header is not standard for OpenAI and might be Eidos-specific if used.
        // For now, let's assume Eidos backend handles auth to downstream LLMs based on its config.

        const currentApiBaseUrl = window.EIDOS_API_BASE_URL;
        const response = await fetch(`${currentApiBaseUrl}/chat/completions`, {
            method: 'POST', headers: headers, body: JSON.stringify(requestBody)
        });
        const result = await response.json();
        console.log("Eidos API Full Response (api_comms):", result);

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
                    tool_calls_from_pathos: toolCalls,
                    tts_stream_attempted: responseMetadata?.tts_stream_attempted // Pass this through
                });
             }
             conversationHistory.push({ role: "assistant", content: aiResponseContent, tool_calls: toolCalls, metadata: responseMetadata });
             apiResult = { success: true, content: aiResponseContent, metadata: responseMetadata };
        } else {
             if (typeof _displayMessageInChatFunc === 'function') _displayMessageInChatFunc("AI", aiResponseContent, { usage: responseUsage });
             conversationHistory.push({ role: "assistant", content: aiResponseContent });
             apiResult = { success: false, content: aiResponseContent, metadata: { usage: responseUsage } };
        }
        saveCurrentActiveChat();
    } catch (error) {
        console.error("Error sending message to Eidos (api_comms):", error);
        const errorMessage = `**Error:** ${error.message || "Unknown API call error."}`;
        if (typeof _displayMessageInChatFunc === 'function') _displayMessageInChatFunc("AI", errorMessage, { usage: null });
        conversationHistory.push({ role: "assistant", content: errorMessage });
        saveCurrentActiveChat();
        apiResult = { success: false, content: errorMessage, metadata: { usage: null } };
    } finally {
        window.isAwaitingResponse = false;
        if (DOM.sendButton) DOM.sendButton.disabled = false;
        if (DOM.userInput) DOM.userInput.disabled = false;
        if (DOM.uploadDocumentButton) DOM.uploadDocumentButton.disabled = false;
        if (DOM.uploadImageButton) DOM.uploadImageButton.disabled = false;
        if (DOM.resetChatButton) DOM.resetChatButton.disabled = false;
        if (DOM.removeAttachedDocumentButton) DOM.removeAttachedDocumentButton.disabled = false;
        if (DOM.forceWebSearchButton) DOM.forceWebSearchButton.disabled = false;
        if (DOM.microphoneButton) DOM.microphoneButton.disabled = false;

        if (window.proactiveReplyContextDisplay) window.proactiveReplyContextDisplay.style.display = 'none';
        if (DOM.userInput) DOM.userInput.placeholder = "How can I help you today?";
        if (DOM.userInput) DOM.userInput.focus();
        if (typeof _scrollToBottomFunc === 'function' && _chatMessagesAreaFromMain) _scrollToBottomFunc(_chatMessagesAreaFromMain);
    }
    return apiResult;
}

// --- Document and Image Upload API Calls ---
export async function handleDocumentUploadAPI(file) {
    // ... (implementation as before, ensure window.EIDOS_API_BASE_URL and window.currentUserId are used)
    if (!DOM.uploadDocumentButton || !DOM.documentInput) return;
    const maxSizeInMB = 50; const maxSizeInBytes = maxSizeInMB * 1024 * 1024;
    if (file.size > maxSizeInBytes) { showNotification(`File too large: ${maxSizeInMB}MB max`, 'error'); DOM.documentInput.value = ''; return; }
    const formData = new FormData(); formData.append('file', file);
    DOM.uploadDocumentButton.disabled = true; showNotification(`Uploading "${file.name}"...`, 'info');
    try {
        const response = await fetch(`${window.EIDOS_API_BASE_URL}/documents/upload`, { method: 'POST', headers: { 'X-User-Id': window.currentUserId }, body: formData });
        const result = await response.json();
        if (response.ok && result.success && result.extracted_text) {
            window.attachedDocumentText = result.extracted_text; window.attachedDocumentName = file.name;
            if (typeof window.showAttachedDocumentIndicator === 'function') window.showAttachedDocumentIndicator(file.name);
            showNotification(`"${file.name}" processed. Attached to next message.`, 'success');
        } else { showNotification(`Upload failed: ${result.message || result.detail || "Unknown error"}`, 'error'); console.error("Doc Upload Error:", result); }
    } catch (e) { console.error("Error uploading doc:", e); showNotification(`Error uploading: ${e.message}`, 'error');
    } finally { DOM.documentInput.value = ''; DOM.uploadDocumentButton.disabled = false; }
}

export function handleImageUploadClientSide(file) {
    // ... (implementation as before)
     if (!DOM.imageInput) return;
     const reader = new FileReader();
     reader.onload = function(e) {
         DOM.imageInput.dataset.attachedImageBase64 = e.target.result.split(',')[1];
         showNotification(`Image "${file.name}" attached.`, 'info');
     };
     reader.onerror = function() { showNotification('Error reading image.', 'error'); };
     reader.readAsDataURL(file);
}

// --- Other API Calls (Settings, Memory Clear, Weather) ---
export async function saveSettingsToBackendAPI(settingsToSyncPayload) {
    // ... (implementation as before, ensure window.EIDOS_API_BASE_URL and window.currentUserId are used)
    if (!window.currentUserId) { showNotification("Cannot save settings: User ID not set.", "error"); return; }
    if (!settingsToSyncPayload?.settings?.length) { console.log("No settings to sync."); return; }
    try {
        const payloadForApi = { user_id: window.currentUserId, settings: settingsToSyncPayload.settings };
        const response = await fetch(`${window.EIDOS_API_BASE_URL}/user/settings`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-User-Id': window.currentUserId }, body: JSON.stringify(payloadForApi) });
        const data = await response.json();
        if (!response.ok || data.status !== "success" && data.status !== "partial_success") {
            showNotification(`Backend settings sync failed: ${data.message || data.detail || "Unknown error"}`, 'error');
        }
        // Success notification handled by caller
    } catch (e) { showNotification(`Error saving settings: ${e.message}`, 'error'); }
}

export async function clearUserBackendMemoryAPI() {
    // ... (implementation as before, ensure window.EIDOS_API_BASE_URL and window.currentUserId are used)
    const uid = window.currentUserId;
    if (!uid || uid === "api_guest_user" || uid === "unknown_user") { showNotification("Set User ID in Settings first.", "warning"); return false; }
    if (confirm(`Clear ALL backend memory for user "${uid}"?`)) {
        showNotification("Requesting user memory clear...", "info");
        try {
            const response = await fetch(`${window.EIDOS_API_BASE_URL}/memory/clear_user`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-User-Id': uid }, body: JSON.stringify({ user_id: uid }) });
            if (response.ok) { showNotification(`Backend memory for ${uid} cleared.`, "success"); return true; }
            else { const err = await response.json().catch(() => ({})); showNotification(`Failed: ${err.detail || response.statusText}`, 'error'); return false; }
        } catch (e) { showNotification(`Error: ${e.message}`, 'error'); return false; }
    } return false;
}

export async function clearEidosBackendMemoryAPI() {
    // ... (implementation as before, ensure window.EIDOS_API_BASE_URL and window.currentUserId are used)
    const pw = prompt("Admin Password for ALL Eidos memory clear:");
    if (pw === null) { showNotification("Cancelled.", "info"); return false; }
    if (!pw) { showNotification("Admin password needed.", "warning"); return false; }
    if (confirm("DANGER! Clear ALL Eidos backend memory for ALL users?")) {
         showNotification("Requesting Eidos memory clear...", "info");
         try {
             const response = await fetch(`${window.EIDOS_API_BASE_URL}/memory/clear`, { method: 'POST', headers: { 'X-User-Id': window.currentUserId, 'X-Admin-Password': pw } });
             if (response.ok) { showNotification("Eidos backend memory cleared.", "success"); return true; }
             else { const err = await response.json().catch(() => ({})); showNotification(`Failed: ${err.detail || response.statusText}`, 'error'); return false; }
         } catch (e) { showNotification(`Error: ${e.message}`, 'error'); return false; }
     } return false;
}

export async function fetchWeatherAPI(location) {
    // ... (implementation as before, ensure window.EIDOS_API_BASE_URL and window.currentUserId are used)
    if (!location?.trim()) return null;
    if (!window.EIDOS_API_BASE_URL) { showNotification("API URL not set.", "error"); return null; }
    try {
        const response = await fetch(`${window.EIDOS_API_BASE_URL}/weather?location=${encodeURIComponent(location.trim())}`, { headers: { 'X-User-Id': window.currentUserId } });
        const result = await response.json();
        if (response.ok && result.success && result.weather_data) return result.weather_data;
        else { showNotification(`Weather fetch failed: ${result.detail || result.error || "Unknown"}`, 'error'); return null; }
    } catch (e) { showNotification(`Weather error: ${e.message}`, 'error'); return null; }
}

// --- WebSocket Connection ---
// connectWebSocket is now more robust and handles deriving URL from window.EIDOS_API_BASE_URL
export function connectWebSocket() {
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL; // From main.js global
    if (!currentApiBaseUrl) {
        console.error("connectWebSocket: EIDOS_API_BASE_URL is not set. Cannot establish WebSocket.");
        // Optionally, retry later or notify user to set API URL in settings.
        // setTimeout(connectWebSocket, 15000); // Example retry
        return;
    }

    let wsBaseUrl = currentApiBaseUrl.replace(/^http/, 'ws');
    wsBaseUrl = wsBaseUrl.replace(/\/v1\/?$/, ''); // Remove /v1 or /v1/
    wsBaseUrl = wsBaseUrl.replace(/\/ws$/, '');    // Remove trailing /ws if accidentally present
    const wsUrl = `${wsBaseUrl.replace(/\/+$/, '')}/ws`; // Ensure single /ws

    console.log(`Attempting WebSocket connection to: ${wsUrl}`);

    if (window.eidosWebSocket && (window.eidosWebSocket.readyState === WebSocket.OPEN || window.eidosWebSocket.readyState === WebSocket.CONNECTING)) {
        console.log("WebSocket already open or connecting. Closing existing before reconnecting to potentially new URL or for re-auth.");
        window.eidosWebSocket.onclose = null; // Prevent old onclose from triggering reconnect logic
        window.eidosWebSocket.close(1000, "Client initiated reconnect due to config change or manual call");
    }

    // Ensure old instance listeners are cleared before creating a new one
    if (window.eidosWebSocket) {
        window.eidosWebSocket.onopen = null;
        window.eidosWebSocket.onmessage = null;
        window.eidosWebSocket.onerror = null;
        // onclose is handled above or will be set on the new instance
    }

    try {
        window.eidosWebSocket = new WebSocket(wsUrl);

        window.eidosWebSocket.onopen = function(event) {
            console.log("WebSocket connection opened:", event);
            if (window.currentUserId) {
                window.eidosWebSocket.send(JSON.stringify({
                    type: "auth",
                    payload: { userId: window.currentUserId } // Send normalized ID
                }));
                console.log("Sent user ID over WebSocket:", window.currentUserId);
            } else {
                console.warn("WebSocket opened but currentUserId is not set. Auth message not sent.");
            }
        };

        window.eidosWebSocket.onmessage = function(event) {
            // console.log("WebSocket message received (raw in api_comms):", event.data); // Can be noisy
            // The primary handler is now window.handleWebSocketMessage in main.js
            if (typeof window.handleWebSocketMessage === 'function') {
                try {
                    const message = JSON.parse(event.data);
                    window.handleWebSocketMessage(message);
                } catch (e) {
                    console.error("Failed to parse WebSocket message JSON in api_comms.js:", e, event.data);
                }
            } else {
                console.warn("window.handleWebSocketMessage function not found in main.js.");
            }
        };

        window.eidosWebSocket.onclose = function(event) {
            console.log("WebSocket connection closed:", event.code, event.reason, "URL:", wsUrl);
            const wasCleanClose = event.wasClean || event.code === 1000 || event.code === 1005;
            window.eidosWebSocket = null; // Nullify the instance

            if (!wasCleanClose && event.reason !== "Client initiated reconnect due to config change or manual call") {
                console.log(`WebSocket closed unexpectedly (code: ${event.code}). Attempting to reconnect in 7s...`);
                setTimeout(connectWebSocket, 7000); // Retry connection
            } else {
                console.log("WebSocket closed as expected or cleanly.");
            }
        };

        window.eidosWebSocket.onerror = function(error) {
            console.error("WebSocket error event:", error, "URL:", wsUrl);
            // onclose will usually be called after onerror, handling reconnect there.
        };
    } catch (e) {
        console.error("WebSocket construction attempt failed (exception):", e);
        window.eidosWebSocket = null;
        setTimeout(connectWebSocket, 10000); // Retry on construction failure
    }
}

console.log("api_comms.js loaded.");