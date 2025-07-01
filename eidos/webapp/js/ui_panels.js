// webapp/js/ui_panels.js

import {
    EIDOS_API_BASE_URL,
    DEFAULT_LOG_FETCH_LIMIT
} from './config.js';
import {
    historyContentArea,
    learningLogContentArea,
    dreamJournalContentArea,
    knowledgeLogContentArea,
    dailyBriefingContentArea,
    userFactsContentArea,
    historyPanel
} from './dom_elements.js';
import { showNotification } from './utils.js';
import { loadChatFromHistory, loadArchivedHistories } from './persistent_storage.js';
import * as DOM from './dom_elements.js'; // Ensure DOM is imported if not already

// --- "Facts About You" Panel Functions (Corrected with Forget Button) ---
export async function fetchAndDisplayUserFacts() {
    if (!userFactsContentArea) {
        console.error("User facts content area not found in DOM.");
        return;
    }
    userFactsContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching facts Eidos knows about you...</p>';

    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    const currentUserIdForFetch = window.currentUserId;

    if (!currentApiBaseUrl) {
         showNotification("Eidos API Base URL is not set in Settings.", "error");
         userFactsContentArea.innerHTML = '<p style="color: #F44336;">API URL not set.</p>';
         return;
    }
    if (!currentUserIdForFetch || ["unknown_user", "api_guest_user"].includes(currentUserIdForFetch) ) {
        userFactsContentArea.innerHTML = '<p style="color: #888;">Please set a specific User ID in Settings to see your personalized facts.</p>';
        return;
    }

    try {
        const response = await fetch(`${currentApiBaseUrl}/user/facts`, {
            method: 'GET',
            headers: { 'X-User-Id': currentUserIdForFetch }
        });

        if (!response.ok) {
            let errorMsg = `Failed to fetch user facts: ${response.status}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.detail || errorMsg;
            } catch (e) { /* ignore parsing error, use status text */ }
            throw new Error(errorMsg);
        }

        const userFacts = await response.json();
        userFactsContentArea.innerHTML = '';

        if (userFacts && userFacts.length > 0) {
            const ul = document.createElement('ul');
            ul.style.listStyleType = 'none';
            ul.style.paddingLeft = '0';

            userFacts.forEach(factEntry => {
                const li = document.createElement('li');
                li.classList.add('history-item', 'user-fact-list-item');
                li.style.borderLeft = '3px solid #5A9BFF';
                li.dataset.memoryId = factEntry.id;

                let factAttribute = "Unknown Attribute";
                let factValue = "Unknown Value";
                let originalStatement = "";

                try {
                    const contentData = JSON.parse(factEntry.content);
                    factAttribute = (contentData.attribute || "").replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                    factValue = contentData.value !== undefined && contentData.value !== null ? String(contentData.value) : "Not specified";
                    originalStatement = contentData.original_user_statement || "";
                } catch (e) {
                    console.warn("Could not parse user_fact content JSON for entry ID " + factEntry.id + ":", factEntry.content, e);
                    factValue = factEntry.content;
                    factAttribute = "Stored Fact (Raw)";
                }

                const factDisplayContainer = document.createElement('div');
                factDisplayContainer.classList.add('user-fact-display');

                const attributeDiv = document.createElement('div');
                attributeDiv.classList.add('user-fact-attribute');
                attributeDiv.innerHTML = `<strong>${factAttribute}:</strong>`;
                factDisplayContainer.appendChild(attributeDiv);

                const valueDiv = document.createElement('div');
                valueDiv.classList.add('user-fact-value');
                valueDiv.textContent = factValue;
                factDisplayContainer.appendChild(valueDiv);
                
                if (originalStatement) {
                    const contextDiv = document.createElement('div');
                    contextDiv.classList.add('user-fact-context');
                    contextDiv.textContent = `(From: "${originalStatement.substring(0, 70)}${originalStatement.length > 70 ? '...' : ''}")`;
                    factDisplayContainer.appendChild(contextDiv);
                }
                
                // *** Create Forget Button - THIS IS THE RESTORED PART ***
                const forgetButton = document.createElement('button');
                forgetButton.classList.add('forget-fact-button');
                forgetButton.textContent = 'Forget';
                forgetButton.title = 'Make Eidos forget this specific fact.';
                forgetButton.dataset.memoryId = factEntry.id;

                forgetButton.addEventListener('click', async (event) => {
                    event.stopPropagation(); 
                    const memoryIdToForget = event.target.dataset.memoryId;
                    const factValuePreview = typeof factValue === 'string' ? factValue.substring(0,30) : 'this fact';
                    if (confirm(`Are you sure you want Eidos to forget this fact: "${factAttribute}: ${factValuePreview}..."?`)) {
                        await forgetUserFactAPI(memoryIdToForget); // Call the API helper
                    }
                });
                // *** END OF RESTORED PART ***

                li.appendChild(factDisplayContainer);
                li.appendChild(forgetButton); // Append the button to the list item
                ul.appendChild(li);
            });
            userFactsContentArea.appendChild(ul);
        } else {
            userFactsContentArea.innerHTML = '<p style="color: #888;">Eidos hasn\'t learned any specific facts about you yet. Try telling it something like "My favorite color is blue."</p>';
        }
    } catch (error) {
        console.error("Error fetching or displaying user facts:", error);
        userFactsContentArea.innerHTML = `<p style="color: #F44336;">Error: ${error.message}</p>`;
        showNotification(`Error fetching your facts: ${error.message}`, "error");
    }
}

// *** New helper function to call the delete API ***
async function forgetUserFactAPI(memoryId) {
    if (!memoryId) {
        showNotification("Cannot forget fact: Memory ID is missing.", "error");
        return;
    }
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    const currentUserId = window.currentUserId; 

    showNotification("Requesting to forget fact...", "info");
    try {
        // The endpoint is /v1/memory/entry/{memory_id}
        const response = await fetch(`${currentApiBaseUrl}/memory/entry/${memoryId}`, {
            method: 'DELETE',
            headers: {
                'X-User-Id': currentUserId,
                // 'X-Admin-Password': '' // Only include if admin override is needed and implemented for this specific action
            }
        });

        if (response.ok) {
            showNotification("Fact forgotten successfully.", "success");
            fetchAndDisplayUserFacts(); // Refresh the panel to show the fact is gone
        } else {
            const errorData = await response.json().catch(() => ({ detail: "Unknown error deleting fact." }));
            showNotification(`Failed to forget fact: ${errorData.detail || response.statusText}`, 'error');
            console.error("Forget Fact API Error:", response.status, errorData);
        }
    } catch (error) {
        console.error("Error calling forget fact API:", error);
        showNotification(`Error forgetting fact: ${error.message}`, 'error');
    }
}


// --- History Panel Functions ---
export async function renderHistoryPanel() { // Make the function async
    if (!historyContentArea) {
        console.error("History content area element not found.");
        return;
    }
    try {
        historyContentArea.innerHTML = '<p style="color: #BBBBBB;">Loading history...</p>'; // Add a loading message
        const histories = await loadArchivedHistories(); // Await the promise
        historyContentArea.innerHTML = ''; // Clear previous content/loading message

        if (!Array.isArray(histories)) {
            console.error("loadArchivedHistories did not return an array:", histories);
            historyContentArea.innerHTML = '<p style="color: #F44336;">Error: Could not load history data correctly.</p>';
            return;
        }

        if (histories.length === 0) {
            historyContentArea.innerHTML = '<p style="color: #888;">No archived chats yet. Chats are archived when you start a new chat or load another.</p>';
            return;
        }

        histories.forEach((entry, index) => {
            const itemDiv = document.createElement('div');
            itemDiv.classList.add('history-item');
            itemDiv.dataset.historyIndex = index; // Keep index if needed, though entry itself is better

            const dateDiv = document.createElement('div');
            dateDiv.classList.add('history-item-date');
            dateDiv.textContent = new Date(entry.timestamp).toLocaleString();

            const titleDiv = document.createElement('div');
            let titleText = entry.title || "Archived Chat"; // Use pre-calculated title if available
            if (!entry.title) { // Fallback to derive title if not present
                const firstUserMsg = entry.conversation.find(msg => msg.role === 'user');
                if (firstUserMsg && firstUserMsg.content) {
                    if (typeof firstUserMsg.content === 'string') {
                        titleText = firstUserMsg.content.substring(0, 50) + (firstUserMsg.content.length > 50 ? '...' : '');
                    } else if (Array.isArray(firstUserMsg.content) && firstUserMsg.content[0]?.type === 'text' && typeof firstUserMsg.content[0].text === 'string') {
                        titleText = firstUserMsg.content[0].text.substring(0, 50) + (firstUserMsg.content[0].text.length > 50 ? '...' : '');
                    } else {
                        titleText = "Chat Entry";
                    }
                }
            }
            titleDiv.textContent = titleText;

            itemDiv.appendChild(dateDiv);
            itemDiv.appendChild(titleDiv);

            itemDiv.addEventListener('click', () => {
                loadChatFromHistory(entry); // Pass the full entry object
                if (historyPanel) historyPanel.classList.remove('open');
            });
            historyContentArea.appendChild(itemDiv);
        });
    } catch (error) {
        console.error("Error rendering history panel:", error);
        historyContentArea.innerHTML = `<p style="color: #F44336;">Error: ${error.message}</p>`;
        showNotification(`Error loading history: ${error.message}`, "error");
    }
}

// --- Learning Log Panel Functions ---
export async function fetchAndDisplayLearnings() {
    if (!learningLogContentArea) {
        console.error("Learning log content area not found.");
        return;
    }
    learningLogContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching agent learnings...</p>';
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    const currentUserIdForFetch = window.currentUserId;

    if (!currentApiBaseUrl) {
        showNotification("Eidos API Base URL is not set.", "error");
        learningLogContentArea.innerHTML = '<p style="color: #F44336;">API URL not set.</p>';
        return;
    }
    try {
        const response = await fetch(`${currentApiBaseUrl}/agent/learnings?limit=${DEFAULT_LOG_FETCH_LIMIT}`, {
            method: 'GET',
            headers: { 'X-User-Id': currentUserIdForFetch || "unknown_user" }
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `Failed to fetch learnings: ${response.status}`);
        }
        const learnings = await response.json();
        learningLogContentArea.innerHTML = ''; // Clear loading message
        if (learnings && learnings.length > 0) {
            learnings.forEach(learning => {
                const itemDiv = document.createElement('div');
                itemDiv.classList.add('history-item'); // Reuse style
                itemDiv.style.borderLeft = '3px solid #FFB74D'; // Learning color

                const dateDiv = document.createElement('div');
                dateDiv.classList.add('history-item-date');
                dateDiv.textContent = `Learned: ${new Date(learning.timestamp).toLocaleString()}`;
                itemDiv.appendChild(dateDiv);

                const typeDiv = document.createElement('div');
                typeDiv.style.fontWeight = 'bold';
                typeDiv.style.color = '#FFB74D'; // Learning color
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

                const metadata = learning.metadata;
                if (metadata) {
                    const metaDisplay = document.createElement('div');
                    metaDisplay.style.fontSize = '0.8em';
                    metaDisplay.style.color = '#AAAAAA';
                    metaDisplay.style.marginTop = '5px';
                    metaDisplay.style.borderTop = '1px dashed #444';
                    metaDisplay.style.paddingTop = '5px';
                    let metaText = [];
                    if(metadata.source_feedback_id) metaText.push(`Source Feedback ID: ${metadata.source_feedback_id.substring(0,8)}`);
                    if(metadata.original_feedback_type) metaText.push(`Original Type: ${metadata.original_feedback_type}`);
                    if(metadata.user_id && metadata.user_id !== currentUserIdForFetch && metadata.user_id !== "system_reflection") metaText.push(`User: ${metadata.user_id}`);

                    if(metaText.length > 0) {
                        metaDisplay.textContent = metaText.join(' | ');
                        itemDiv.appendChild(metaDisplay);
                    }
                }
                learningLogContentArea.appendChild(itemDiv);
            });
        } else {
            learningLogContentArea.innerHTML = '<p style="color: #888;">No agent learnings recorded yet.</p>';
        }
    } catch (error) {
        console.error("Error fetching agent learnings:", error);
        learningLogContentArea.innerHTML = `<p style="color: #F44336;">Error: ${error.message}</p>`;
        showNotification(`Error fetching learnings: ${error.message}`, "error");
    }
}

// --- Dream Journal Panel Functions ---
export async function fetchAndDisplayDreams() {
    if (!dreamJournalContentArea) {
        console.error("Dream journal content area not found.");
        return;
    }
    dreamJournalContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching dreams...</p>';
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    const currentUserIdForFetch = window.currentUserId;

    if (!currentApiBaseUrl) {
        showNotification("Eidos API Base URL is not set.", "error");
        dreamJournalContentArea.innerHTML = '<p style="color: #F44336;">API URL not set.</p>';
        return;
    }
    try {
        const response = await fetch(`${currentApiBaseUrl}/agent/dreams?limit=${DEFAULT_LOG_FETCH_LIMIT}`, {
            method: 'GET',
            headers: { 'X-User-Id': currentUserIdForFetch || "unknown_user" }
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `Failed to fetch dreams: ${response.status}`);
        }
        const dreams = await response.json();
        dreamJournalContentArea.innerHTML = ''; // Clear loading
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

                if (dream.dream_seed_summary) {
                    const seedDiv = document.createElement('div');
                    seedDiv.classList.add('dream-seed-summary');
                    seedDiv.innerHTML = `<strong>Seed:</strong> <em>${dream.dream_seed_summary}</em>`;
                    itemDiv.appendChild(seedDiv);
                }

                if (dream.dream_image_url) {
                    const imgContainer = document.createElement('div');
                    imgContainer.classList.add('dream-image-container');
                    const imgElement = document.createElement('img');
                    imgElement.src = dream.dream_image_url;
                    imgElement.alt = "Dream Image";
                    imgElement.onerror = () => { imgElement.alt = "Dream image failed to load"; imgElement.style.display='none'; };
                    imgContainer.appendChild(imgElement);
                    itemDiv.appendChild(imgContainer);
                }
                dreamJournalContentArea.appendChild(itemDiv);
            });
        } else {
            dreamJournalContentArea.innerHTML = '<p style="color: #888;">No dreams recorded yet.</p>';
        }
    } catch (error) {
        console.error("Error fetching agent dreams:", error);
        dreamJournalContentArea.innerHTML = `<p style="color: #F44336;">Error: ${error.message}</p>`;
        showNotification(`Error fetching dreams: ${error.message}`, "error");
    }
}

// --- Knowledge Upkeep Log Panel Functions ---
export async function fetchAndDisplayKnowledgeVerifications() {
    if (!knowledgeLogContentArea) {
        console.error("Knowledge log content area not found.");
        return;
    }
    knowledgeLogContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching knowledge upkeep log...</p>';
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    const currentUserIdForFetch = window.currentUserId;

    if (!currentApiBaseUrl) {
        showNotification("Eidos API Base URL is not set.", "error");
        knowledgeLogContentArea.innerHTML = '<p style="color: #F44336;">API URL not set.</p>';
        return;
    }
    try {
        const response = await fetch(`${currentApiBaseUrl}/agent/knowledge_verifications?limit=${DEFAULT_LOG_FETCH_LIMIT}`, {
            method: 'GET',
            headers: { 'X-User-Id': currentUserIdForFetch || "unknown_user" }
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `Failed to fetch knowledge log: ${response.status}`);
        }
        const verifications = await response.json();
        knowledgeLogContentArea.innerHTML = ''; // Clear loading
        if (verifications && verifications.length > 0) {
            verifications.forEach(verification => {
                const itemDiv = document.createElement('div');
                itemDiv.classList.add('knowledge-log-item');

                const metadata = verification.metadata || {};
                const verificationTimestamp = metadata.last_verified_timestamp ? new Date(metadata.last_verified_timestamp).toLocaleString() : 'N/A';
                const status = metadata.status || (metadata.verification_attempt_failed ? 'Verification Failed' : 'Unknown');
                const reason = metadata.verification_reason || 'No details.';

                let statusColor = '#AAAAAA';
                if (status === 'accurate') statusColor = '#81C784';
                else if (status === 'updated' || status === 'outdated_by_upkeep') statusColor = '#FFB74D';
                else if (status === 'Verification Failed' || status.toLowerCase().includes('error')) statusColor = '#E57373';

                itemDiv.style.borderLeft = `3px solid ${statusColor}`;

                const dateDiv = document.createElement('div');
                dateDiv.classList.add('log-timestamp');
                dateDiv.textContent = `Verified: ${verificationTimestamp}`;
                itemDiv.appendChild(dateDiv);

                const factDiv = document.createElement('div');
                factDiv.classList.add('log-fact');
                factDiv.innerHTML = `<strong>Fact:</strong> "${(verification.content || "N/A").substring(0,150)}..."`;
                itemDiv.appendChild(factDiv);

                const statusDiv = document.createElement('div');
                statusDiv.classList.add('log-status');
                statusDiv.style.color = statusColor;
                statusDiv.textContent = `Status: ${status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}`;
                itemDiv.appendChild(statusDiv);

                if (status === 'updated' || status === 'outdated_by_upkeep') {
                    if (metadata.superseded_by_fact_id) {
                        const newFactId = metadata.superseded_by_fact_id;
                        const newFactInfo = document.createElement('div');
                        newFactInfo.style.fontSize = '0.9em';
                        newFactInfo.innerHTML = `Superseded by new fact (ID: ...${newFactId.substring(newFactId.length - 8)})`;
                        itemDiv.appendChild(newFactInfo);
                    }
                }
                const reasonDiv = document.createElement('div');
                reasonDiv.style.fontSize = '0.9em';
                reasonDiv.style.marginTop = '4px';
                reasonDiv.innerHTML = `<em>Details: ${reason}</em>`;
                itemDiv.appendChild(reasonDiv);

                knowledgeLogContentArea.appendChild(itemDiv);
            });
        } else {
            knowledgeLogContentArea.innerHTML = '<p style="color: #888;">No knowledge upkeep activities recorded yet.</p>';
        }
    } catch (error) {
        console.error("Error fetching knowledge log:", error);
        knowledgeLogContentArea.innerHTML = `<p style="color: #F44336;">Error: ${error.message}</p>`;
        showNotification(`Error fetching knowledge log: ${error.message}`, "error");
    }
}

// --- Daily Briefing Panel Functions ---
export async function fetchAndDisplayDailyBriefingGUI() {
    if (!dailyBriefingContentArea) {
        console.error("Daily briefing content area not found.");
        return;
    }
    dailyBriefingContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching briefing...</p>';
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    const currentUserIdForFetch = window.currentUserId;

    if (!currentApiBaseUrl) {
        showNotification("Eidos API Base URL is not set.", "error");
        dailyBriefingContentArea.innerHTML = '<p style="color: #F44336;">API URL not set.</p>';
        return;
    }
    try {
        const response = await fetch(`${currentApiBaseUrl}/briefing`, {
            method: 'GET',
            headers: { 'X-User-Id': currentUserIdForFetch || "unknown_user" }
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.message || errorData.detail || `Failed to fetch briefing: ${response.status}`);
        }
        const result = await response.json();
        if (result.success && result.briefing_content) {
            if (typeof marked !== 'undefined') {
                dailyBriefingContentArea.innerHTML = marked.parse(result.briefing_content);
            } else {
                dailyBriefingContentArea.textContent = result.briefing_content;
            }
            if (typeof Prism !== 'undefined') Prism.highlightAllUnder(dailyBriefingContentArea);
            if (typeof MathJax !== 'undefined' && MathJax.typesetPromise) MathJax.typesetPromise([dailyBriefingContentArea]).catch(err => console.warn("MathJax (briefing):", err));
        } else {
            dailyBriefingContentArea.innerHTML = `<p style="color: #888;">${result.message || "Briefing not available at the moment."}</p>`;
        }
    } catch (error) {
        console.error("Error fetching daily briefing:", error);
        dailyBriefingContentArea.innerHTML = `<p style="color: #F44336;">Error: ${error.message}</p>`;
        showNotification(`Error fetching briefing: ${error.message}`, "error");
    }
}

// --- Pathos Chronos Panel Functions ---
export async function fetchAndDisplayPathosChronosData() {
    console.log("DEBUG: fetchAndDisplayPathosChronosData CALLED (B.1 update)");

    if (!DOM.chronosCurrentActivityDisplay || !DOM.chronosTodaysScheduleList || !DOM.chronosUpcomingEventsList) {
        console.error("Chronos panel DOM elements not found in fetchAndDisplayPathosChronosData.");
        if (DOM.chronosPanelContentArea) { 
            DOM.chronosPanelContentArea.innerHTML = '<p style="color: #F44336;">Error: Panel components missing. Cannot load Pathos\'s day.</p>';
        }
        return;
    }

    DOM.chronosCurrentActivityDisplay.innerHTML = '<p style="color: #BBBBBB;">Loading current activity...</p>';
    DOM.chronosTodaysScheduleList.innerHTML = '<p style="color: #BBBBBB;">Loading today\'s schedule...</p>';
    DOM.chronosUpcomingEventsList.innerHTML = '<p style="color: #BBBBBB;">Loading upcoming events...</p>';

    const currentApiBaseUrl = window.EIDOS_API_BASE_URL;
    if (!currentApiBaseUrl) {
        const errorMsg = '<p style="color: #F44336;">Error: Eidos API Base URL not set. Cannot load Pathos\'s day.</p>';
        DOM.chronosCurrentActivityDisplay.innerHTML = errorMsg;
        DOM.chronosTodaysScheduleList.innerHTML = errorMsg;
        DOM.chronosUpcomingEventsList.innerHTML = errorMsg;
        showNotification("Eidos API Base URL is not set in Settings.", "error");
        return;
    }

    let scheduleFetched = false;
    let eventsFetched = false;

    // Fetch Today's Schedule
    try {
        console.log("DEBUG: Chronos - Fetching today's schedule from:", `${currentApiBaseUrl}/pathos/schedule/today`);
        const scheduleResponse = await fetch(`${currentApiBaseUrl}/pathos/schedule/today`, {
            headers: { 'X-User-Id': window.currentUserId || "pathos_agent_internal" } 
        });
        console.log("DEBUG: Chronos - Schedule Response Status:", scheduleResponse.status);
        if (!scheduleResponse.ok) {
            const errText = await scheduleResponse.text();
            console.error("DEBUG: Chronos - Schedule Fetch Error Text:", errText);
            throw new Error(`Failed to fetch today's schedule: ${scheduleResponse.status} ${errText}`);
        }
        const scheduleSlots = await scheduleResponse.json();
        console.log("DEBUG: Chronos - Received scheduleSlots:", JSON.stringify(scheduleSlots, null, 2).substring(0, 500) + "...");
        renderTodaysSchedule(scheduleSlots);
        determineAndRenderCurrentActivity(scheduleSlots);
        scheduleFetched = true;
    } catch (error) {
        console.error("DEBUG: Chronos - Error fetching today's schedule (in catch block):", error);
        if (DOM.chronosTodaysScheduleList) DOM.chronosTodaysScheduleList.innerHTML = `<p style="color: #F44336;">Error loading schedule: ${error.message}</p>`;
        if (DOM.chronosCurrentActivityDisplay) DOM.chronosCurrentActivityDisplay.innerHTML = `<p style="color: #F44336;">Error determining current activity.</p>`;
    }

    // Fetch Upcoming Events
    try {
        const daysAheadForEvents = 14; 
        console.log("DEBUG: Chronos - Fetching upcoming events from:", `${currentApiBaseUrl}/pathos/events/upcoming?days_ahead=${daysAheadForEvents}`);
        const eventsResponse = await fetch(`${currentApiBaseUrl}/pathos/events/upcoming?days_ahead=${daysAheadForEvents}`, {
             headers: { 'X-User-Id': window.currentUserId || "pathos_agent_internal" } 
        });
        console.log("DEBUG: Chronos - Events Response Status:", eventsResponse.status);
        if (!eventsResponse.ok) {
            const errText = await eventsResponse.text();
            console.error("DEBUG: Chronos - Events Fetch Error Text:", errText);
            throw new Error(`Failed to fetch upcoming events: ${eventsResponse.status} ${errText}`);
        }
        const upcomingEvents = await eventsResponse.json();
        console.log("DEBUG: Chronos - Received upcomingEvents:", JSON.stringify(upcomingEvents, null, 2).substring(0, 500) + "...");
        renderUpcomingEvents(upcomingEvents); 
        eventsFetched = true;
    } catch (error) {
        console.error("DEBUG: Chronos - Error fetching upcoming events (in catch block):", error);
        if (DOM.chronosUpcomingEventsList) DOM.chronosUpcomingEventsList.innerHTML = `<p style="color: #F44336;">Error loading events: ${error.message}</p>`;
    }

    if (scheduleFetched && eventsFetched) {
        // showNotification("Pathos's day view updated.", "info"); // Can be noisy if called often
    } else if (scheduleFetched) {
        showNotification("Pathos's schedule updated, but events failed to load.", "warning");
    } else if (eventsFetched) {
        showNotification("Pathos's upcoming events updated, but schedule failed to load.", "warning");
    } else {
        // Both failed, error messages already shown in respective divs
    }
}

