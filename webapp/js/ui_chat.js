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
import { conversationHistory, saveCurrentActiveChat } from './persistent_storage.js';

// --- Injected Dependencies ---
let _expandChatInterfaceFunc = () => console.warn("expandChatInterface function not yet set in ui_chat");
export function setExpandChatInterfaceFunction(func) {
    _expandChatInterfaceFunc = func;
}

let _displayMessageFuncForProactive = (sender, content, metadata) => console.warn("displayMessage function not yet set in ui_chat for proactive injection");
export function setDisplayMessageFunctionForProactive(func) {
    _displayMessageFuncForProactive = func;
}

// --- TTS Playback Queue and State ---
let ttsPlaybackQueue = []; // Stores objects: { audioSrc: 'url', text: 'sentence', messageBubble: bubble, sequence: number }
let isPlayingFromQueue = false;
let currentAudio = null; // Holds the current Audio object
let currentPlayingMessageBubble = null; // Tracks the bubble for the current audio's indicator

export function getLatestAIMessageBubbleForTTS() {
    if (!chatMessagesArea) return null;
    const aiMessages = chatMessagesArea.querySelectorAll('.message-bubble.ai-message');
    if (aiMessages.length === 0) return null;

    for (let i = aiMessages.length - 1; i >= 0; i--) {
        const bubble = aiMessages[i];
        if (bubble.dataset.ttsExpected === 'true' || bubble.classList.contains('currently-streaming-tts')) {
            return bubble;
        }
    }
    return aiMessages[aiMessages.length - 1]; // Fallback
}

export function addAudioUrlToTTSQueue(audioUrl, sequence, textForIndicator, messageBubbleForIndicator) {
    if (!audioUrl || typeof textForIndicator === 'undefined' || typeof sequence === 'undefined') {
        console.error("addAudioUrlToTTSQueue: Missing required parameters.", { audioUrl, sequence, textForIndicator });
        return;
    }
    const targetBubble = messageBubbleForIndicator;
    ttsPlaybackQueue.push({
        audioSrc: audioUrl,
        text: textForIndicator,
        messageBubble: targetBubble,
        sequence: sequence
    });
    ttsPlaybackQueue.sort((a, b) => a.sequence - b.sequence);
    console.log(`UI_Chat: Audio chunk (seq ${sequence}, text: "${textForIndicator.substring(0,20)}...") added to TTS queue. Queue length: ${ttsPlaybackQueue.length}`);
}

export function playNextInTTSQueueIfIdle() {
    if (!isPlayingFromQueue && ttsPlaybackQueue.length > 0) {
        console.log("playNextInTTSQueueIfIdle: Queue is idle and has items. Starting playback.");
        playNextInQueue();
    } else if (isPlayingFromQueue) {
        console.log("playNextInTTSQueueIfIdle: Queue is already playing.");
    } else {
        console.log("playNextInTTSQueueIfIdle: Queue is empty.");
        window.currentlyPlayingMainChatTTS = false; // Ensure flag is reset if queue is empty when checked
    }
}

