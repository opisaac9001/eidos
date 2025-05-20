// webapp/js/ui_panels.js

import {
    EIDOS_API_BASE_URL, // From config.js
    DEFAULT_LOG_FETCH_LIMIT 
} from './config.js';
import { 
    currentUserId // Assuming this will be set globally by main.js after loading from config/localStorage
} from './main.js'; // Or directly from where currentUserId is managed e.g. config.js if exported
import { 
    historyContentArea, 
    learningLogContentArea, 
    dreamJournalContentArea, 
    knowledgeLogContentArea,
    dailyBriefingContentArea,
    historyPanel // For loadChatFromHistory to close panel
} from './dom_elements.js';
import { showNotification } from './utils.js';
import { loadChatFromHistory, archiveCurrentChatToHistory, saveCurrentActiveChat } from './persistent_storage.js'; // For history panel interaction

// Assume `marked` and `Prism` are global from CDN
// Assume `MathJax` is global from CDN

// --- History Panel Functions ---
/**
 * Renders the chat history panel from localStorage.
 */
export function renderHistoryPanel() {
    if (!historyContentArea) {
        console.error("History content area element not found.");
        return;
    }
    const histories = JSON.parse(localStorage.getItem('eidosChatHistoryArchive')) || []; // Use CHAT_HISTORY_KEY from config.js
    historyContentArea.innerHTML = '';

    if (histories.length === 0) {
        historyContentArea.innerHTML = '<p style="color: #888;">No archived chats yet. Chats are archived when you start a new chat or load another.</p>';
        return;
    }

    histories.forEach((entry, index) => {
        const itemDiv = document.createElement('div');
        itemDiv.classList.add('history-item');
        itemDiv.dataset.historyIndex = index; // Keep for potential direct array access if needed

        const dateDiv = document.createElement('div');
        dateDiv.classList.add('history-item-date');
        dateDiv.textContent = new Date(entry.timestamp).toLocaleString();

        const titleDiv = document.createElement('div');
        // Use a helper to get title text robustly
        let titleText = "Chat Entry";
        if (entry.title) { titleText = entry.title; }
        else {
            const firstUserMsg = entry.conversation.find(msg => msg.role === 'user');
            if (firstUserMsg) {
                if (typeof firstUserMsg.content === 'string') titleText = firstUserMsg.content.substring(0, 50) + (firstUserMsg.content.length > 50 ? '...' : '');
                else if (Array.isArray(firstUserMsg.content) && firstUserMsg.content[0]?.type === 'text') titleText = firstUserMsg.content[0].text.substring(0, 50) + (firstUserMsg.content[0].text.length > 50 ? '...' : '');
                else titleText = 'Multimodal Input...';
            }
        }
        titleDiv.textContent = titleText;

        itemDiv.appendChild(dateDiv);
        itemDiv.appendChild(titleDiv);

        itemDiv.addEventListener('click', () => {
            // loadChatFromHistory is now imported from persistent_storage.js
            // It handles archiving current, loading new, and setting as current active.
            loadChatFromHistory(entry); 
            if (historyPanel) historyPanel.classList.remove('open');
        });
        historyContentArea.appendChild(itemDiv);
    });
}


