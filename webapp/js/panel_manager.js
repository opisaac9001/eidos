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
    if (allPanelConfigurations.length === 0 && !(DOM.dropdownButton && DOM.dropdownContent)) { // Adjusted condition
        console.warn("PanelManager: Panel configurations not initialized and/or dropdown elements missing. Cannot set up all event listeners.");
        // return; // Don't return if only dropdown is present
    }
    console.log("PanelManager: Setting up panel event listeners...");

    allPanelConfigurations.forEach(item => {
        const triggerButton = item.button; 

        if (item.panel && item.button) { 
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

    // --- ADDED/MODIFIED DROPDOWN TOGGLE LOGIC ---
    if (DOM.dropdownButton && DOM.dropdownContent) {
        console.log("PanelManager: Setting up model dropdown toggle listener.");
        DOM.dropdownButton.addEventListener('click', (event) => {
            event.stopPropagation(); // Prevent global click listener from immediately closing it
            const isVisible = DOM.dropdownContent.style.display === 'block';
            DOM.dropdownContent.style.display = isVisible ? 'none' : 'block';
            if (!isVisible) {
                // Optional: Call fetchModels if you want to refresh models every time it opens
                // if (typeof window.fetchModelsApiComms === 'function') window.fetchModelsApiComms();
            }
        });
    } else {
        console.warn("PanelManager: Model dropdown button or content not found. Toggle not set up.");
    }

    // Global click listener to close dropdowns/panels when clicking outside
    document.addEventListener('click', (event) => {
        let clickedInsidePanel = false;
        allPanelConfigurations.forEach(item => {
            if (item.panel && item.panel.contains(event.target)) {
                clickedInsidePanel = true;
            }
        });
        // Close model dropdown if click is outside
        if (DOM.dropdownContent && DOM.dropdownContent.style.display === 'block') {
            if (DOM.dropdownButton && !DOM.dropdownButton.contains(event.target) && !DOM.dropdownContent.contains(event.target)) {
                DOM.dropdownContent.style.display = 'none';
            }
        }
        // Close side panels if click is outside
        if (!clickedInsidePanel) {
            let shouldClose = true;
            // Check if the click was on any of the panel trigger buttons
            allPanelConfigurations.forEach(item => {
                if (item.button && item.button.contains(event.target)) {
                    shouldClose = false; // Don't close if a panel button was clicked (it will toggle)
                }
            });
            if (shouldClose) {
                closeAllSidePanels();
            }
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeAllSidePanels();
            if (DOM.dropdownContent) DOM.dropdownContent.style.display = 'none';
        }
    });
    
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