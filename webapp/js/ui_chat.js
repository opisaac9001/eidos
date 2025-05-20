// webapp/js/ui_chat.js

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

let _expandChatInterfaceFunc = () => console.warn("expandChatInterface function not yet set in ui_chat");
export function setExpandChatInterfaceFunction(func) {
    _expandChatInterfaceFunc = func;
}

let _displayMessageFuncForProactive = (sender, content, metadata) => console.warn("displayMessage function not yet set in ui_chat for proactive injection");
export function setDisplayMessageFunctionForProactive(func) {
    _displayMessageFuncForProactive = func;
}

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
           // Fallback: append to messageBubble if senderDiv not found or not child
           const contentDiv = messageBubble.querySelector('.message-content');
           if (contentDiv) contentDiv.insertAdjacentElement('afterend', ttsStatusIndicator);
           else messageBubble.appendChild(ttsStatusIndicator);
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
        currentAudio.src = ""; // Release the audio object
        currentAudio = null;
    }
    ttsPlaybackQueue = [];
    isPlayingFromQueue = false;
    // Clear any visible TTS status indicators
    const indicators = document.querySelectorAll('.tts-status-indicator');
    indicators.forEach(ind => ind.textContent = '');
    console.log("TTS queue cleared and current playback stopped.");
}

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

    let textContentToParse = "";
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
        docDisplayDiv.innerHTML = `<strong>Uploaded Document:</strong><br><pre>${documentContentForDisplay}</pre>`; // Simple pre for now
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

    // --- RESTORED/VERIFIED FEEDBACK BUTTON LOGIC ---
    if (isAIMessage && metadata && !metadata.injected_proactive_thought) {
        const footerInfoDiv = document.createElement('div');
        footerInfoDiv.classList.add('message-footer-info');

        let footerParts = [];
        if (metadata.usage && (metadata.usage.prompt_tokens || metadata.usage.completion_tokens)) {
            const pTokens = metadata.usage.prompt_tokens || metadata.usage.estimated_prompt_tokens || 'N/A';
            const cTokens = metadata.usage.completion_tokens || 'N/A';
            footerParts.push(`Tokens: P ${pTokens} / C ${cTokens}`);
        }
        if (metadata.mood_at_response) {
            footerParts.push(`Mood: V ${metadata.mood_at_response.valence.toFixed(2)} A ${metadata.mood_at_response.arousal.toFixed(2)}`);
        }
        if (metadata.hexus_scores) {
            const hexusShort = Object.entries(metadata.hexus_scores)
                                   .map(([k, v]) => `${k.substring(0,1).toUpperCase()}${k.substring(1,3)}:${parseFloat(v).toFixed(1)}`)
                                   .join(' ');
            footerParts.push(`Hexus: ${hexusShort}`);
        }
        if (metadata.vision_llm_output) {
            footerParts.push(`Vision: [Output present]`);
        }
        if (metadata.tool_calls_from_pathos) {
            const toolNames = metadata.tool_calls_from_pathos.map(tc => tc.function?.name || 'unknown_tool').join(', ');
            footerParts.push(`Tools: ${toolNames}`);
        }

        if (footerParts.length > 0) {
            footerInfoDiv.innerHTML = footerParts.map(p => `<span>${p}</span>`).join('');
            messageBubble.appendChild(footerInfoDiv);
        }

        const feedbackContainer = document.createElement('div');
        feedbackContainer.classList.add('feedback-buttons-container'); // Add a class for styling if needed

        const feedbackTypes = [
            { type: 'positive', label: '👍', title: 'Good response' },
            { type: 'negative', label: '👎', title: 'Bad response' },
            { type: 'correction', label: '✍️', title: 'Suggest correction' },
            // { type: 'suggestion', label: '💡', title: 'Offer suggestion' } // Optional
        ];

        feedbackTypes.forEach(fb => {
            const button = document.createElement('button');
            button.classList.add('feedback-button');
            button.textContent = fb.label;
            button.title = fb.title;
            button.dataset.feedbackType = fb.type;
            button.addEventListener('click', () => handleFeedbackClick(button, messageBubble, textContentToParse, metadata));
            feedbackContainer.appendChild(button);
        });
        messageBubble.appendChild(feedbackContainer); // Append the container of buttons
    }
    // --- END RESTORED/VERIFIED FEEDBACK BUTTON LOGIC ---

    const timestampDiv = document.createElement('div');
    timestampDiv.classList.add('message-timestamp');
    timestampDiv.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    messageBubble.appendChild(timestampDiv);

    if (isAIMessage && textContentToParse.trim() && window.autoTtsEnabled) {
        console.log("Auto TTS: Queuing message for playback:", textContentToParse.substring(0,30) + "...");
        ttsPlaybackQueue.push({ text: textContentToParse, messageBubble: messageBubble });
        playNextInQueue();
    }

    if (chatMessagesArea) { chatMessagesArea.appendChild(messageBubble); scrollToBottom(chatMessagesArea); }
    return messageBubble;
}