function determineAndRenderCurrentActivity(scheduleSlots) {
    console.log("DEBUG: determineAndRenderCurrentActivity called with:", JSON.stringify(scheduleSlots, null, 2).substring(0, 500) + "...");
    if (!DOM.chronosCurrentActivityDisplay) return;
    if (!scheduleSlots || !Array.isArray(scheduleSlots) || scheduleSlots.length === 0) {
        DOM.chronosCurrentActivityDisplay.innerHTML = '<p style="color: #888;">No schedule available to determine current activity.</p>';
        return;
    }

    const now = new Date();
    const currentTime = now.getHours() * 60 + now.getMinutes();

    let currentActivity = null;
    for (const slot of scheduleSlots) {
        try {
            if (!slot || typeof slot.start_time !== 'string' || typeof slot.end_time !== 'string') {
                console.warn("Skipping invalid slot in determineAndRenderCurrentActivity:", slot);
                continue;
            }
            const [startH, startM] = slot.start_time.split(':').map(Number);
            const [endH, endM] = slot.end_time.split(':').map(Number);
            const slotStartTimeMinutes = startH * 60 + startM;
            const slotEndTimeMinutes = endH * 60 + endM;

            if (currentTime >= slotStartTimeMinutes && currentTime < slotEndTimeMinutes) {
                currentActivity = slot;
                break;
            }
        } catch (e) {
            console.error("Error parsing time for activity slot:", slot, e);
        }
    }

    if (currentActivity) {
        const title = currentActivity.activity_title || "Unnamed Activity";
        const startTime = currentActivity.start_time || "N/A";
        const endTime = currentActivity.end_time || "N/A";
        const description = currentActivity.activity_details && currentActivity.activity_details.description ? currentActivity.activity_details.description : "No details.";
        const subFocus = currentActivity.activity_details && currentActivity.activity_details.sub_focus ? currentActivity.activity_details.sub_focus : "";

        DOM.chronosCurrentActivityDisplay.innerHTML = `
            <p><strong>${title}</strong> (${startTime} - ${endTime})</p>
            <p style="font-size: 0.9em; color: #B0B0B0;"><em>${description}</em></p>
            ${subFocus ? `<p style="font-size: 0.8em; color: #999;">Focus: ${subFocus}</p>` : ''}
        `;
    } else {
        DOM.chronosCurrentActivityDisplay.innerHTML = '<p style="color: #888;">Pathos is currently between scheduled activities.</p>';
    }
}

