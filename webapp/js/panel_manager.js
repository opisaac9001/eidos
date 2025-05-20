// webapp/js/panel_manager.js

import * as DOM from './dom_elements.js';

const allPanelConfigurations = []; 

let _renderHistoryPanelFunc, _fetchLearningsFunc, _fetchDreamsFunc, 
    _fetchKnowledgeVerificationsFunc, _fetchDailyBriefingFunc;

export function initializePanelConfigurations(panelFuncs) {
    allPanelConfigurations.length = 0; 
    _renderHistoryPanelFunc = panelFuncs.renderHistoryPanel;
    _fetchLearningsFunc = panelFuncs.fetchLearnings;
    _fetchDreamsFunc = panelFuncs.fetchDreams;
    _fetchKnowledgeVerificationsFunc = panelFuncs.fetchKnowledgeVerifications;
    _fetchDailyBriefingFunc = panelFuncs.fetchDailyBriefing;

    // Ensure all DOM elements are valid before pushing
    const panels = [
        { button: DOM.systemPromptButton, panel: DOM.systemPromptPanel, fetchFunc: null, side: 'right-sliding', closeButton: DOM.systemPromptClose },
        { button: DOM.historyButton, panel: DOM.historyPanel, fetchFunc: _renderHistoryPanelFunc, side: 'left-sliding', closeButton: DOM.historyCloseButton },
        { button: DOM.proactiveButton, panel: DOM.proactivePanel, fetchFunc: null, side: 'right-sliding', closeButton: DOM.proactiveCloseButton },
        { button: DOM.learningLogButton, panel: DOM.learningLogPanel, fetchFunc: _fetchLearningsFunc, side: 'right-sliding', closeButton: DOM.learningLogCloseButton },
        { button: DOM.dreamJournalButton, panel: DOM.dreamJournalPanel, fetchFunc: _fetchDreamsFunc, side: 'right-sliding', closeButton: DOM.dreamJournalCloseButton },
        { button: DOM.knowledgeLogButton, panel: DOM.knowledgeLogPanel, fetchFunc: _fetchKnowledgeVerificationsFunc, side: 'right-sliding', closeButton: DOM.knowledgeLogCloseButton },
        // Special case for daily briefing button if it's different from the panel toggle
        { button: DOM.getDailyBriefingButton, panel: DOM.dailyBriefingPanel, fetchFunc: _fetchDailyBriefingFunc, side: 'right-sliding', isMainButton: true, closeButton: DOM.dailyBriefingCloseButton }
    ];

    panels.forEach(p => {
        if (p.panel) { // Only add if the panel element exists
            allPanelConfigurations.push(p);
        } else {
            console.warn(`Panel element for button ${p.button?.id || p.isMainButton?.id} not found in DOM. Panel config skipped.`);
        }
    });
    
    console.log("Panel configurations initialized with fetch functions. Count:", allPanelConfigurations.length);
}

function togglePanel(panelElement, fetchFunction, panelSide) {
    if (!panelElement) {
        console.warn("togglePanel called with null panelElement.");
        return;
    }
    const panelWasOpen = panelElement.classList.contains('open');
    closeAllSidePanels(); 
    if (!panelWasOpen) {
        // panelElement.classList.add(panelSide); // Side class should already be on the element from setupPanelEventListeners
        panelElement.classList.add('open');
        if (fetchFunction && typeof fetchFunction === 'function') {
            try { fetchFunction(); } catch (e) { console.error("Error in panel fetchFunction:", e); }
        }
        if (panelElement.id === 'system-prompt-panel' && DOM.systemPromptPanel) {
            const firstInput = DOM.systemPromptPanel.querySelector('input[type="text"], textarea');
            if (firstInput) setTimeout(() => firstInput.focus(), 300);
        }
    }
}