async function playNextInQueue() {
    if (isPlayingFromQueue || ttsPlaybackQueue.length === 0) {
        if (ttsPlaybackQueue.length === 0) {
            isPlayingFromQueue = false;
            window.currentlyPlayingMainChatTTS = false;
            console.log("playNextInQueue: Queue empty, isPlayingFromQueue=false, currentlyPlayingMainChatTTS=false");
        }
        return;
    }
    isPlayingFromQueue = true;
    // Set global flag if this item is for main chat
    if (ttsPlaybackQueue[0] && ttsPlaybackQueue[0].audioSrc && ttsPlaybackQueue[0].audioSrc.includes("/chat_tts_")) {
        window.currentlyPlayingMainChatTTS = true;
    }


    const itemToPlay = ttsPlaybackQueue.shift();

    if (!itemToPlay || !itemToPlay.audioSrc || typeof itemToPlay.text === 'undefined') {
        console.error("playNextInQueue: Invalid item in TTS queue.", itemToPlay);
        isPlayingFromQueue = false;
        if (ttsPlaybackQueue.length === 0) window.currentlyPlayingMainChatTTS = false;
        playNextInTTSQueueIfIdle(); // Try next item or reset state
        return;
    }

    const { audioSrc, text, messageBubble, sequence } = itemToPlay;
    
    currentPlayingMessageBubble = (messageBubble && document.body.contains(messageBubble)) ? messageBubble : null;
    // Attempt to find a suitable bubble if the one passed is invalid, especially for main chat audio
    if (!currentPlayingMessageBubble && audioSrc.includes("/chat_tts_")) { 
        const latestAiBubble = getLatestAIMessageBubbleForTTS ? getLatestAIMessageBubbleForTTS() : null;
        if (latestAiBubble && latestAiBubble.dataset.ttsExpected === 'true') {
            console.warn(`playNextInQueue: itemToPlay.messageBubble was invalid for chat audio (Seq: ${sequence}). Attempting to use latestAiBubble.`);
            currentPlayingMessageBubble = latestAiBubble;
        } else {
            console.warn(`playNextInQueue: itemToPlay.messageBubble was invalid for chat audio (Seq: ${sequence}), and no suitable latestAiBubble found.`);
        }
    }

    let ttsStatusIndicator = null;
    if (currentPlayingMessageBubble) {
        currentPlayingMessageBubble.classList.add('currently-streaming-tts');
        ttsStatusIndicator = currentPlayingMessageBubble.querySelector('.tts-status-indicator');
        if (!ttsStatusIndicator) {
            ttsStatusIndicator = document.createElement('span');
            ttsStatusIndicator.classList.add('tts-status-indicator');
            const senderDiv = currentPlayingMessageBubble.querySelector('.message-sender');
            if (senderDiv && senderDiv.parentNode === currentPlayingMessageBubble) {
               senderDiv.appendChild(ttsStatusIndicator);
            } else {
               const contentDiv = currentPlayingMessageBubble.querySelector('.message-content');
               if (contentDiv) contentDiv.insertAdjacentElement('afterend', ttsStatusIndicator);
               else currentPlayingMessageBubble.appendChild(ttsStatusIndicator);
            }
        }
        ttsStatusIndicator.textContent = `(Playing: "${text.substring(0, 20)}...")`;
        console.log(`playNextInQueue: Playing seq ${sequence}, text: "${text.substring(0,30)}..." for bubble:`, currentPlayingMessageBubble ? currentPlayingMessageBubble.id || "anonymous bubble" : "no bubble");
    } else {
        console.warn(`playNextInQueue: No valid/current messageBubble for TTS item (Seq: ${sequence}). Indicator won't be shown.`);
    }

    try {
        console.log(`UI_Chat: Fetching audio for TTS playback from ${audioSrc}`);
        const audioResponse = await fetch(audioSrc);
        if (!audioResponse.ok) {
            throw new Error(`Failed to fetch audio chunk ${audioSrc}: ${audioResponse.status} ${audioResponse.statusText}`);
        }
        const audioBlob = await audioResponse.blob();
        const playableAudioUrl = URL.createObjectURL(audioBlob);

        currentAudio = new Audio(playableAudioUrl);
        currentAudio.play()
            .catch(playError => { 
                console.error("Error starting audio playback:", playError, "Src:", playableAudioUrl);
                showNotification("Error starting audio playback.", "error");
                URL.revokeObjectURL(playableAudioUrl); 
                if (ttsStatusIndicator) ttsStatusIndicator.textContent = '(Play Error)';
                if (currentPlayingMessageBubble) currentPlayingMessageBubble.classList.remove('currently-streaming-tts');
                currentPlayingMessageBubble = null;
                isPlayingFromQueue = false;
                if (ttsPlaybackQueue.length === 0) window.currentlyPlayingMainChatTTS = false;
                currentAudio = null; 
                playNextInTTSQueueIfIdle(); 
            });

        currentAudio.onended = () => {
            console.log(`playNextInQueue: Audio ended for seq ${sequence}, text: "${text.substring(0,30)}..."`);
            URL.revokeObjectURL(playableAudioUrl);
            currentAudio = null;
            if (ttsStatusIndicator) ttsStatusIndicator.textContent = '';
            if (currentPlayingMessageBubble) currentPlayingMessageBubble.classList.remove('currently-streaming-tts');
            currentPlayingMessageBubble = null;
            isPlayingFromQueue = false;
            playNextInTTSQueueIfIdle(); 
        };
        currentAudio.onerror = (e) => {
            console.error("Error playing TTS audio from queue (onerror event):", e, "Src:", playableAudioUrl);
            showNotification("Error playing audio chunk.", "error");
            URL.revokeObjectURL(playableAudioUrl);
            currentAudio = null;
            if (ttsStatusIndicator) ttsStatusIndicator.textContent = '(Error)';
            if (currentPlayingMessageBubble) currentPlayingMessageBubble.classList.remove('currently-streaming-tts');
            currentPlayingMessageBubble = null;
            isPlayingFromQueue = false;
            if (ttsPlaybackQueue.length === 0) window.currentlyPlayingMainChatTTS = false;
            playNextInTTSQueueIfIdle();
        };
    } catch (error) { 
        console.error("Error fetching or preparing TTS audio for queue:", error, "Original Src:", audioSrc);
        showNotification(error.message || "TTS audio chunk request failed.", "error");
        if (ttsStatusIndicator) ttsStatusIndicator.textContent = '(Failed to load)';
        if (currentPlayingMessageBubble) currentPlayingMessageBubble.classList.remove('currently-streaming-tts');
        currentPlayingMessageBubble = null;
        isPlayingFromQueue = false;
        if (ttsPlaybackQueue.length === 0) window.currentlyPlayingMainChatTTS = false;
        playNextInTTSQueueIfIdle();
    }
}

