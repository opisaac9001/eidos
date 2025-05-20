import {
    chatMessagesArea,
    userInput,
    proactiveMessagesArea,
    proactivePanel,
    proactiveReplyContextDisplay
} from './dom_elements.js';
import {
    scrollToBottom,
    processThinkTagsInMarkdown,
    renderThinkBlocksHTML,
    addThinkBlockListeners,
    autoAdjustTextareaHeight,
    showNotification
} from './utils.js';
import { conversationHistory } from './persistent_storage.js';
import { THINK_TAG_PLACEHOLDER_PREFIX, THINK_TAG_PLACEHOLDER_SUFFIX } from './config.js';

// REMOVE this import:
// import { autoTtsEnabled } from './main.js';

let _expandChatInterfaceFunc = () => console.warn("expandChatInterface function not yet set in ui_chat");
export function setExpandChatInterfaceFunction(func) {
    _expandChatInterfaceFunc = func;
}

let _displayMessageFuncForProactive = (sender, content, metadata) => console.warn("displayMessage function not yet set in ui_chat for proactive injection");
export function setDisplayMessageFunctionForProactive(func) {
    _displayMessageFuncForProactive = func;
}

// Keep a queue for TTS playback
let ttsPlaybackQueue = [];
let isPlayingFromQueue = false;
let currentAudio = null;

async function playNextInQueue() {
    if (isPlayingFromQueue || ttsPlaybackQueue.length === 0) {
        return;
    }
    isPlayingFromQueue = true;
    const { text, messageBubble } = ttsPlaybackQueue.shift();

    let ttsStatusIndicator = messageBubble.querySelector('.tts-status-indicator');
    if (!ttsStatusIndicator) {
        ttsStatusIndicator = document.createElement('span');
        ttsStatusIndicator.classList.add('tts-status-indicator');
        Object.assign(ttsStatusIndicator.style, {
            fontSize: '0.7em', color: '#F97B65', marginLeft: '8px', fontStyle: 'italic'
        });
        const senderDiv = messageBubble.querySelector('.message-sender');
        if (senderDiv && senderDiv.parentNode === messageBubble) {
           senderDiv.appendChild(ttsStatusIndicator);
        } else {
           messageBubble.appendChild(ttsStatusIndicator);
        }
    }
    ttsStatusIndicator.textContent = '(Playing...)';

    try {
        const ttsApiUrl = `${window.EIDOS_API_BASE_URL}/tts/synthesize`;
        const response = await fetch(ttsApiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-User-Id': window.currentUserId },
            body: JSON.stringify({ text: text })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `TTS synthesis failed: ${response.status}`);
        }

        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);
        currentAudio = new Audio(audioUrl);
        currentAudio.play();

        currentAudio.onended = () => {
            URL.revokeObjectURL(audioUrl);
            currentAudio = null;
            if (ttsStatusIndicator) ttsStatusIndicator.textContent = '';
            isPlayingFromQueue = false;
            playNextInQueue();
        };
        currentAudio.onerror = (e) => {
            console.error("Error playing TTS audio from queue:", e);
            showNotification("Error playing audio.", "error");
            URL.revokeObjectURL(audioUrl);
            currentAudio = null;
            if (ttsStatusIndicator) ttsStatusIndicator.textContent = '(Error)';
            isPlayingFromQueue = false;
            playNextInQueue();
        };
    } catch (error) {
        console.error("Error fetching TTS audio for queue:", error);
        showNotification(error.message || "TTS request failed.", "error");
        if (ttsStatusIndicator) ttsStatusIndicator.textContent = '(Failed)';
        isPlayingFromQueue = false;
        playNextInQueue();
    }
}

export function stopAndClearTTSQueue() {
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.src = "";
        const indicators = document.querySelectorAll('.tts-status-indicator'); // Clear all indicators
        indicators.forEach(ind => ind.textContent = '');
        currentAudio = null;
    }
    ttsPlaybackQueue = [];
    isPlayingFromQueue = false;
    console.log("TTS queue cleared and current playback stopped.");
}
// window.stopAndClearTTSQueue = stopAndClearTTSQueue; // Expose if needed