export function setupPanelEventListeners() {
    if (allPanelConfigurations.length === 0) {
        console.warn("Panel configurations not initialized. Cannot set up panel event listeners.");
        // Attempt to initialize if DOM elements are ready (e.g. if main.js calls this too early)
        // This is a bit of a hack; ideally, main.js ensures order.
        if (DOM.systemPromptButton) { // Check if DOM is likely ready
             console.warn("Attempting to re-initialize panel configurations in setupPanelEventListeners.");
             // This requires panelFuncs to be available globally or passed differently.
             // For now, this re-init won't work perfectly without panelFuncs.
             // initializePanelConfigurations({}); // This would fail without functions
        } else {
            return;
        }
    }

    allPanelConfigurations.forEach(item => {
        const trigger = item.isMainButton ? item.button : item.button; // Corrected: isMainButton is the button itself
        if (item.isMainButton && !trigger) { // If isMainButton was true but button was null
            console.warn(`Panel config for ${item.panel.id} has isMainButton but no button assigned.`);
            return;
        }

        if (trigger && item.panel) {
            if (!item.panel.classList.contains(item.side)) { // Ensure side class is present
                item.panel.classList.add(item.side);
            }
            trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                togglePanel(item.panel, item.fetchFunc, item.side);
            });
        } else if (!trigger && item.panel.id === 'daily-briefing-panel' && DOM.getDailyBriefingButton) {
            // Special handling for daily briefing if its trigger is DOM.getDailyBriefingButton
            // This assumes DOM.getDailyBriefingButton is the trigger for dailyBriefingPanel
            DOM.getDailyBriefingButton.addEventListener('click', (e) => {
                e.stopPropagation();
                togglePanel(DOM.dailyBriefingPanel, _fetchDailyBriefingFunc, 'right-sliding');
            });
        }


        if (item.closeButton && item.panel) {
            item.closeButton.addEventListener('click', (e) => {
                e.stopPropagation();
                item.panel.classList.remove('open');
            });
        }
    });

    document.addEventListener('click', (event) => {
        const allPanels = allPanelConfigurations.map(item => item.panel).filter(Boolean);
        const allTriggers = allPanelConfigurations.map(item => item.isMainButton ? item.button : item.button).filter(Boolean);
        
        const clickedTrigger = allTriggers.some(b => b?.contains(event.target));
        const clickedPanel = allPanels.some(p => p?.classList.contains('open') && p.contains(event.target));

        if (!clickedTrigger && !clickedPanel) closeAllSidePanels();

        if (DOM.dropdownButton && DOM.dropdownContent?.style.display === 'block') {
            if (!DOM.dropdownButton.contains(event.target) && !DOM.dropdownContent.contains(event.target)) {
                DOM.dropdownContent.style.display = 'none';
            }
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeAllSidePanels();
            if (DOM.dropdownContent) DOM.dropdownContent.style.display = 'none';
        }
    });

    if (DOM.dropdownButton && DOM.dropdownContent) {
        DOM.dropdownButton.addEventListener('click', function (event) {
            event.stopPropagation();
            const isOpen = DOM.dropdownContent.style.display === 'block';
            // closeAllSidePanels(); // Closing all panels on dropdown click might be too aggressive
            DOM.dropdownContent.style.display = isOpen ? 'none' : 'block';
        });
    }
    console.log("Panel event listeners set up.");
}

export function closeAllSidePanels() {
    // This function should only use classList.remove('open')
    if (Array.isArray(allPanelConfigurations)) {
        allPanelConfigurations.forEach(item => {
            if (item.panel && item.panel.classList.contains('open')) {
                item.panel.classList.remove('open');
            }
        });
    }
    // Also hide the weather panel if it's managed separately and uses display:none
    if (DOM.weatherPanel && DOM.weatherPanel.style.display !== 'none') {
        // DOM.weatherPanel.style.display = 'none'; // Only if it's not part of allPanelConfigurations
    }
    console.log('All side panels closed via class removal.');
}

console.log("panel_manager.js loaded.");