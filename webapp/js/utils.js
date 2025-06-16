// webapp/js/utils.js

import { THINK_TAG_PLACEHOLDER_PREFIX, THINK_TAG_PLACEHOLDER_SUFFIX } from './config.js';
// We need marked and Prism from global scope if they are loaded via CDN,
// or we would import them if they were JS modules.
// For now, assume global `marked` and `Prism` exist.

/**
 * Scrolls the main chat messages area to the bottom.
 */
export function scrollToBottom(chatArea) {
    if (chatArea) {
        chatArea.scrollTop = chatArea.scrollHeight;
    }
}

/**
 * Displays a temporary toast-like notification on the screen.
 * @param {string} message - The message to display.
 * @param {'info' | 'success' | 'error' | 'warning'} type - The type of notification, affects styling.
 */
export function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.textContent = message;
    notification.style.position = 'fixed';
    notification.style.bottom = '20px';
    notification.style.right = '20px';
    notification.style.padding = '10px 16px';
    notification.style.borderRadius = '4px';
    notification.style.color = 'white';
    notification.style.opacity = '0';
    notification.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
    notification.style.transform = 'translateY(20px)';
    notification.style.zIndex = '2000'; // Ensure it's above most other elements

    switch (type) {
        case 'success':
            notification.style.backgroundColor = '#4CAF50'; // Green
            break;
        case 'error':
            notification.style.backgroundColor = '#F44336'; // Red
            break;
        case 'warning':
            notification.style.backgroundColor = '#FF9800'; // Orange
            break;
        case 'info':
        default:
            notification.style.backgroundColor = '#F97B65'; // Eidos Orange (or a neutral blue like #2196F3)
            break;
    }

    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.style.opacity = '1';
        notification.style.transform = 'translateY(0)';
    }, 10);

    // Animate out and remove
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateY(20px)';
        setTimeout(() => {
            if (document.body.contains(notification)) {
                document.body.removeChild(notification);
            }
        }, 300);
    }, 3500); // Notification visible for 3.5 seconds
}

/**
 * Replaces <think>...</think> tags with placeholders for later HTML rendering.
 * @param {string} markdown - The input Markdown string.
 * @returns {{processedMarkdown: string, thinkBlocks: Array<Object>}}
 */
export function processThinkTagsInMarkdown(markdown) {
    if (typeof markdown !== 'string') return { processedMarkdown: String(markdown), thinkBlocks: [] };
    const thinkBlocks = [];
    let blockIdCounter = 0;
    const processedMarkdown = markdown.replace(/<think>([\s\S]*?)<\/think>/g, (match, thinkContent) => {
        const currentId = blockIdCounter++;
        thinkBlocks.push({ id: `think-${Date.now()}-${currentId}`, rawContent: thinkContent.trim() });
        return `${THINK_TAG_PLACEHOLDER_PREFIX}${thinkBlocks[thinkBlocks.length - 1].id}${THINK_TAG_PLACEHOLDER_SUFFIX}`;
    });
    return { processedMarkdown, thinkBlocks };
}

/**
 * Renders the actual HTML for think blocks where placeholders were inserted.
 * @param {HTMLElement} contentDiv - The div containing the HTML from processedMarkdown.
 * @param {Array<Object>} thinkBlocks - The array of think blocks from processThinkTagsInMarkdown.
 */
export function renderThinkBlocksHTML(contentDiv, thinkBlocks) {
    if (!contentDiv || !thinkBlocks || thinkBlocks.length === 0) return;

    let html = contentDiv.innerHTML;
    thinkBlocks.forEach(block => {
        const placeholder = `${THINK_TAG_PLACEHOLDER_PREFIX}${block.id}${THINK_TAG_PLACEHOLDER_SUFFIX}`;
        // Ensure rawContent is parsed as Markdown for display within the think block
        const thinkBlockInnerHtml = (typeof marked !== 'undefined') ? marked.parse(block.rawContent) : `<pre>${block.rawContent}</pre>`;
        
        const thinkSectionHtml = `
            <div class="collapsible-think-section">
                <div class="think-header" data-think-block-id="${block.id}">
                    <span>AI Thoughts</span> <span class="toggle-icon">[+]</span>
                </div>
                <div class="think-content" id="think-content-${block.id}" style="display:none;">
                    ${thinkBlockInnerHtml}
                </div>
            </div>`;
        
        // Use a more robust way to replace placeholders if they might contain special regex characters
        // However, our placeholders are simple enough for direct string replace.
        // For safety, one might escape the placeholder before creating a RegExp.
        const placeholderRegExp = new RegExp(RegExp.escape(placeholder), 'g');
        html = html.replace(placeholderRegExp, thinkSectionHtml);
    });
    contentDiv.innerHTML = html;
}

/**
 * Adds click listeners to think block headers to toggle content visibility.
 * @param {HTMLElement} parentElement - The element containing the think blocks (e.g., a message bubble).
 */
export function addThinkBlockListeners(parentElement) {
    if (!parentElement) return;

    parentElement.querySelectorAll('.think-header').forEach(header => {
        // Prevent adding multiple listeners if this function is called again on the same element
        if (header.dataset.listenerAttached === 'true') return;

        header.addEventListener('click', () => {
            const blockId = header.dataset.thinkBlockId;
            const thinkContentElement = parentElement.querySelector(`#think-content-${blockId}`);
            const toggleIcon = header.querySelector('.toggle-icon');

            if (thinkContentElement) {
                const isHidden = thinkContentElement.style.display === 'none';
                thinkContentElement.style.display = isHidden ? 'block' : 'none';
                if (toggleIcon) toggleIcon.textContent = isHidden ? '[-]' : '[+]';

                // Highlight content when it becomes visible
                if (isHidden && typeof Prism !== 'undefined') {
                    Prism.highlightAllUnder(thinkContentElement);
                }
                // Typeset MathJax if present and visible
                if (isHidden && typeof MathJax !== 'undefined' && MathJax.typesetPromise) {
                     MathJax.typesetPromise([thinkContentElement]).catch(err => console.warn("MathJax (think block):", err));
                }
            }
        });
        header.dataset.listenerAttached = 'true'; // Mark as listener attached
    });
}

/**
 * Auto-adjusts the height of a textarea based on its content.
 * @param {HTMLTextAreaElement} textareaElement - The textarea to adjust.
 */
export function autoAdjustTextareaHeight(textareaElement) {
    if (!textareaElement) return;
    textareaElement.style.height = 'auto'; // Temporarily shrink to get correct scrollHeight
    let scrollHeight = textareaElement.scrollHeight;
    const maxHeight = parseInt(window.getComputedStyle(textareaElement).maxHeight, 10) || 120; // Default max height if not set in CSS

    if (scrollHeight > maxHeight) {
        textareaElement.style.height = maxHeight + 'px';
        textareaElement.style.overflowY = 'auto'; 
    } else {
        textareaElement.style.height = scrollHeight + 'px';
        textareaElement.style.overflowY = 'hidden'; 
    }
}

/**
 * Polyfill for RegExp.escape if it doesn't exist (useful for robust placeholder replacement).
 */
if (!RegExp.escape) {
    RegExp.escape = function(string) {
        return string.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
    };
}

console.log("utils.js loaded.");