export function displayMessage(sender, content, metadata = null) {
    if (!chatMessagesArea) {
        console.error("displayMessage: chatMessagesArea is not available.");
        return null;
    }

    const messageBubble = document.createElement('div');
    const isAIMessage = sender.toLowerCase().startsWith('ai') || sender.toLowerCase() === 'pathos';
    messageBubble.classList.add('message-bubble', isAIMessage ? 'ai-message' : 'user-message');

    const senderDiv = document.createElement('div');
    senderDiv.classList.add('message-sender');
    senderDiv.textContent = isAIMessage ? 'Pathos' : 'You';
    messageBubble.appendChild(senderDiv);

    const contentDiv = document.createElement('div');
    contentDiv.classList.add('message-content');

    let textContentToParse = ""; // Ensure this is populated correctly
    let imageUrl = null;
    let documentContentForDisplay = null;

    if (Array.isArray(content)) {
        content.forEach(part => {
            if (part.type === 'text' && part.text) {
                if (typeof part.text === 'string' && part.text.includes("--- Uploaded Document Content ---")) {
                     const docMatch = part.text.match(/--- Uploaded Document Content ---\n([\s\S]*?)\n--- End Uploaded Document Content ---/);
                     if (docMatch && docMatch[1]) {
                          documentContentForDisplay = docMatch[1].trim();
                          textContentToParse += part.text.split("--- Uploaded Document Content ---")[0].trim() + " ";
                          const afterDoc = part.text.split("--- End Uploaded Document Content ---")[1];
                          if (afterDoc) textContentToParse += afterDoc.trim() + " ";
                     } else { textContentToParse += part.text + " "; }
                } else if (typeof part.text === 'string') { textContentToParse += part.text + " "; }
            } else if (part.type === 'image_url' && part.image_url && part.image_url.url) { imageUrl = part.image_url.url; }
        });
    } else if (typeof content === 'string') { textContentToParse = content; }
    else if (content !== null && content !== undefined) { textContentToParse = String(content); }
    textContentToParse = textContentToParse.trim();

    if (documentContentForDisplay) {
        const docDisplayDiv = document.createElement('div');
        docDisplayDiv.classList.add('document-content-display');
        docDisplayDiv.innerHTML = `<strong>Uploaded Document:</strong><br><pre>${documentContentForDisplay}</pre>`;
        contentDiv.appendChild(docDisplayDiv);
    }

    const { processedMarkdown, thinkBlocks } = processThinkTagsInMarkdown(textContentToParse);
    if (typeof marked !== 'undefined') { contentDiv.innerHTML += marked.parse(processedMarkdown || ""); }
    else { const fallbackPre = document.createElement('pre'); fallbackPre.textContent = processedMarkdown || ""; contentDiv.appendChild(fallbackPre); }

    if (imageUrl) { const imgElement = document.createElement('img'); imgElement.src = imageUrl; imgElement.alt = "User uploaded image"; contentDiv.appendChild(imgElement); }

    renderThinkBlocksHTML(contentDiv, thinkBlocks);
    addThinkBlockListeners(contentDiv);

    if (typeof Prism !== 'undefined') Prism.highlightAllUnder(contentDiv);
    if (typeof MathJax !== 'undefined' && MathJax.typesetPromise) MathJax.typesetPromise([contentDiv]).catch(err => console.warn(`MathJax error:`, err));

    messageBubble.appendChild(contentDiv);

    // ... (Feedback button logic, timestamp logic - ensure textContentToParse is used for feedback payload) ...
    if (isAIMessage && metadata && !metadata.injected_proactive_thought) {
        // ... (footerInfoDiv logic) ...
        // ... (feedback button creation logic) ...
        // Ensure the handleSubmitFeedback uses textContentToParse for last_pathos_response
    }


    const timestampDiv = document.createElement('div');
    timestampDiv.classList.add('message-timestamp');
    timestampDiv.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    messageBubble.appendChild(timestampDiv);


    // Auto-play TTS for AI messages if enabled
    // USE window.autoTtsEnabled here
    if (isAIMessage && textContentToParse.trim() && window.autoTtsEnabled) {
        console.log("Auto TTS: Queuing message for playback:", textContentToParse.substring(0,30) + "...");
        ttsPlaybackQueue.push({ text: textContentToParse, messageBubble: messageBubble });
        playNextInQueue();
    }

    if (chatMessagesArea) { chatMessagesArea.appendChild(messageBubble); scrollToBottom(chatMessagesArea); }
    return messageBubble;
}


