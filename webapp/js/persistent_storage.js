// webapp/js/persistent_storage.js

import { 
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

// Cross-browser compatible UUID generator
function generateUUID() {
    // Try crypto.randomUUID() first (modern browsers)
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    
    // Fallback for older browsers/environments
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// Chat Storage API endpoints
const API_BASE = '/v1';
const CHAT_ENDPOINTS = {
    CURRENT: `${API_BASE}/chat/current`,
    ARCHIVE: `${API_BASE}/chat/archive`, 
    HISTORY: `${API_BASE}/chat/history`,
    CLEAR: `${API_BASE}/chat/all`
};

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


const MAX_MESSAGES_TO_STORE = 50; // Keep last 50 messages
const MAX_MESSAGE_LENGTH = 2000; // Max chars per message
const MAX_SYSTEM_PROMPT_LENGTH = 1000; // Max system prompt length

// Helper function to generate a title from processed messages
function getTitleFromProcessedMessages(messages, defaultTitle = "Chat") {
    if (!messages || messages.length === 0) return defaultTitle;
    
    const firstMessage = messages[0];
    // After processing, message content is always a string (original string, or JSON.stringified object/array)
    const firstMessageContentString = firstMessage.content; 

    if (typeof firstMessageContentString !== 'string' || firstMessageContentString.length === 0) {
        return defaultTitle;
    }

    let title = null;
    // Check if the content string is a JSON array (e.g., from complex content)
    if (firstMessageContentString.startsWith('[') && firstMessageContentString.endsWith(']')) {
        try {
            const parts = JSON.parse(firstMessageContentString);
            if (Array.isArray(parts)) {
                const firstTextPart = parts.find(p => p.type === 'text' && typeof p.text === 'string' && p.text.trim().length > 0);
                if (firstTextPart) {
                    title = firstTextPart.text.substring(0, 50);
                }
            }
        } catch (e) {
            // Content might be a string that looks like an array but isn't valid JSON, or another error.
            // Fallback to using the string directly.
            // console.warn("Failed to parse first message content as JSON array for title:", e);
        }
    }
    
    if (!title) { // Fallback if not a parsable array with a text part, or if it's a simple string message
        title = firstMessageContentString.substring(0, 50);
    }
    
    return title.length > 0 ? title : defaultTitle;
}

/**
 * Saves the current active chat state to the server.
 * Implements data size management and cleanup to prevent issues.
 */
export async function saveCurrentActiveChat() {
    if (!systemPromptInput || !modelDisplayName) {
        console.warn("saveCurrentActiveChat: DOM elements not ready, skipping save.");
        return;
    }

    if (conversationHistory.length === 0 && !systemPromptInput.value.trim()) {
        console.log("No active conversation content to save.");
        return;
    }

    // Only keep the most recent messages if we have too many
    const recentMessages = conversationHistory.length > MAX_MESSAGES_TO_STORE 
        ? conversationHistory.slice(-MAX_MESSAGES_TO_STORE) 
        : [...conversationHistory];

    // Truncate long messages while preserving important info
    const processedMessages = recentMessages.map(msg => {
        let contentToSave;
        if (typeof msg.content === 'string') {
            contentToSave = msg.content.length > MAX_MESSAGE_LENGTH 
                ? msg.content.slice(0, MAX_MESSAGE_LENGTH) + "..." 
                : msg.content;
        } else if (msg.content === undefined) {
            contentToSave = "null"; // Store undefined as the string "null"
        } else { 
            // For objects (including arrays and null), numbers, booleans.
            try {
                contentToSave = JSON.stringify(msg.content);
            } catch (e) {
                console.error("Failed to stringify message content during save:", msg.content, e);
                contentToSave = "[Error stringifying content]";
            }
        }
        return {
            role: msg.role,
            content: contentToSave, // contentToSave is now always a string
            metadata: msg.metadata
        };
    });    // Create the chat state object
    const currentChatState = {
        id: window.currentChatId || generateUUID(),
        timestamp: new Date().toISOString(),
        systemPrompt: systemPromptInput.value.trim().slice(0, MAX_SYSTEM_PROMPT_LENGTH),
        conversation: processedMessages,
        selectedModel: modelDisplayName.textContent,
        userId: window.userId || 'default',
        title: getTitleFromProcessedMessages(processedMessages, "New Chat")
    };

    try {
        // Save current chat to server
        const response = await fetch(CHAT_ENDPOINTS.CURRENT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': window.userId || 'default'
            },
            body: JSON.stringify(currentChatState)
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        // Update the window's current chat ID
        window.currentChatId = currentChatState.id;
        
        console.log("Successfully saved current chat to server");
    } catch (e) {
        console.error("Error saving current chat state to server:", e);
        showNotification("Could not save current chat. Please try again later.", "error");
    }
}

/**
 * Archives the current chat to server storage.
 */
export async function archiveCurrentChatToHistory() {
    if (conversationHistory.length === 0 && (!systemPromptInput || !systemPromptInput.value.trim())) {
        console.log("No conversation to archive (current chat is empty).");
        return;
    }

    const currentSystemPrompt = systemPromptInput ? systemPromptInput.value.trim() : "";
    const currentModel = modelDisplayName ? modelDisplayName.textContent : "eidos-agent";

    // Process messages for archiving
    const processedHistory = conversationHistory.map(msg => {
        let contentToSave;
        if (typeof msg.content === 'string') {
            contentToSave = msg.content.length > MAX_MESSAGE_LENGTH 
                ? msg.content.slice(0, MAX_MESSAGE_LENGTH) + "..." 
                : msg.content;
        } else if (msg.content === undefined) {
            contentToSave = "null"; // Store undefined as the string "null"
        } else { 
            // For objects (including arrays and null), numbers, booleans.
            try {
                contentToSave = JSON.stringify(msg.content);
            } catch (e) {
                console.error("Failed to stringify message content during archive:", msg.content, e);
                contentToSave = "[Error stringifying content]";
            }
        }
        return {
            role: msg.role,
            content: contentToSave, // contentToSave is now always a string
            metadata: msg.metadata
        };
    });

    const chatEntry = {
        id: window.currentChatId || generateUUID(), // Ensure this uses the currentChatId if available
        timestamp: new Date().toISOString(),
        systemPrompt: currentSystemPrompt.slice(0, MAX_SYSTEM_PROMPT_LENGTH),
        conversation: processedHistory,
        selectedModel: currentModel,
        userId: window.userId || 'default',
        title: getTitleFromProcessedMessages(processedHistory, "Archived Chat")
    };

    try {
        // Archive chat to server
        const response = await fetch(CHAT_ENDPOINTS.ARCHIVE, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': window.userId || 'default'
            },
            body: JSON.stringify(chatEntry)
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        console.log("Chat archived to server successfully");
    } catch (e) {
        console.error("Error archiving chat to server:", e);
        showNotification("Could not archive chat. Please try again later.", "error");
    }
}

/**
 * Loads all archived chat histories from server.
 * @returns {Promise<Array>}
 */
export async function loadArchivedHistories() {
    try {
        const response = await fetch(CHAT_ENDPOINTS.HISTORY, {
            headers: {
                'X-User-Id': window.userId || 'default'
            }
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        return await response.json();
    } catch (e) {
        console.error("Error loading archived histories from server:", e);
        showNotification("Could not load chat history. Please try again later.", "error");
        return [];
    }
}

/**
 * Loads a specific chat from the archived history into the active chat area.
 */
export async function loadChatFromHistory(historyEntry) {
    if (!chatMessagesArea || !systemPromptInput || !userInput || !modelDisplayName || !modelDropdownContent) {
        console.error("loadChatFromHistory: Critical DOM elements not ready.");
        return;
    }

    try {
        // Archive current chat before loading the new one
        await archiveCurrentChatToHistory();
        
        chatMessagesArea.innerHTML = '';
        conversationHistory.length = 0;
        // conversationHistory.push(...historyEntry.conversation); // Old line

        const rehydratedConversation = historyEntry.conversation.map(messageFromServer => {
            let rehydratedContent = messageFromServer.content;
            if (typeof messageFromServer.content === 'string') {
                try {
                    const trimmedContent = messageFromServer.content.trim();
                    if ((trimmedContent.startsWith('{') && trimmedContent.endsWith('}')) ||
                        (trimmedContent.startsWith('[') && trimmedContent.endsWith(']'))) {
                        rehydratedContent = JSON.parse(trimmedContent);
                    }
                } catch (parseError) {
                    // If parsing fails, rehydratedContent remains the original string.
                    // console.warn("Content looked like JSON but failed to parse, using as string:", parseError, messageFromServer.content);
                }
            }
            return { ...messageFromServer, content: rehydratedContent };
        });
        conversationHistory.push(...rehydratedConversation);

        if (imageInput) imageInput.value = '';
        if (imageInput) imageInput.dataset.attachedImageBase64 = '';
        window.attachedDocumentText = null;
        window.attachedDocumentName = null;
        _hideAttachedDocumentIndicatorFunc();

        window.isAwaitingResponse = false;
        if (window.sendButton) window.sendButton.disabled = false;
        userInput.disabled = false;

        systemPromptInput.value = historyEntry.systemPrompt || "";

        if (historyEntry.selectedModel) {
            const modelOptionInDropdown = modelDropdownContent.querySelector(`div[data-model-name="${historyEntry.selectedModel}"]`);
            if (modelOptionInDropdown) {
                _selectModelFunc(historyEntry.selectedModel, modelOptionInDropdown.dataset.providerUrl);
            } else {
                console.warn(`Model "${historyEntry.selectedModel}" from history not found in current dropdown. Using current/default.`);
            }
        }

        // Set the current chat ID
        window.currentChatId = historyEntry.id;

        conversationHistory.forEach(message => {
            _displayMessageFunc(message.role === 'user' ? 'User' : 'AI', message.content, message.metadata || {});
        });

        _expandChatInterfaceFunc();
        userInput.focus();
        autoAdjustTextareaHeight(userInput);
        scrollToBottom(chatMessagesArea);

        // Save this as the new current chat
        await saveCurrentActiveChat();

    } catch (e) {
        console.error("Error loading chat from history:", e);
        showNotification("Could not load chat from history. Please try again later.", "error");
    }
}

/**
 * Resets the current chat: archives it, clears the display and history array.
 */
export async function resetChat() {
    if (!chatMessagesArea || !userInput || !proactiveMessagesArea || !proactiveReplyContextDisplayElement) {
        console.error("resetChat: Critical DOM elements not ready.");
        return;
    }

    try {
        // Archive current chat before resetting
        await archiveCurrentChatToHistory();
        
        chatMessagesArea.innerHTML = '';
        conversationHistory.length = 0;

        if (imageInput) imageInput.value = '';
        if (imageInput) imageInput.dataset.attachedImageBase64 = '';
        window.attachedDocumentText = null;
        window.attachedDocumentName = null;
        _hideAttachedDocumentIndicatorFunc();
        
        // Clear current chat ID
        window.currentChatId = null;
        
        _initCleanInterfaceFunc();
        userInput.value = '';
        userInput.focus();
        autoAdjustTextareaHeight(userInput);
        
        proactiveMessagesArea.innerHTML = '<p style="color: #888;">No proactive messages yet.</p>';
        if (proactiveReplyContextDisplayElement) proactiveReplyContextDisplayElement.style.display = 'none';
        
        console.log("Chat reset completed.");
    } catch (e) {
        console.error("Error during chat reset:", e);
        showNotification("Could not properly reset chat. Some state may remain.", "warning");
    }
}

/**
 * Clears all archived chat histories from server storage.
 */
export async function clearAllLocalChatHistory() {
    if (confirm("Are you sure you want to clear ALL archived chat history?")) {
        try {
            const response = await fetch(CHAT_ENDPOINTS.CLEAR, {
                method: 'DELETE',
                headers: {
                    'X-User-Id': window.userId || 'default'
                }
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            if (typeof window.renderHistoryPanel === 'function') {
                window.renderHistoryPanel();
            } else {
                console.warn("renderHistoryPanel function not available on window to refresh history panel.");
            }

            console.log("All archived chat history cleared from server.");
            showNotification("Archived chat history cleared.", "info");
        } catch (e) {
            console.error("Error clearing chat history from server:", e);
            showNotification("Could not clear chat history. Please try again later.", "error");
        }
    }
}

/**
 * Loads the current active chat from server on page load.
 * @returns {Promise<boolean>} True if a chat was loaded, false otherwise.
 */
export async function loadCurrentActiveChatOnStartup() {
    if (!chatMessagesArea || !systemPromptInput || !modelDisplayName) {
        console.warn("loadCurrentActiveChatOnStartup: DOM elements not ready, skipping load.");
        return false;
    }

    try {
        const response = await fetch(CHAT_ENDPOINTS.CURRENT, {
            headers: {
                'X-User-Id': window.userId || 'default'
            }
        });

        if (!response.ok) {
            if (response.status === 404) {
                console.log("No current chat found on server for this user.");
                _initCleanInterfaceFunc(); // Initialize a clean interface if no chat is found
                return false; // No current chat found
            }
            throw new Error(`Server error: ${response.status}`);
        }

        const savedChatState = await response.json();
        if (savedChatState && savedChatState.conversation) { // Added check for savedChatState.conversation
            console.log("Loading previously active chat state from server.");
            
            conversationHistory.length = 0;

            const rehydratedStartupConversation = savedChatState.conversation.map(messageFromServer => {
                let rehydratedContent = messageFromServer.content;
                if (typeof messageFromServer.content === 'string') {
                    try {
                        const trimmedContent = messageFromServer.content.trim();
                        if ((trimmedContent.startsWith('{') && trimmedContent.endsWith('}')) ||
                            (trimmedContent.startsWith('[') && trimmedContent.endsWith(']'))) {
                            rehydratedContent = JSON.parse(trimmedContent);
                        }
                    } catch (parseError) {
                        // If parsing fails, rehydratedContent remains the original string.
                        // console.warn("Startup content looked like JSON but failed to parse, using as string:", parseError, messageFromServer.content);
                    }
                }
                return { ...messageFromServer, content: rehydratedContent };
            });
            conversationHistory.push(...rehydratedStartupConversation);
            
            if (systemPromptInput && savedChatState.systemPrompt !== undefined) {
                systemPromptInput.value = savedChatState.systemPrompt;
            }

            if (savedChatState.selectedModel) {
                const modelOptionInDropdown = modelDropdownContent.querySelector(`div[data-model-name="${savedChatState.selectedModel}"]`);
                if (modelOptionInDropdown) {
                    _selectModelFunc(savedChatState.selectedModel, modelOptionInDropdown.dataset.providerUrl);
                } else {
                    console.warn(`Model "${savedChatState.selectedModel}" from saved state not found in current dropdown. Using current/default.`);
                }
            }

            // Set the current chat ID
            window.currentChatId = savedChatState.id;

            // Clear chatMessagesArea before re-populating
            if(chatMessagesArea) chatMessagesArea.innerHTML = ''; 

            conversationHistory.forEach(message => {
                _displayMessageFunc(message.role === 'user' ? 'User' : 'AI', message.content, message.metadata || {});
            });

            _expandChatInterfaceFunc();
            if(userInput) userInput.focus(); // Added null check for userInput
            if(userInput) autoAdjustTextareaHeight(userInput); // Added null check for userInput
            if(chatMessagesArea) scrollToBottom(chatMessagesArea); // Added null check for chatMessagesArea
            return true; // Return true as a chat was loaded
        } else {
            console.log("No saved chat state found on server or conversation data missing.");
            _initCleanInterfaceFunc(); // Initialize a clean interface
            return false; // Return false as no chat was loaded
        }
    } catch (e) {
        console.error("Error loading current active chat on startup:", e);
        showNotification("Could not load current chat. Please try again later.", "error");
        _initCleanInterfaceFunc(); // Also ensure clean interface on error
    }

    return false; // Default to false if try block didn't return
}

// console.log("persistent_storage.js loaded."); // This line might be removed if generateUUID was the last thing before it