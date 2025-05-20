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
    userFactsContentArea, // New
    historyPanel
} from './dom_elements.js';
import { showNotification } from './utils.js';
import { loadChatFromHistory } from './persistent_storage.js';

// --- History Panel Functions ---
export function renderHistoryPanel() {
    if (!historyContentArea) {
        console.error("History content area element not found.");
        return;
    }
    const histories = JSON.parse(localStorage.getItem('eidosChatHistoryArchive')) || [];
    historyContentArea.innerHTML = '';

    if (histories.length === 0) {
        historyContentArea.innerHTML = '<p style="color: #888;">No archived chats yet. Chats are archived when you start a new chat or load another.</p>';
        return;
    }

    histories.forEach((entry, index) => {
        const itemDiv = document.createElement('div');
        itemDiv.classList.add('history-item');
        itemDiv.dataset.historyIndex = index;

        const dateDiv = document.createElement('div');
        dateDiv.classList.add('history-item-date');
        dateDiv.textContent = new Date(entry.timestamp).toLocaleString();

        const titleDiv = document.createElement('div');
        let titleText = "Chat Entry";
        if (entry.title) { titleText = entry.title; }
        else { /* ... logic to derive title from first user message ... */ }
        titleDiv.textContent = titleText;

        itemDiv.appendChild(dateDiv);
        itemDiv.appendChild(titleDiv);

        itemDiv.addEventListener('click', () => {
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
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    const currentUserIdForFetch = window.currentUserId;

    if (!currentApiBaseUrl) { /* ... error handling ... */ return; }
    try {
        const response = await fetch(`${currentApiBaseUrl}/agent/learnings?limit=${DEFAULT_LOG_FETCH_LIMIT}`, {
            method: 'GET',
            headers: { 'X-User-Id': currentUserIdForFetch }
        });
        if (!response.ok) { /* ... error handling ... */ throw new Error(`Failed: ${response.status}`); }
        const learnings = await response.json();
        learningLogContentArea.innerHTML = '';
        if (learnings && learnings.length > 0) {
            learnings.forEach(learning => { /* ... render learning item ... */
                const itemDiv = document.createElement('div'); itemDiv.classList.add('history-item');
                const dateDiv = document.createElement('div'); dateDiv.classList.add('history-item-date'); dateDiv.textContent = `Learned: ${new Date(learning.timestamp).toLocaleString()}`; itemDiv.appendChild(dateDiv);
                const typeDiv = document.createElement('div'); typeDiv.style.fontWeight = 'bold'; typeDiv.style.color = '#F97B65'; typeDiv.textContent = `Type: ${learning.type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}`; itemDiv.appendChild(typeDiv);
                const contentDiv = document.createElement('div'); contentDiv.style.marginTop = '5px';
                if (typeof marked !== 'undefined') contentDiv.innerHTML = marked.parse(learning.content || "[No content]"); else contentDiv.textContent = learning.content || "[No content]";
                itemDiv.appendChild(contentDiv);
                // ... (metadata display if any) ...
                learningLogContentArea.appendChild(itemDiv);
            });
        } else { /* ... no learnings message ... */ }
    } catch (error) { /* ... error handling ... */ }
}

// --- Dream Journal Panel Functions ---
export async function fetchAndDisplayDreams() {
    if (!dreamJournalContentArea) return;
    dreamJournalContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching dreams...</p>';
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    const currentUserIdForFetch = window.currentUserId;
    if (!currentApiBaseUrl) { /* ... error handling ... */ return; }
    try {
        const response = await fetch(`${currentApiBaseUrl}/agent/dreams?limit=${DEFAULT_LOG_FETCH_LIMIT}`, {
            method: 'GET',
            headers: { 'X-User-Id': currentUserIdForFetch }
        });
        if (!response.ok) { /* ... error handling ... */ throw new Error(`Failed: ${response.status}`); }
        const dreams = await response.json();
        dreamJournalContentArea.innerHTML = '';
        if (dreams && dreams.length > 0) {
            dreams.forEach(dream => { /* ... render dream item with image ... */
                const itemDiv = document.createElement('div'); itemDiv.classList.add('dream-journal-item');
                const dateDiv = document.createElement('div'); dateDiv.classList.add('dream-timestamp'); dateDiv.textContent = `Dreamed: ${new Date(dream.timestamp).toLocaleString()}`; itemDiv.appendChild(dateDiv);
                const contentDiv = document.createElement('div'); contentDiv.classList.add('dream-content');
                if (typeof marked !== 'undefined') contentDiv.innerHTML = marked.parse(dream.content || "[No textual dream content]"); else contentDiv.textContent = dream.content || "[No textual dream content]";
                itemDiv.appendChild(contentDiv);
                if (dream.dream_image_url) { /* ... add image ... */ }
                if (dream.dream_seed_summary) { /* ... add seed summary ... */ }
                dreamJournalContentArea.appendChild(itemDiv);
            });
        } else { /* ... no dreams message ... */ }
    } catch (error) { /* ... error handling ... */ }
}

// --- Knowledge Upkeep Log Panel Functions ---
export async function fetchAndDisplayKnowledgeVerifications() {
    if (!knowledgeLogContentArea) return;
    knowledgeLogContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching knowledge upkeep log...</p>';
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    const currentUserIdForFetch = window.currentUserId;
    if (!currentApiBaseUrl) { /* ... error handling ... */ return; }
    try {
        const response = await fetch(`${currentApiBaseUrl}/agent/knowledge_verifications?limit=${DEFAULT_LOG_FETCH_LIMIT}`, {
            method: 'GET',
            headers: { 'X-User-Id': currentUserIdForFetch }
        });
        if (!response.ok) { /* ... error handling ... */ throw new Error(`Failed: ${response.status}`); }
        const verifications = await response.json();
        knowledgeLogContentArea.innerHTML = '';
        if (verifications && verifications.length > 0) {
            verifications.forEach(verification => { /* ... render verification item ... */
                const itemDiv = document.createElement('div'); itemDiv.classList.add('knowledge-log-item');
                // ... (logic to display timestamp, fact, status, new_statement, reasoning) ...
                // ... (set itemDiv.style.borderLeftColor based on status) ...
                knowledgeLogContentArea.appendChild(itemDiv);
            });
        } else { /* ... no verifications message ... */ }
    } catch (error) { /* ... error handling ... */ }
}

// --- Daily Briefing Panel Functions ---
export async function fetchAndDisplayDailyBriefingGUI() {
    if (!dailyBriefingContentArea) return;
    dailyBriefingContentArea.innerHTML = '<p style="color: #BBBBBB;">Fetching briefing...</p>';
    const currentApiBaseUrl = window.EIDOS_API_BASE_URL || EIDOS_API_BASE_URL;
    const currentUserIdForFetch = window.currentUserId;
    if (!currentApiBaseUrl) { /* ... error handling ... */ return; }
    try {
        const response = await fetch(`${currentApiBaseUrl}/briefing`, {
            method: 'GET',
            headers: { 'X-User-Id': currentUserIdForFetch }
        });
        if (!response.ok) { /* ... error handling ... */ throw new Error(`Failed: ${response.status}`); }
        const result = await response.json();
        if (result.success && result.briefing_content) {
            if (typeof marked !== 'undefined') dailyBriefingContentArea.innerHTML = marked.parse(result.briefing_content);
            else dailyBriefingContentArea.textContent = result.briefing_content;
            if (typeof Prism !== 'undefined') Prism.highlightAllUnder(dailyBriefingContentArea);
            if (typeof MathJax !== 'undefined' && MathJax.typesetPromise) MathJax.typesetPromise([dailyBriefingContentArea]).catch(err => console.warn("MathJax (briefing):", err));
        } else { /* ... handle no briefing or error message from API ... */ }
    } catch (error) { /* ... error handling ... */ }
}

// --- "Facts About You" Panel Functions ---
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
    if (!currentUserIdForFetch || currentUserIdForFetch === "unknown_user" || currentUserIdForFetch === "api_guest_user" || currentUserIdForFetch === "default_user") {
        userFactsContentArea.innerHTML = '<p style="color: #888;">Please set a specific User ID in Settings to see your personalized facts.</p>';
        return;
    }

    try {
        const response = await fetch(`${currentApiBaseUrl}/user/facts`, { // Corrected endpoint
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
                li.classList.add('history-item'); // Reuse style
                li.dataset.memoryId = factEntry.id;

                let factAttribute = "Unknown Attribute";
                let factValue = "Unknown Value";
                let originalStatement = "";

                try {
                    const contentData = JSON.parse(factEntry.content);
                    factAttribute = contentData.attribute || factAttribute;
                    factValue = contentData.value || factValue;
                    originalStatement = contentData.original_user_statement || "";
                } catch (e) {
                    console.warn("Could not parse user_fact content JSON:", factEntry.content, e);
                    factValue = factEntry.content;
                }

                const presentableAttribute = factAttribute.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

                const factDisplay = document.createElement('div');
                factDisplay.innerHTML = `<strong>${presentableAttribute}:</strong> ${factValue}`;
                
                if (originalStatement) {
                    const contextDiv = document.createElement('div');
                    contextDiv.style.fontSize = '0.8em';
                    contextDiv.style.color = '#AAAAAA';
                    contextDiv.style.marginTop = '4px';
                    contextDiv.style.fontStyle = 'italic';
                    contextDiv.textContent = `(From: "${originalStatement.substring(0, 70)}${originalStatement.length > 70 ? '...' : ''}")`;
                    factDisplay.appendChild(contextDiv);
                }
                li.appendChild(factDisplay);
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

console.log("ui_panels.js loaded.");