export function displayProactiveMessageInPanel(messageContent, metadata = null) {
    // ... (existing implementation)
    // If you want proactive panel messages to also auto-play TTS when clicked and injected:
    // The current logic in displayProactiveMessageInPanel calls _displayMessageFuncForProactive,
    // which is set to displayMessageInChat (this function). So, the auto-TTS logic above
    // will apply when the proactive message is injected into the main chat.
    // No change needed here for that part.
    // ...
    if (!proactiveMessagesArea || !userInput) {
        console.error("displayProactiveMessageInPanel: proactiveMessagesArea or userInput not found.");
        return;
    }
    const placeholder = proactiveMessagesArea.querySelector('p[style*="color: #888;"]');
    if (placeholder) placeholder.remove();

    const itemDiv = document.createElement('div');
    itemDiv.classList.add('proactive-item');
    itemDiv.dataset.rawMessage = messageContent;
    if (metadata && metadata.proactive_utterance_id) {
        itemDiv.dataset.proactiveId = metadata.proactive_utterance_id;
    }

    const dateDiv = document.createElement('div');
    dateDiv.classList.add('proactive-item-date');
    dateDiv.textContent = new Date(metadata?.timestamp || Date.now()).toLocaleString();
    itemDiv.appendChild(dateDiv);

    const contentDivElement = document.createElement('div'); // Renamed to avoid conflict
    if (typeof marked !== 'undefined') contentDivElement.innerHTML = marked.parse(messageContent);
    else contentDivElement.textContent = messageContent;
    itemDiv.appendChild(contentDivElement);

    if (metadata) {
        const metaDiv = document.createElement('div');
        metaDiv.style.fontSize = '0.8em'; metaDiv.style.color = '#AAAAAA'; metaDiv.style.marginTop = '5px';
        let metaParts = [];
        if (metadata.proactive_type) metaParts.push(`Type: ${metadata.proactive_type}`);
        if (metaParts.length > 0) { metaDiv.innerHTML = metaParts.join(' | '); itemDiv.appendChild(metaDiv); }
    }

    itemDiv.addEventListener('click', () => {
        const clickedRawMessage = itemDiv.dataset.rawMessage;
        const proactiveId = itemDiv.dataset.proactiveId;
        if (userInput && clickedRawMessage) {
            const proactiveDisplayMetadata = { injected_proactive_thought: true, proactive_utterance_id: proactiveId };
            _displayMessageFuncForProactive("AI", clickedRawMessage, proactiveDisplayMetadata);

            conversationHistory.push({
                role: "assistant",
                content: clickedRawMessage,
                metadata: { proactive_utterance_id: proactiveId, injected_proactive: true }
            });

            userInput.value = "";
            userInput.placeholder = "Your response to Pathos...";
            userInput.focus();
            autoAdjustTextareaHeight(userInput);
            itemDiv.remove();
            if (proactiveMessagesArea.children.length === 0 || (proactiveMessagesArea.children.length === 1 && proactiveMessagesArea.firstChild.tagName === 'P')) {
                proactiveMessagesArea.innerHTML = '<p style="color: #888;">No proactive messages yet.</p>';
            }
            if(typeof _expandChatInterfaceFunc === 'function') _expandChatInterfaceFunc();
            if (proactiveReplyContextDisplay) proactiveReplyContextDisplay.style.display = 'none';
            if (proactivePanel) proactivePanel.classList.remove('open');
        }
    });
    proactiveMessagesArea.appendChild(itemDiv);
}
console.log("ui_chat.js loaded.");