// --- Learning Log Panel Functions ---
export async function fetchAndDisplayLearnings() {
    if (!learningLogContentArea) return;
    learningLogContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching agent learnings...</p>';
    if (!EIDOS_API_BASE_URL) {
         showNotification("Eidos API Base URL is not set in Settings.", "error");
         learningLogContentArea.innerHTML = '<p style="color: #F44336;">API URL not set.</p>';
         return;
    }
    try {
        const response = await fetch(`${EIDOS_API_BASE_URL}/agent/learnings?limit=${DEFAULT_LOG_FETCH_LIMIT}`, { 
            method: 'GET',
            headers: { 'X-User-Id': currentUserId } 
        });
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to fetch learnings: ${response.status} ${errorText}`);
        }
        const learnings = await response.json();
        learningLogContentArea.innerHTML = ''; 
        if (learnings && learnings.length > 0) {
            learnings.forEach(learning => {
                const itemDiv = document.createElement('div');
                itemDiv.classList.add('history-item'); // Reuse history-item style for consistency
                
                const dateDiv = document.createElement('div');
                dateDiv.classList.add('history-item-date');
                dateDiv.textContent = `Learned: ${new Date(learning.timestamp).toLocaleString()}`;
                itemDiv.appendChild(dateDiv);

                const typeDiv = document.createElement('div');
                typeDiv.style.fontWeight = 'bold';
                typeDiv.style.color = '#F97B65'; 
                typeDiv.textContent = `Type: ${learning.type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}`;
                itemDiv.appendChild(typeDiv);

                const contentDiv = document.createElement('div');
                contentDiv.style.marginTop = '5px';
                if (typeof marked !== 'undefined') {
                    contentDiv.innerHTML = marked.parse(learning.content || "[No content]"); 
                } else {
                    contentDiv.textContent = learning.content || "[No content]";
                }
                itemDiv.appendChild(contentDiv);

                if (learning.metadata) {
                    const metaDiv = document.createElement('div');
                    metaDiv.style.fontSize = '0.8em';
                    metaDiv.style.color = '#AAAAAA';
                    metaDiv.style.marginTop = '8px';
                    metaDiv.style.borderTop = '1px dashed #444';
                    metaDiv.style.paddingTop = '5px';
                    
                    let metaText = "";
                    if (learning.metadata.source_feedback_id) {
                        metaText += `Source Feedback ID: ${String(learning.metadata.source_feedback_id).substring(0,8)}...<br>`;
                    }
                    if (learning.metadata.original_user_input) {
                        metaText += `Original Input: "${String(learning.metadata.original_user_input).substring(0, 50)}..."<br>`;
                    }
                     if (learning.metadata.user_suggestion_or_feedback_text) {
                        metaText += `User's Text: "${String(learning.metadata.user_suggestion_or_feedback_text).substring(0, 70)}..."<br>`;
                    }
                    if (metaText) {
                        metaDiv.innerHTML = metaText;
                        itemDiv.appendChild(metaDiv);
                    }
                }
                learningLogContentArea.appendChild(itemDiv);
            });
        } else {
            learningLogContentArea.innerHTML = '<p style="color: #888;">No recent agent learnings found.</p>';
        }
    } catch (error) {
        console.error("Error fetching agent learnings:", error);
        learningLogContentArea.innerHTML = `<p style="color: #F44336;">Error: ${error.message}</p>`;
        showNotification(`Error fetching agent learnings: ${error.message}`, "error");
    }
}