function renderTodaysSchedule(scheduleSlots) {
    console.log("DEBUG: renderTodaysSchedule called with:", JSON.stringify(scheduleSlots, null, 2).substring(0, 500) + "...");
    if (!DOM.chronosTodaysScheduleList) return;
    if (!scheduleSlots || !Array.isArray(scheduleSlots) || scheduleSlots.length === 0) {
        DOM.chronosTodaysScheduleList.innerHTML = '<p style="color: #888;">No schedule planned for today yet, or an error occurred.</p>';
        return;
    }

    let html = '<ul class="chronos-list">';
    scheduleSlots.forEach(slot => {
        const startTime = slot.start_time || "N/A";
        const endTime = slot.end_time || "N/A";
        const title = slot.activity_title || "Unnamed Activity";
        const type = slot.activity_type || "Unknown";
        const description = slot.activity_details && slot.activity_details.description ? slot.activity_details.description : "No details.";
        const subFocus = slot.activity_details && slot.activity_details.sub_focus ? slot.activity_details.sub_focus : "";

        html += `
            <li class="chronos-list-item schedule-item">
                <div class="chronos-time">${startTime} - ${endTime}</div>
                <div class="chronos-title">${title} <span class="chronos-type">(${type})</span></div>
                <div class="chronos-description">${description}</div>
                ${subFocus ? `<div class="chronos-subfocus">Focus: ${subFocus}</div>` : ''}
            </li>
        `;
    });
    html += '</ul>';
    DOM.chronosTodaysScheduleList.innerHTML = html;
}