// --- NEW OR UPDATED: Feedback Handling Logic ---
let activeFeedbackTextarea = null; // Keep track of any open textarea

function handleFeedbackClick(button, messageBubble, lastPathosResponse, messageMetadata) {
    const feedbackType = button.dataset.feedbackType;

    // Remove any existing feedback textarea
    if (activeFeedbackTextarea && activeFeedbackTextarea.parentNode) {
        activeFeedbackTextarea.parentNode.remove(); // Remove the container of the textarea
        activeFeedbackTextarea = null;
    }

    if (feedbackType === 'positive' || feedbackType === 'negative') {
        submitFeedback(feedbackType, null, null, lastPathosResponse, messageMetadata);
        // Optionally, provide visual feedback on the button or bubble
        button.classList.add('feedback-submitted');
        setTimeout(() => button.classList.remove('feedback-submitted'), 1500);
    } else if (feedbackType === 'correction') {
        const textareaContainer = document.createElement('div');
        textareaContainer.classList.add('feedback-text-container');

        const textarea = document.createElement('textarea');
        textarea.placeholder = "Your corrected version or feedback...";
        textarea.rows = 2;
        activeFeedbackTextarea = textarea; // Track the new textarea

        const submitButton = document.createElement('button');
        submitButton.textContent = 'Send Correction';
        submitButton.addEventListener('click', () => {
            const feedbackText = textarea.value.trim();
            if (feedbackText) {
                submitFeedback(feedbackType, feedbackText, feedbackText, lastPathosResponse, messageMetadata);
                textareaContainer.remove();
                activeFeedbackTextarea = null;
                button.classList.add('feedback-submitted');
                setTimeout(() => button.classList.remove('feedback-submitted'), 1500);
            } else {
                showNotification("Please enter your correction.", "warning");
            }
        });

        textareaContainer.appendChild(textarea);
        textareaContainer.appendChild(submitButton);
        messageBubble.appendChild(textareaContainer);
        textarea.focus();
    }
}