// --- Dream Journal Panel Functions ---
export async function fetchAndDisplayDreams() {
    if (!dreamJournalContentArea) return;
    dreamJournalContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching dreams...</p>';
    if (!EIDOS_API_BASE_URL) {
         showNotification("Eidos API Base URL is not set in Settings.", "error");
         dreamJournalContentArea.innerHTML = '<p style="color: #F44336;">API URL not set.</p>';
         return;
    }
    try {
        const response = await fetch(`${EIDOS_API_BASE_URL}/agent/dreams?limit=${DEFAULT_LOG_FETCH_LIMIT}`, { 
            method: 'GET',
            headers: { 'X-User-Id': currentUserId } 
        });
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to fetch dreams: ${response.status} ${errorText}`);
        }
        const dreams = await response.json();
        dreamJournalContentArea.innerHTML = ''; 
        if (dreams && dreams.length > 0) {
            dreams.forEach(dream => {
                const itemDiv = document.createElement('div');
                itemDiv.classList.add('dream-journal-item'); 
                
                const dateDiv = document.createElement('div');
                dateDiv.classList.add('dream-timestamp');
                dateDiv.textContent = `Dreamed: ${new Date(dream.timestamp).toLocaleString()}`;
                itemDiv.appendChild(dateDiv);

                const contentDiv = document.createElement('div');
                contentDiv.classList.add('dream-content');
                if (typeof marked !== 'undefined') {
                    contentDiv.innerHTML = marked.parse(dream.content || "[No textual dream content]"); 
                } else {
                    contentDiv.textContent = dream.content || "[No textual dream content]";
                }
                itemDiv.appendChild(contentDiv);

                if (dream.dream_image_url) {
                    const imgContainer = document.createElement('div');
                    imgContainer.classList.add('dream-image-container');
                    const imgElement = document.createElement('img');
                    imgElement.src = dream.dream_image_url; 
                    imgElement.alt = "Dream visualization";
                    imgElement.onerror = () => { 
                        imgElement.alt = "Error loading dream image."; 
                        console.warn("Failed to load dream image:", dream.dream_image_url);
                    };
                    imgContainer.appendChild(imgElement);
                    itemDiv.appendChild(imgContainer);
                }

                if (dream.dream_seed_summary) {
                    const seedDiv = document.createElement('div');
                    seedDiv.classList.add('dream-seed-summary');
                    seedDiv.innerHTML = `<strong>Inspired by:</strong> ${dream.dream_seed_summary}`;
                    itemDiv.appendChild(seedDiv);
                }
                dreamJournalContentArea.appendChild(itemDiv);
            });
        } else {
            dreamJournalContentArea.innerHTML = '<p style="color: #888;">No recent dreams found in the journal.</p>';
        }
    } catch (error) {
        console.error("Error fetching dreams:", error);
        dreamJournalContentArea.innerHTML = `<p style="color: #F44336;">Error fetching dreams: ${error.message}</p>`;
        showNotification(`Error fetching dreams: ${error.message}`, "error");
    }
}

// --- Knowledge Upkeep Log Panel Functions ---
export async function fetchAndDisplayKnowledgeVerifications() {
    if (!knowledgeLogContentArea) {
        console.error("Knowledge log content area not found in DOM.");
        return;
    }
    knowledgeLogContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching knowledge upkeep log...</p>';
    
    if (!EIDOS_API_BASE_URL) {
         showNotification("Eidos API Base URL is not set in Settings.", "error");
         knowledgeLogContentArea.innerHTML = '<p style="color: #F44336;">API URL not set. Please configure it in Settings.</p>';
         return;
    }

    try {
        const limit = DEFAULT_LOG_FETCH_LIMIT;
        const response = await fetch(`${EIDOS_API_BASE_URL}/agent/knowledge_verifications?limit=${limit}`, { 
            method: 'GET',
            headers: { 'X-User-Id': currentUserId } 
        });

        if (!response.ok) {
            const errorText = await response.text();
            let detail = errorText;
            try { detail = JSON.parse(errorText).detail || errorText; } catch (e) {}
            throw new Error(`Failed to fetch knowledge verifications: ${response.status} - ${detail}`);
        }

        const verifications = await response.json();
        knowledgeLogContentArea.innerHTML = ''; 

        if (verifications && verifications.length > 0) {
            verifications.forEach(verification => {
                const itemDiv = document.createElement('div');
                itemDiv.classList.add('knowledge-log-item');
                
                const metadata = verification.metadata || {};
                const originalFactContent = verification.content || "[No original fact content]";
                const lastVerifiedTimestamp = metadata.last_verified_timestamp;
                const verificationAttemptFailed = metadata.verification_attempt_failed === true || metadata.verification_attempt_failed === 'true' || metadata.verification_attempt_failed === 1;
                const isOutdated = metadata.status === 'outdated_by_upkeep';
                const supersedingFactContent = metadata.superseding_fact_content; // From backend enhancement
                const llmReasoning = metadata.reason; 

                const timestampDiv = document.createElement('div');
                timestampDiv.classList.add('log-timestamp');
                if (lastVerifiedTimestamp) {
                    timestampDiv.textContent = `Verified: ${new Date(lastVerifiedTimestamp).toLocaleString()}`;
                } else {
                    timestampDiv.textContent = `Verification Attempted: ${new Date(verification.timestamp).toLocaleString()}`;
                }
                itemDiv.appendChild(timestampDiv);

                const factDiv = document.createElement('div');
                factDiv.classList.add('log-fact');
                const factStrong = document.createElement('strong');
                factStrong.textContent = "Original Fact: ";
                factDiv.appendChild(factStrong);
                factDiv.appendChild(document.createTextNode(originalFactContent.substring(0, 200) + (originalFactContent.length > 200 ? "..." : "")));
                itemDiv.appendChild(factDiv);

                const statusDiv = document.createElement('div');
                statusDiv.classList.add('log-status');
                let statusText = "Status Unknown";
                let statusClass = "unverifiable"; 

                if (isOutdated && supersedingFactContent) {
                    statusText = "Updated"; statusClass = "updated"; itemDiv.style.borderLeftColor = "#FF9800"; 
                } else if (verificationAttemptFailed) {
                    statusText = "Unverifiable / Error"; statusClass = "unverifiable"; itemDiv.style.borderLeftColor = "#F44336"; 
                } else if (lastVerifiedTimestamp && !isOutdated) { 
                    statusText = "Confirmed Accurate"; statusClass = "accurate"; itemDiv.style.borderLeftColor = "#4CAF50"; 
                } else { itemDiv.style.borderLeftColor = "#757575"; }
                
                statusDiv.classList.add(statusClass);
                statusDiv.textContent = `Status: ${statusText}`;
                itemDiv.appendChild(statusDiv);

                if (isOutdated && supersedingFactContent && supersedingFactContent !== "[Content of new fact not found]") {
                    const newStatementDiv = document.createElement('div');
                    newStatementDiv.classList.add('log-new-statement');
                    const newFactStrong = document.createElement('strong');
                    newFactStrong.textContent = "Updated To: "; newStatementDiv.appendChild(newFactStrong);
                    newStatementDiv.appendChild(document.createTextNode(supersedingFactContent.substring(0, 200) + (supersedingFactContent.length > 200 ? "..." : "")));
                    itemDiv.appendChild(newStatementDiv);
                } else if (isOutdated && metadata.superseded_by_fact_id && !supersedingFactContent) {
                    const newStatementDiv = document.createElement('div');
                    newStatementDiv.classList.add('log-new-statement');
                    newStatementDiv.textContent = `Updated. New fact ID: ${metadata.superseded_by_fact_id}`;
                    itemDiv.appendChild(newStatementDiv);
                }

                if (llmReasoning) {
                    const reasonDiv = document.createElement('div');
                    reasonDiv.style.fontSize = '0.9em'; reasonDiv.style.color = '#B0B0B0'; 
                    reasonDiv.style.marginTop = '4px'; reasonDiv.style.paddingLeft = '10px';
                    reasonDiv.style.borderLeft = '2px dotted #555';
                    const reasonStrong = document.createElement('strong');
                    reasonStrong.textContent = "Details: "; reasonDiv.appendChild(reasonStrong);
                    reasonDiv.appendChild(document.createTextNode(llmReasoning));
                    itemDiv.appendChild(reasonDiv);
                }
                knowledgeLogContentArea.appendChild(itemDiv);
            });
        } else {
            knowledgeLogContentArea.innerHTML = '<p style="color: #888;">No knowledge upkeep activities found in the log.</p>';
        }
    } catch (error) {
        console.error("Error fetching or displaying knowledge verifications:", error);
        knowledgeLogContentArea.innerHTML = `<p style="color: #F44336;">Error: ${error.message}</p>`;
        showNotification(`Error fetching knowledge log: ${error.message}`, "error");
    }
}

// --- Daily Briefing Panel Functions ---
export async function fetchAndDisplayDailyBriefingGUI() { // Renamed to avoid conflict with imported name
    if (!dailyBriefingContentArea) return;
    dailyBriefingContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching briefing...</p>';
    if (!EIDOS_API_BASE_URL) {
         showNotification("Eidos API Base URL is not set in Settings.", "error");
         dailyBriefingContentArea.innerHTML = '<p style="color: #F44336;">API URL not set.</p>';
         return;
    }
    try {
        const response = await fetch(`${EIDOS_API_BASE_URL}/briefing`, {
            method: 'GET',
            headers: { 'X-User-Id': currentUserId }
        });
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to fetch briefing: ${response.status} ${errorText}`);
        }
        const result = await response.json();
        if (result.success && result.briefing_content) {
            if (typeof marked !== 'undefined') {
                dailyBriefingContentArea.innerHTML = marked.parse(result.briefing_content);
            } else {
                dailyBriefingContentArea.textContent = result.briefing_content;
            }
            if (typeof Prism !== 'undefined') Prism.highlightAllUnder(dailyBriefingContentArea);
            if (typeof MathJax !== 'undefined' && MathJax.typesetPromise) {
                 MathJax.typesetPromise([dailyBriefingContentArea]).catch(err => console.warn("MathJax (briefing):", err));
            }
        } else if (result.message) {
            dailyBriefingContentArea.innerHTML = `<p style="color: #BBBBBB;">${result.message}</p>`;
        } else {
            dailyBriefingContentArea.innerHTML = '<p style="color: #F97B65;">Briefing not available or an error occurred.</p>';
        }
    } catch (error) {
        console.error("Error fetching daily briefing:", error);
        dailyBriefingContentArea.innerHTML = `<p style="color: #F44336;">Error: ${error.message}</p>`;
        showNotification(`Error fetching briefing: ${error.message}`, "error");
    }
}


console.log("ui_panels.js loaded.");

let _loadChatFromHistoryFunc = null;

export function setLoadChatFromHistoryFunction(func) {
    _loadChatFromHistoryFunc = func;
}

// Example usage placeholder:
// if (_loadChatFromHistoryFunc) _loadChatFromHistoryFunc(historyItem);