function renderUpcomingEvents(events) {
    console.log("DEBUG: renderUpcomingEvents called with:", JSON.stringify(events, null, 2).substring(0, 500) + "...");
    if (!DOM.chronosUpcomingEventsList) {
        console.error("renderUpcomingEvents: chronosUpcomingEventsList DOM element not found.");
        return;
    }
    if (!events || !Array.isArray(events) || events.length === 0) {
        DOM.chronosUpcomingEventsList.innerHTML = '<p style="color: #888;">No upcoming special events planned for Pathos in the near future.</p>';
        return;
    }

    let html = '<ul class="chronos-list">';
    events.forEach(event => {
        const title = event.title || "Untitled Event";
        const startDate = event.start_date || "N/A";
        const endDate = event.end_date || "N/A";
        const eventType = event.event_type || "Unknown Type";
        const description = event.description || "";
        const location = event.location || "";
        const activityTheme = event.details && event.details.activity_theme ? event.details.activity_theme : "";
        const plannedSites = event.details && Array.isArray(event.details.planned_sites_or_tasks) ? event.details.planned_sites_or_tasks.join(', ') : "";

        html += `
            <li class="chronos-list-item event-item">
                <div class="chronos-time">${startDate} to ${endDate}</div>
                <div class="chronos-title">${title} <span class="chronos-type">(${eventType})</span></div>
                ${description ? `<div class="chronos-description">${description}</div>` : ''}
                ${location ? `<div class="chronos-location">Location: ${location}</div>` : ''}
                ${activityTheme ? `<div class="chronos-subfocus">Theme: ${activityTheme}</div>` : ''}
                ${plannedSites ? `<div class="chronos-subfocus">Activities/Sites: ${plannedSites}</div>` : ''}
            </li>
        `;
    });
    html += '</ul>';
    DOM.chronosUpcomingEventsList.innerHTML = html;
}

console.log("ui_panels.js loaded (Chronos panel updated).");