export function stopAndClearTTSQueue() {
    console.log("stopAndClearTTSQueue called.");
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.onended = null; 
        currentAudio.onerror = null;
        if (currentAudio.src && currentAudio.src.startsWith('blob:')) {
            URL.revokeObjectURL(currentAudio.src);
        }
        currentAudio.src = ""; 
        currentAudio = null;
    }
    ttsPlaybackQueue = [];
    isPlayingFromQueue = false;
    window.currentlyPlayingMainChatTTS = false; 
    if (currentPlayingMessageBubble) {
        const indicator = currentPlayingMessageBubble.querySelector('.tts-status-indicator');
        if (indicator) indicator.textContent = '';
        currentPlayingMessageBubble.classList.remove('currently-streaming-tts');
    }
    currentPlayingMessageBubble = null;
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

    let shouldStartTTSForThisBubble = false;
    if (isAIMessage && metadata && metadata.tts_stream_attempted === true) {
        messageBubble.dataset.ttsExpected = 'true';
        console.log("displayMessage: Set ttsExpected=true on AI bubble. Metadata tts_stream_attempted:", metadata.tts_stream_attempted);
        if (window.autoTtsEnabled) {
            shouldStartTTSForThisBubble = true;
        }
    }

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
            } else if (part.type === 'image_url' && part.image_url && part.image_url.url) {
                imageUrl = part.image_url.url;
            }
        });
    } else if (typeof content === 'string') {
        textContentToParse = content;
    } else if (content !== null && content !== undefined) {
        textContentToParse = String(content);
    }
    textContentToParse = textContentToParse.trim();

    if (documentContentForDisplay) {
        const docDisplayDiv = document.createElement('div');
        docDisplayDiv.classList.add('document-content-display');
        docDisplayDiv.innerHTML = `<strong>Uploaded Document:</strong><br><pre>${documentContentForDisplay.replace(/</g, "<").replace(/>/g, ">")}</pre>`;
        contentDiv.appendChild(docDisplayDiv);
    }

    const { processedMarkdown, thinkBlocks } = processThinkTagsInMarkdown(textContentToParse);
    if (typeof marked !== 'undefined') {
        contentDiv.innerHTML += marked.parse(processedMarkdown || "");
    } else {
        const fallbackPre = document.createElement('pre');
        fallbackPre.textContent = processedMarkdown || "";
        contentDiv.appendChild(fallbackPre);
    }

    if (imageUrl) {
        const imgElement = document.createElement('img');
        imgElement.src = imageUrl;
        imgElement.alt = "User uploaded image";
        imgElement.style.maxWidth = '100%';
        imgElement.style.borderRadius = '4px';
        imgElement.style.marginTop = '8px';
        imgElement.style.display = 'block';
        contentDiv.appendChild(imgElement);
    }

    renderThinkBlocksHTML(contentDiv, thinkBlocks);
    addThinkBlockListeners(contentDiv);

    if (typeof Prism !== 'undefined') Prism.highlightAllUnder(contentDiv);
    if (typeof MathJax !== 'undefined' && MathJax.typesetPromise) {
        MathJax.typesetPromise([contentDiv]).catch(err => console.warn(`MathJax typesetting error:`, err));
    }

    messageBubble.appendChild(contentDiv);

    if (isAIMessage && metadata && !metadata.injected_proactive_thought) {
        const footerInfoDiv = document.createElement('div');
        footerInfoDiv.classList.add('message-footer-info');
        let footerParts = [];
        if (metadata.usage && (metadata.usage.prompt_tokens || metadata.usage.completion_tokens || metadata.usage.estimated_prompt_tokens)) {
            const pTokens = metadata.usage.prompt_tokens || metadata.usage.estimated_prompt_tokens || 'N/A';
            const cTokens = metadata.usage.completion_tokens || 'N/A';
            footerParts.push(`Tokens: P ${pTokens} / C ${cTokens}`);
        }
        if (metadata.mood_at_response) footerParts.push(`Mood: V ${metadata.mood_at_response.valence.toFixed(2)} A ${metadata.mood_at_response.arousal.toFixed(2)}`);
        if (metadata.hexus_scores) {
            const hexusShort = Object.entries(metadata.hexus_scores).map(([k, v]) => `${k.substring(0,1).toUpperCase()}${k.substring(1,3)}:${parseFloat(v).toFixed(1)}`).join(' ');
            footerParts.push(`Hexus: ${hexusShort}`);
        }
        if (metadata.vision_llm_output) footerParts.push(`Vision: [Output present]`);
        if (metadata.tool_calls_from_pathos) {
            const toolNames = metadata.tool_calls_from_pathos.map(tc => tc.function?.name || 'unknown_tool').join(', ');
            footerParts.push(`Tools: ${toolNames}`);
        }
        if (footerParts.length > 0) {
            footerInfoDiv.innerHTML = footerParts.map(p => `<span>${p}</span>`).join('');
            messageBubble.appendChild(footerInfoDiv);
        }

        const feedbackContainer = document.createElement('div');
        feedbackContainer.classList.add('feedback-buttons-container');
        const feedbackTypes = [
            { type: 'positive', label: '👍', title: 'Good response' },
            { type: 'negative', label: '👎', title: 'Bad response' },
            { type: 'correction', label: '✍️', title: 'Suggest correction' },
        ];
        feedbackTypes.forEach(fb => {
            const button = document.createElement('button');
            button.classList.add('feedback-button'); button.textContent = fb.label; button.title = fb.title;
            button.dataset.feedbackType = fb.type;
            button.addEventListener('click', () => handleFeedbackClick(button, messageBubble, textContentToParse, metadata));
            feedbackContainer.appendChild(button);
        });
        messageBubble.appendChild(feedbackContainer);
    }

    const timestampDiv = document.createElement('div');
    timestampDiv.classList.add('message-timestamp');
    timestampDiv.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    messageBubble.appendChild(timestampDiv);

    if (chatMessagesArea) {
        chatMessagesArea.appendChild(messageBubble);
        scrollToBottom(chatMessagesArea);
    }

    if (shouldStartTTSForThisBubble && typeof playNextInTTSQueueIfIdle === 'function') {
        console.log("displayMessage: AI message bubble added, autoTtsEnabled. Triggering playNextInTTSQueueIfIdle.");
        window.currentlyPlayingMainChatTTS = true; // Set flag as we are initiating for main chat
        setTimeout(() => playNextInTTSQueueIfIdle(), 50); 
    }
    return messageBubble;
}

