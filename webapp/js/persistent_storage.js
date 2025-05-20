// webapp/js/persistent_storage.js

import { 
    CHAT_HISTORY_KEY, 
    CURRENT_CHAT_KEY, 
    SYSTEM_PROMPT_KEY, // Used by resetChat if we decide to reset system prompt
    SELECTED_MODEL_KEY // To save/load the selected model with the chat
} from './config.js';
import { 
    showNotification, 
    autoAdjustTextareaHeight, 
    scrollToBottom 
} from './utils.js'; 
import { 
    chatMessagesArea, 
    systemPromptInput, 
    userInput,
    imageInput,
    proactiveMessagesArea,
    modelDisplayName,
    modelDropdownContent, // Corrected import
    historyPanel,
    // Import proactiveReplyContextDisplay if resetChat needs it directly
    proactiveReplyContextDisplay as proactiveReplyContextDisplayElement 
} from './dom_elements.js';

// This module "owns" and exports the conversationHistory array.
export let conversationHistory = [];

// Helper functions to store references to functions injected by main.js
let _displayMessageFunc = (sender, content, metadata) => console.warn("displayMessage function not yet set in persistent_storage.js");
let _initCleanInterfaceFunc = () => console.warn("initCleanInterface function not yet set in persistent_storage.js");
let _expandChatInterfaceFunc = () => console.warn("expandChatInterface function not yet set in persistent_storage.js");
let _hideAttachedDocumentIndicatorFunc = () => console.warn("hideAttachedDocumentIndicator function not yet set in persistent_storage.js");
let _selectModelFunc = (modelName, providerUrl) => console.warn("selectModel function not yet set in persistent_storage.js");

export function setDisplayMessageFunction(func) {
    _displayMessageFunc = func;
}
export function setLayoutFunctions(initFunc, expandFunc, hideDocFunc) {
    _initCleanInterfaceFunc = initFunc;
    _expandChatInterfaceFunc = expandFunc;
    _hideAttachedDocumentIndicatorFunc = hideDocFunc;
}
export function setSelectModelFunction(func) {
    _selectModelFunc = func;
}


/**
 * Saves the current active chat state (history, system prompt, model) to localStorage.
 */
export function saveCurrentActiveChat() {
    if (!systemPromptInput || !modelDisplayName) {
        console.warn("saveCurrentActiveChat: DOM elements (systemPromptInput or modelDisplayName) not ready, skipping save.");
        return;
    }

    if (conversationHistory.length === 0 && !systemPromptInput.value.trim()) {
        localStorage.removeItem(CURRENT_CHAT_KEY);
        console.log("No active conversation content to save to current chat slot.");
        return;
    }

    const currentChatState = {
        timestamp: new Date().toISOString(),
        systemPrompt: systemPromptInput.value.trim(),
        conversation: [...conversationHistory], // Save a copy
        selectedModel: modelDisplayName.textContent, 
    };
    try {
        localStorage.setItem(CURRENT_CHAT_KEY, JSON.stringify(currentChatState));
        console.log("Current active chat state saved to localStorage.");
    } catch (e) {
        console.error("Error saving current active chat state to localStorage:", e);
        showNotification("Could not save current chat. Storage might be full.", "error");
    }
}

/**
 * Archives the current chat to the list of saved histories in localStorage.
 */
export function archiveCurrentChatToHistory() {
    if (conversationHistory.length === 0 && (!systemPromptInput || !systemPromptInput.value.trim())) {
        console.log("No conversation to archive (current chat is empty).");
        return;
    }

    const currentSystemPrompt = systemPromptInput ? systemPromptInput.value.trim() : "";
    const currentModel = modelDisplayName ? modelDisplayName.textContent : "eidos-agent";

    const getPreview = (content) => {
        let text = "Chat Entry";
        if (typeof content === 'string') text = content;
        else if (Array.isArray(content) && content[0]?.type === 'text' && typeof content[0].text === 'string') text = content[0].text;
        else if (Array.isArray(content)) text = "Multimodal Input...";
        return text.substring(0, 50) + (text.length > 50 ? '...' : '');
    };
    
    const firstUserMsg = conversationHistory.find(msg => msg.role === 'user');
    const title = getPreview(firstUserMsg?.content);

    const chatEntry = {
        timestamp: new Date().toISOString(),
        systemPrompt: currentSystemPrompt,
        conversation: [...conversationHistory], 
        selectedModel: currentModel,
        title: title || "Archived Chat"
    };

    let savedHistories = JSON.parse(localStorage.getItem(CHAT_HISTORY_KEY)) || [];
    savedHistories.unshift(chatEntry); 
    
    const maxHistoryItems = parseInt(localStorage.getItem('eidosMaxHistoryItems') || '50', 10); 
    if (savedHistories.length > maxHistoryItems) {
        savedHistories = savedHistories.slice(0, maxHistoryItems);
    }
    
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(savedHistories));
    console.log("Chat archived to history.");
}

/**
 * Loads all archived chat histories from localStorage.
 * @returns {Array<Object>}
 */
export function loadArchivedHistories() {
    return JSON.parse(localStorage.getItem(CHAT_HISTORY_KEY)) || [];
}

/**
 * Loads a specific chat from the archived history into the active chat area.
 * @param {Object} historyEntry - The chat entry object to load.
 */
