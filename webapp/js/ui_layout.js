// webapp/js/ui_layout.js

import { 
    chatMessagesArea, 
    chatContainer, 
    attachedDocumentIndicator, 
    attachedDocumentNameSpan 
} from './dom_elements.js';
import { scrollToBottom, showNotification as utilShowNotification } from './utils.js'; // Renamed to avoid conflict

let _closeAllSidePanelsFunc = () => console.warn("closeAllSidePanels function not yet set in ui_layout");
export function setCloseAllSidePanelsFunction(func) {
    _closeAllSidePanelsFunc = func;
}

// This function is no longer needed if the chat is always open.
// You can remove it or leave it as a no-op.
export function initCleanInterface() {
    // console.log("initCleanInterface called, but chat is now always open.");
    // If chatContainer and chatMessagesArea exist, ensure no 'minimized' class is present
    if (chatContainer) chatContainer.classList.remove('minimized');
    if (chatMessagesArea) chatMessagesArea.classList.remove('minimized');
    // Ensure it's considered 'active' if that class affects other styles
    if (chatContainer) chatContainer.classList.add('chat-active');
}

// This function's main purpose was to remove 'minimized'.
// It can now just ensure side panels are closed and scroll to bottom.
export function expandChatInterface() {
    // console.log("expandChatInterface called, ensuring chat is open and panels are closed.");
    if (chatContainer) chatContainer.classList.remove('minimized'); // Just in case
    if (chatMessagesArea) chatMessagesArea.classList.remove('minimized'); // Just in case
    if (chatContainer) chatContainer.classList.add('chat-active'); // Ensure active styles apply

    if (typeof _closeAllSidePanelsFunc === 'function') {
        _closeAllSidePanelsFunc();
    }
    if (chatMessagesArea) {
        // Slight delay might be needed if content is still rendering
        setTimeout(() => scrollToBottom(chatMessagesArea), 100); 
    }
}

export function showAttachedDocumentIndicator(fileName) {
    if (attachedDocumentIndicator && attachedDocumentNameSpan) {
        attachedDocumentNameSpan.textContent = fileName;
        attachedDocumentIndicator.style.display = 'flex';
    }
}

export function hideAttachedDocumentIndicator() {
    if (attachedDocumentIndicator && attachedDocumentNameSpan) {
        attachedDocumentNameSpan.textContent = '';
        attachedDocumentIndicator.style.display = 'none';
    }
}

export function removeAttachedDocument() {
    window.attachedDocumentText = null;
    window.attachedDocumentName = null;
    hideAttachedDocumentIndicator();
    if (typeof utilShowNotification === 'function') utilShowNotification('Attached document removed.', 'info');
    else console.log('Attached document removed.');
}

console.log("ui_layout.js loaded (modified for always-open chat).");