export function displayProactiveMessageInPanel(messageContent, metadata = null) {
    console.log("displayProactiveMessageInPanel CALLED. Raw MessageContent:", JSON.stringify(messageContent), "Raw Metadata:", JSON.stringify(metadata));

    if (!proactiveMessagesArea) {
        console.error("displayProactiveMessageInPanel: proactiveMessagesArea not found.");
        return;
    }
    const placeholder = proactiveMessagesArea.querySelector('p[style*="color: #888;"]');
    if (placeholder) placeholder.remove();

    const itemDiv = document.createElement('div');
    itemDiv.classList.add('proactive-item');

    let textualContentForMarked = "";
    let rawTextForDataset = "";
    let audioChunksData = null;

    if (Array.isArray(messageContent)) {
        if (messageContent.length > 0) {
            if (typeof messageContent[0] === 'string') {
                textualContentForMarked = messageContent[0];
                rawTextForDataset = messageContent[0];
            } else {
                console.warn("displayProactiveMessageInPanel: messageContent[0] is not a string, stringifying:", messageContent[0]);
                textualContentForMarked = String(messageContent[0] || "");
                rawTextForDataset = textualContentForMarked;
            }
        } else {
            console.warn("displayProactiveMessageInPanel: messageContent is an empty array.");
            textualContentForMarked = "[Empty proactive message content array]";
            rawTextForDataset = textualContentForMarked;
        }

        if (messageContent.length > 1) {
            if (Array.isArray(messageContent[1])) {
                audioChunksData = messageContent[1];
            } else if (messageContent[1] === null) {
                audioChunksData = null;
            } else {
                console.warn("displayProactiveMessageInPanel: messageContent[1] is not an array or null, ignoring for audio chunks:", messageContent[1]);
            }
        }
    } else if (typeof messageContent === 'string') {
        textualContentForMarked = messageContent;
        rawTextForDataset = messageContent;
    } else {
        console.error("displayProactiveMessageInPanel: messageContent is not a string or expected array. Stringifying:", messageContent);
        textualContentForMarked = String(messageContent || "");
        rawTextForDataset = textualContentForMarked;
    }
    console.log("displayProactiveMessageInPanel: Final textualContentForMarked:", textualContentForMarked);
    console.log("displayProactiveMessageInPanel: Final audioChunksData:", audioChunksData);

    itemDiv.dataset.rawMessage = rawTextForDataset;

    const effectiveMetadata = metadata || {};
    const proactiveId = effectiveMetadata.proactive_utterance_id;
    if (proactiveId) {
        itemDiv.dataset.proactiveId = proactiveId;
    }

    if (audioChunksData && Array.isArray(audioChunksData) && audioChunksData.length > 0) {
        itemDiv.dataset.audioChunks = JSON.stringify(audioChunksData);
        console.log("displayProactiveMessageInPanel: Stored audioChunks in dataset:", itemDiv.dataset.audioChunks);
    } else {
        console.log("displayProactiveMessageInPanel: No valid audioChunksData to store in dataset.");
    }

    const dateDiv = document.createElement('div');
    dateDiv.classList.add('proactive-item-date');
    const timestamp = effectiveMetadata.timestamp || Date.now();
    dateDiv.textContent = new Date(timestamp).toLocaleString();
    itemDiv.appendChild(dateDiv);

    const contentDivElement = document.createElement('div');
    if (typeof marked !== 'undefined') {
        try {
            if (typeof textualContentForMarked !== 'string') {
                console.error("CRITICAL: textualContentForMarked is NOT a string before marked.parse! Value:", textualContentForMarked);
                textualContentForMarked = String(textualContentForMarked);
            }
            contentDivElement.innerHTML = marked.parse(textualContentForMarked);
        } catch (e) {
            console.error("Error during marked.parse for proactive message:", e, "Input was:", textualContentForMarked);
            contentDivElement.textContent = textualContentForMarked + " (Error rendering Markdown)";
        }
    } else {
        contentDivElement.textContent = textualContentForMarked;
    }
    itemDiv.appendChild(contentDivElement);

    if (Object.keys(effectiveMetadata).length > 0) {
        const metaDiv = document.createElement('div');
        metaDiv.style.fontSize = '0.8em'; metaDiv.style.color = '#AAAAAA'; metaDiv.style.marginTop = '5px';
        let metaParts = [];
        if (effectiveMetadata.proactive_type) metaParts.push(`Type: ${effectiveMetadata.proactive_type}`);
        if (effectiveMetadata.source_dream_id) metaParts.push(`Dream ID: ${effectiveMetadata.source_dream_id.substring(0,8)}`);
        if (metaParts.length > 0) { metaDiv.innerHTML = metaParts.join(' | '); itemDiv.appendChild(metaDiv); }
    }

    itemDiv.addEventListener('click', () => {
        const clickedRawMessage = itemDiv.dataset.rawMessage;
        const currentProactiveId = itemDiv.dataset.proactiveId;

        if (userInput && clickedRawMessage) {
            const displayMetaForChat = {
                injected_proactive_thought: true,
                proactive_utterance_id: currentProactiveId,
                tts_stream_attempted: !!itemDiv.dataset.audioChunks 
            };
            const mainChatMessageBubble = _displayMessageFuncForProactive("AI", clickedRawMessage, displayMetaForChat);

            conversationHistory.push({
                role: "assistant",
                content: clickedRawMessage,
                metadata: {
                    proactive_utterance_id: currentProactiveId,
                    injected_proactive: true,
                    proactive_type: effectiveMetadata.proactive_type || "unknown"
                }
            });
            saveCurrentActiveChat();

            const audioChunksDataStringFromDataset = itemDiv.dataset.audioChunks;
            if (audioChunksDataStringFromDataset) {
                try {
                    const audioChunksToPlay = JSON.parse(audioChunksDataStringFromDataset);
                    if (Array.isArray(audioChunksToPlay) && audioChunksToPlay.length > 0) {
                        console.log("Proactive Click: Queuing audio for playback:", audioChunksToPlay);
                        stopAndClearTTSQueue(); 
                        audioChunksToPlay.sort((a, b) => a.sequence - b.sequence);
                        audioChunksToPlay.forEach(chunk => {
                            if (typeof addAudioUrlToTTSQueue === 'function' && chunk.url && typeof chunk.sequence !== 'undefined' && typeof chunk.text_for_indicator !== 'undefined') {
                                addAudioUrlToTTSQueue(
                                    chunk.url, chunk.sequence, chunk.text_for_indicator,
                                    mainChatMessageBubble
                                );
                            }
                        });
                        if (window.autoTtsEnabled && typeof playNextInTTSQueueIfIdle === 'function') {
                            console.log("Proactive Click: Triggering playback from queue because autoTtsEnabled is true.");
                            window.currentlyPlayingMainChatTTS = true; // Proactive audio is now main focus
                            playNextInTTSQueueIfIdle();
                        }
                    }
                } catch (e) { console.error("Error parsing or queuing audio_chunks for proactive message click:", e); }
            } else { console.log("Proactive Click: No audio_chunks data found in dataset for this item."); }
            
            userInput.value = "";
            userInput.placeholder = "Your response to Pathos...";
            userInput.focus();
            if (typeof autoAdjustTextareaHeight === 'function') autoAdjustTextareaHeight(userInput);

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

// --- Feedback Handling Logic ---
let activeFeedbackTextarea = null;
function handleFeedbackClick(button, messageBubble, lastPathosResponse, messageMetadata) {
    const feedbackType = button.dataset.feedbackType;
    if (activeFeedbackTextarea && activeFeedbackTextarea.parentNode) {
        activeFeedbackTextarea.parentNode.remove();
        activeFeedbackTextarea = null;
    }
    if (feedbackType === 'positive' || feedbackType === 'negative') {
        submitFeedback(feedbackType, null, null, lastPathosResponse, messageMetadata);
        button.classList.add('feedback-submitted');
        setTimeout(() => button.classList.remove('feedback-submitted'), 1500);
    } else if (feedbackType === 'correction') {
        const textareaContainer = document.createElement('div');
        textareaContainer.classList.add('feedback-text-container');
        const textarea = document.createElement('textarea');
        textarea.placeholder = "Your corrected version or feedback..."; textarea.rows = 2;
        activeFeedbackTextarea = textarea;
        const submitButton = document.createElement('button');
        submitButton.textContent = 'Send Correction';
        submitButton.addEventListener('click', () => {
            const feedbackText = textarea.value.trim();
            if (feedbackText) {
                submitFeedback(feedbackType, feedbackText, feedbackText, lastPathosResponse, messageMetadata);
                textareaContainer.remove(); activeFeedbackTextarea = null;
                button.classList.add('feedback-submitted');
                setTimeout(() => button.classList.remove('feedback-submitted'), 1500);
            } else { showNotification("Please enter your correction.", "warning"); }
        });
        textareaContainer.appendChild(textarea); textareaContainer.appendChild(submitButton);
        messageBubble.appendChild(textareaContainer); textarea.focus();
    }
}

async function submitFeedback(feedbackType, feedbackText, suggestedResponse, lastPathosResponse, messageMetadata) {
    const lastUserMessage = conversationHistory.slice().reverse().find(msg => msg.role === 'user');
    let lastUserInput = "[Could not retrieve last user input]";
    if (lastUserMessage) {
        if (typeof lastUserMessage.content === 'string') {
            lastUserInput = lastUserMessage.content;
        } else if (Array.isArray(lastUserMessage.content)) {
            const textPart = lastUserMessage.content.find(p => p.type === 'text');
            lastUserInput = textPart ? textPart.text : JSON.stringify(lastUserMessage.content);
        } else {
            lastUserInput = JSON.stringify(lastUserMessage.content);
        }
    }

    const payload = {
        interaction_id: messageMetadata?.interaction_id || null,
        user_id: window.currentUserId || "unknown_gui_user",
        last_user_input: lastUserInput,
        last_pathos_response: lastPathosResponse,
        feedback_type: feedbackType,
        rating: feedbackType === 'positive' ? 1 : (feedbackType === 'negative' ? -1 : null),
        feedback_text: feedbackText,
        suggested_response: suggestedResponse,
    };
    console.log("Submitting feedback:", payload);
    try {
        const response = await fetch(`${window.EIDOS_API_BASE_URL}/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-User-Id': window.currentUserId },
            body: JSON.stringify(payload)
        });
        if (response.ok) { showNotification('Feedback submitted. Thank you!', 'success');
        } else { const errorData = await response.json(); showNotification(`Feedback failed: ${errorData.detail || response.statusText}`, 'error'); }
    } catch (error) { console.error('Error submitting feedback:', error); showNotification('Error submitting feedback.', 'error'); }
}

console.log("ui_chat.js loaded (with proactive panel and TTS queue logic).");