export function loadChatFromHistory(historyEntry) {
    if (!chatMessagesArea || !systemPromptInput || !userInput || !modelDisplayName || !modelDropdownContent) {
        console.error("loadChatFromHistory: Critical DOM elements not ready.");
        return;
    }
    console.log("Loading chat from history archive:", historyEntry);
    
    archiveCurrentChatToHistory(); 

    chatMessagesArea.innerHTML = ''; 
    conversationHistory.length = 0; 
    conversationHistory.push(...historyEntry.conversation);

    if (imageInput) imageInput.value = ''; 
    if (imageInput) imageInput.dataset.attachedImageBase64 = '';
    window.attachedDocumentText = null; 
    window.attachedDocumentName = null;
    _hideAttachedDocumentIndicatorFunc();

    window.isAwaitingResponse = false; 
    userInput.disabled = false;
    if (window.sendButton) window.sendButton.disabled = false; // Assuming sendButton is global via main.js

    systemPromptInput.value = historyEntry.systemPrompt || "";
    
    if (historyEntry.selectedModel) {
        const modelOptionInDropdown = modelDropdownContent.querySelector(`div[data-model-name="${historyEntry.selectedModel}"]`);
        if (modelOptionInDropdown) {
            _selectModelFunc(historyEntry.selectedModel, modelOptionInDropdown.dataset.providerUrl);
        } else {
            console.warn(`Model "${historyEntry.selectedModel}" from history not found in current dropdown. Using current/default.`);
        }
    }

    conversationHistory.forEach(message => { 
        _displayMessageFunc(message.role === 'user' ? 'User' : 'AI', message.content, message.metadata || {}); 
    });
    
    _expandChatInterfaceFunc(); 
    userInput.focus(); 
    autoAdjustTextareaHeight(userInput); 
    scrollToBottom(chatMessagesArea);
    saveCurrentActiveChat(); 
}

/**
 * Resets the current chat: archives it, clears the display and history array, and clears current active chat from storage.
 */
export function resetChat() {
    if (!chatMessagesArea || !userInput || !proactiveMessagesArea || !proactiveReplyContextDisplayElement) {
        console.error("resetChat: Critical DOM elements not ready.");
        return;
    }
    archiveCurrentChatToHistory(); 
    
    chatMessagesArea.innerHTML = ''; 
    conversationHistory.length = 0; 

    if (imageInput) imageInput.value = '';
    if (imageInput) imageInput.dataset.attachedImageBase64 = '';
    window.attachedDocumentText = null; 
    window.attachedDocumentName = null;
    _hideAttachedDocumentIndicatorFunc();
    
    localStorage.removeItem(CURRENT_CHAT_KEY); 
    
    _initCleanInterfaceFunc(); 
    userInput.value = '';
    userInput.focus(); 
    autoAdjustTextareaHeight(userInput); 
    
    proactiveMessagesArea.innerHTML = '<p style="color: #888;">No proactive messages yet.</p>';
    if (proactiveReplyContextDisplayElement) proactiveReplyContextDisplayElement.style.display = 'none';
    
    console.log("Chat reset. Current active chat cleared from storage.");
}

/**
 * Clears all archived chat histories from localStorage.
 */
export function clearAllLocalChatHistory() {
    if (confirm("Are you sure you want to clear ALL LOCAL archived chat history?")) {
        localStorage.removeItem(CHAT_HISTORY_KEY);
        if (typeof window.renderHistoryPanel === 'function') { 
            window.renderHistoryPanel(); 
        } else {
            console.warn("renderHistoryPanel function not available on window to refresh history panel.");
        }
        console.log("All local archived chat history cleared.");
        showNotification("Archived chat history cleared.", "info");
    }
}

/**
 * Loads the current active chat from localStorage on page load.
 * To be called from main.js during DOMContentLoaded.
 * @returns {boolean} True if a chat was loaded, false otherwise.
 */
export function loadCurrentActiveChatOnStartup() {
    if (!chatMessagesArea || !systemPromptInput || !modelDisplayName) {
        console.warn("loadCurrentActiveChatOnStartup: DOM elements not ready, skipping load.");
        return false; 
    }

    const savedCurrentChatJSON = localStorage.getItem(CURRENT_CHAT_KEY);
    if (savedCurrentChatJSON) {
        try {
            const savedChatState = JSON.parse(savedCurrentChatJSON);
            if (savedChatState && savedChatState.conversation) {
                console.log("Loading previously active chat state from localStorage.");
                
                conversationHistory.length = 0; 
                conversationHistory.push(...savedChatState.conversation);

                if (systemPromptInput && savedChatState.systemPrompt !== undefined) {
                    systemPromptInput.value = savedChatState.systemPrompt;
                }

                if (savedChatState.selectedModel) {
                    localStorage.setItem(SELECTED_MODEL_KEY, savedChatState.selectedModel);
                }

                chatMessagesArea.innerHTML = '';
                conversationHistory.forEach(message => {
                    _displayMessageFunc(message.role === 'user' ? 'User' : 'AI', message.content, message.metadata || {});
                });
                _expandChatInterfaceFunc();
                scrollToBottom(chatMessagesArea);
                return true; 
            }
        } catch (e) {
            console.error("Error loading saved current chat state from localStorage:", e);
            localStorage.removeItem(CURRENT_CHAT_KEY); 
        }
    }
    return false; 
}

console.log("persistent_storage.js loaded.");