async function submitFeedback(feedbackType, feedbackText, suggestedResponse, lastPathosResponse, messageMetadata) {
    const lastUserMessage = conversationHistory.slice().reverse().find(msg => msg.role === 'user');
    const lastUserInput = lastUserMessage ? (typeof lastUserMessage.content === 'string' ? lastUserMessage.content : JSON.stringify(lastUserMessage.content)) : "[Could not retrieve last user input]";

    const payload = {
        interaction_id: messageMetadata?.interaction_id || null, // If you store interaction IDs
        user_id: window.currentUserId || "unknown_gui_user",
        last_user_input: lastUserInput,
        last_pathos_response: lastPathosResponse,
        feedback_type: feedbackType,
        rating: feedbackType === 'positive' ? 1 : (feedbackType === 'negative' ? -1 : null),
        feedback_text: feedbackText,
        suggested_response: suggestedResponse, // For corrections, this is the user's version
        // Add any other relevant metadata from messageMetadata if needed
        // e.g., mood_at_response: messageMetadata?.mood_at_response
    };

    console.log("Submitting feedback:", payload);
    try {
        const response = await fetch(`${window.EIDOS_API_BASE_URL}/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-User-Id': window.currentUserId },
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            showNotification('Feedback submitted. Thank you!', 'success');
        } else {
            const errorData = await response.json();
            showNotification(`Feedback submission failed: ${errorData.detail || response.statusText}`, 'error');
        }
    } catch (error) {
        console.error('Error submitting feedback:', error);
        showNotification('Error submitting feedback. Check console.', 'error');
    }
}
// --- END NEW OR UPDATED FEEDBACK HANDLING ---


export function displayProactiveMessageInPanel(messageContent, metadata = null) {
    if (!proactiveMessagesArea || !userInput) {
        console.error("displayProactiveMessageInPanel: proactiveMessagesArea or userInput not found.");
        return;
    }
    const placeholder = proactiveMessagesArea.querySelector('p[style*="color: #888;"]');
    if (placeholder) placeholder.remove();

    const itemDiv = document.createElement('div');
    itemDiv.classList.add('proactive-item');
    itemDiv.dataset.rawMessage = messageContent;
    if (metadata && metadata.proactive_utterance_id) { // Ensure this ID is passed from backend
        itemDiv.dataset.proactiveId = metadata.proactive_utterance_id;
    } else if (metadata && metadata.payload && metadata.payload.metadata && metadata.payload.metadata.proactive_utterance_id) {
        // Handle if metadata is nested under payload (as seen in some WS messages)
        itemDiv.dataset.proactiveId = metadata.payload.metadata.proactive_utterance_id;
    }


    const dateDiv = document.createElement('div');
    dateDiv.classList.add('proactive-item-date');
    // Adjust timestamp source based on typical metadata structure
    const timestamp = metadata?.timestamp || metadata?.payload?.metadata?.timestamp || Date.now();
    dateDiv.textContent = new Date(timestamp).toLocaleString();
    itemDiv.appendChild(dateDiv);

    const contentDivElement = document.createElement('div');
    if (typeof marked !== 'undefined') contentDivElement.innerHTML = marked.parse(messageContent);
    else contentDivElement.textContent = messageContent;
    itemDiv.appendChild(contentDivElement);

    // Adjust metadata display based on typical structure
    const effectiveMetadata = metadata?.payload?.metadata || metadata || {};
    if (Object.keys(effectiveMetadata).length > 0) {
        const metaDiv = document.createElement('div');
        metaDiv.style.fontSize = '0.8em'; metaDiv.style.color = '#AAAAAA'; metaDiv.style.marginTop = '5px';
        let metaParts = [];
        if (effectiveMetadata.proactive_type) metaParts.push(`Type: ${effectiveMetadata.proactive_type}`);
        // Add other metadata parts if needed, e.g., source_dream_id
        if (effectiveMetadata.source_dream_id) metaParts.push(`Dream ID: ${effectiveMetadata.source_dream_id.substring(0,8)}`);

        if (metaParts.length > 0) { metaDiv.innerHTML = metaParts.join(' | '); itemDiv.appendChild(metaDiv); }
    }

    itemDiv.addEventListener('click', () => {
        const clickedRawMessage = itemDiv.dataset.rawMessage;
        const proactiveId = itemDiv.dataset.proactiveId; // This is the proactive_utterance_id
        if (userInput && clickedRawMessage) {
            // This metadata is for the *display* of the AI's proactive message in chat
            const displayMetadataForChat = { 
                injected_proactive_thought: true, 
                proactive_utterance_id: proactiveId // Pass the ID
            };
            _displayMessageFuncForProactive("AI", clickedRawMessage, displayMetadataForChat);

            // This is the metadata for the *next user message* that Pathos will receive
            // It indicates that the user is responding to this specific proactive message.
            // This should be handled in api_comms.js when constructing the request to Pathos.
            // For now, we can set a global flag or store it to be picked up.
            // A better way is to pass it through the sendMessage call.
            // Let's assume main.js or api_comms.js will handle adding `engaged_proactive_id`
            // to the *next* API call's metadata.
            
            // Update conversationHistory to reflect the AI's proactive message being part of the chat
            conversationHistory.push({
                role: "assistant",
                content: clickedRawMessage,
                metadata: { 
                    proactive_utterance_id: proactiveId, 
                    injected_proactive: true, // Mark it as injected
                    proactive_type: effectiveMetadata.proactive_type || "unknown"
                }
            });

            userInput.value = ""; // Clear user input
            userInput.placeholder = "Your response to Pathos..."; // Change placeholder
            userInput.focus();
            autoAdjustTextareaHeight(userInput);
            itemDiv.remove(); // Remove from proactive panel
            if (proactiveMessagesArea.children.length === 0 || (proactiveMessagesArea.children.length === 1 && proactiveMessagesArea.firstChild.tagName === 'P')) {
                proactiveMessagesArea.innerHTML = '<p style="color: #888;">No proactive messages yet.</p>';
            }
            if(typeof _expandChatInterfaceFunc === 'function') _expandChatInterfaceFunc();
            if (proactiveReplyContextDisplay) proactiveReplyContextDisplay.style.display = 'none'; // Hide context display
            if (proactivePanel) proactivePanel.classList.remove('open'); // Close panel
        }
    });
    proactiveMessagesArea.appendChild(itemDiv);
}
console.log("ui_chat.js loaded.");