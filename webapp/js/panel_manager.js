// webapp/js/panel_manager.js

import * as DOM from './dom_elements.js';

const allPanelConfigurations = [];

let _renderHistoryPanelFunc, _fetchLearningsFunc, _fetchDreamsFunc,
    _fetchKnowledgeVerificationsFunc, _fetchDailyBriefingFunc, _fetchUserFactsFunc;

export function initializePanelConfigurations(panelFuncs) {
    allPanelConfigurations.length = 0;
    _renderHistoryPanelFunc = panelFuncs.renderHistoryPanel;
    _fetchLearningsFunc = panelFuncs.fetchLearnings;
    _fetchDreamsFunc = panelFuncs.fetchDreams;
    _fetchKnowledgeVerificationsFunc = panelFuncs.fetchKnowledgeVerifications;
    _fetchDailyBriefingFunc = panelFuncs.fetchDailyBriefing;
    _fetchUserFactsFunc = panelFuncs.fetchUserFacts;

    const panelConfigs = [ // Changed to panelConfigs to avoid confusion
        { id: 'systemPrompt', button: DOM.systemPromptButton, panel: DOM.systemPromptPanel, fetchFunc: null, side: 'right-sliding', closeButton: DOM.systemPromptClose },
        { id: 'history', button: DOM.historyButton, panel: DOM.historyPanel, fetchFunc: _renderHistoryPanelFunc, side: 'left-sliding', closeButton: DOM.historyCloseButton },
        { id: 'proactive', button: DOM.proactiveButton, panel: DOM.proactivePanel, fetchFunc: null, side: 'right-sliding', closeButton: DOM.proactiveCloseButton },
        { id: 'learningLog', button: DOM.learningLogButton, panel: DOM.learningLogPanel, fetchFunc: _fetchLearningsFunc, side: 'right-sliding', closeButton: DOM.learningLogCloseButton },
        { id: 'dreamJournal', button: DOM.dreamJournalButton, panel: DOM.dreamJournalPanel, fetchFunc: _fetchDreamsFunc, side: 'right-sliding', closeButton: DOM.dreamJournalCloseButton },
        { id: 'knowledgeLog', button: DOM.knowledgeLogButton, panel: DOM.knowledgeLogPanel, fetchFunc: _fetchKnowledgeVerificationsFunc, side: 'right-sliding', closeButton: DOM.knowledgeLogCloseButton },
        { id: 'userFacts', button: DOM.userFactsButton, panel: DOM.userFactsPanel, fetchFunc: _fetchUserFactsFunc, side: 'right-sliding', closeButton: DOM.userFactsCloseButton },
        { id: 'dailyBriefing', button: DOM.getDailyBriefingButton, panel: DOM.dailyBriefingPanel, fetchFunc: _fetchDailyBriefingFunc, side: 'right-sliding', isMainButton: true, closeButton: DOM.dailyBriefingCloseButton }
    ];

    panelConfigs.forEach(config => {
        if (config.panel) {
            allPanelConfigurations.push(config);
            console.log(`PanelManager: Added '${config.id}' to configurations. Button: ${config.button?.id}, Panel: ${config.panel.id}, FetchFunc type: ${typeof config.fetchFunc}`);
        } else {
            const buttonId = config.button?.id || (config.isMainButton && config.button?.id) || 'unknown button';
            console.warn(`PanelManager: Panel DOM element for '${config.id}' (button: ${buttonId}) not found. Config skipped.`);
        }
    });
    console.log("PanelManager: Panel configurations initialized. Total configured:", allPanelConfigurations.length);
}

function togglePanel(panelElement, fetchFunction, panelSide) {
    console.log(`PanelManager: togglePanel called for panel ID: ${panelElement?.id}, Fetch func type: ${typeof fetchFunction}, Side: ${panelSide}`);
    if (!panelElement) {
        console.warn("PanelManager: togglePanel called with null panelElement.");
        return;
    }
    const panelWasOpen = panelElement.classList.contains('open');
    closeAllSidePanels(); // Close all other panels first
    if (!panelWasOpen) {
        if (!panelElement.classList.contains(panelSide)) {
            panelElement.classList.add(panelSide); // Ensure the sliding direction class is present
        }
        panelElement.classList.add('open');
        console.log(`PanelManager: Opened panel ${panelElement.id}`);
        if (fetchFunction && typeof fetchFunction === 'function') {
            try {
                console.log(`PanelManager: Calling fetchFunction for ${panelElement.id}`);
                fetchFunction();
            } catch (e) { console.error(`PanelManager: Error in fetchFunction for ${panelElement.id}:`, e); }
        }
        if (panelElement.id === 'system-prompt-panel' && DOM.systemPromptPanel) {
            const firstInput = DOM.systemPromptPanel.querySelector('input[type="text"], textarea');
            if (firstInput) setTimeout(() => firstInput.focus(), 300);
        }
    } else {
        console.log(`PanelManager: Panel ${panelElement.id} was already open, now closed (or re-closed by closeAllSidePanels).`);
    }
}

export function setupPanelEventListeners() {
    if (allPanelConfigurations.length === 0) {
        console.warn("PanelManager: Panel configurations not initialized. Cannot set up panel event listeners.");
        return;
    }
    console.log("PanelManager: Setting up panel event listeners...");

    allPanelConfigurations.forEach(item => {
        // Use item.isMainButton to determine the correct trigger.
        // If item.isMainButton is true, item.button is the actual button element.
        // If item.isMainButton is false or undefined, item.button is also the trigger.
        const triggerButton = item.button; // Simplified: item.button should always be the trigger if defined

        if (item.panel && item.button) { // Ensure both panel and its primary toggle button exist
             console.log(`PanelManager: Attempting to add listener to button: ${item.button.id} for panel: ${item.panel.id}`);
            if (!item.panel.classList.contains(item.side)) {
                item.panel.classList.add(item.side);
            }
            item.button.addEventListener('click', (e) => {
                console.log(`PanelManager: Clicked button: ${item.button.id}, targeting panel: ${item.panel.id}`);
                e.stopPropagation();
                togglePanel(item.panel, item.fetchFunc, item.side);
            });
        } else if (item.panel && item.isMainButton && !item.button) {
            // This case was for when the button in config was null but isMainButton was true.
            // The getDailyBriefingButton is handled in event_handlers.js now to also open the panel.
            // So, this specific branch might not be strictly needed if all panel toggles are header icons.
            console.warn(`PanelManager: Panel ${item.panel.id} configured with isMainButton but no direct button in config. Ensure its trigger is handled elsewhere.`);
        }


        if (item.closeButton && item.panel) {
            item.closeButton.addEventListener('click', (e) => {
                console.log(`PanelManager: Clicked close button for panel: ${item.panel.id}`);
                e.stopPropagation();
                item.panel.classList.remove('open');
            });
        }
    });

    // Global click listener (remains the same)
    document.addEventListener('click', (event) => { /* ... */ });
    document.addEventListener('keydown', (event) => { /* ... */ });
    if (DOM.dropdownButton && DOM.dropdownContent) { /* ... */ }

    console.log("PanelManager: Panel event listeners setup complete.");
}

export function closeAllSidePanels() {
    if (Array.isArray(allPanelConfigurations)) {
        allPanelConfigurations.forEach(item => {
            if (item.panel && item.panel.classList.contains('open')) {
                item.panel.classList.remove('open');
            }
        });
    }
    console.log('PanelManager: All side panels closed.');
}

console.log("panel_manager.js loaded.");