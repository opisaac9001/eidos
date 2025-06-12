// webapp/js/stt.js

import { 
    microphoneButton, 
    userInput 
} from './dom_elements.js';
import { 
    showNotification, 
    autoAdjustTextareaHeight 
} from './utils.js';
// isAwaitingResponse will be managed in main.js and accessed via window or passed if needed
// For now, assume window.isAwaitingResponse exists if needed by toggleListening

// State variables specific to STT
let speechRecognition = null;
let isListening = false;

/**
 * Initializes the SpeechRecognition API.
 * @returns {SpeechRecognition | null} The SpeechRecognition instance or null if not supported.
 */
export function initializeSpeechRecognition() {
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    
    if (!SpeechRecognitionAPI) {
        console.warn("Web Speech API not supported by this browser.");
        if (microphoneButton) {
            microphoneButton.disabled = true;
            microphoneButton.title = "Voice input not supported by this browser";
        }
        return null;
    }

    const recognition = new SpeechRecognitionAPI();
    recognition.continuous = false;      // True means it keeps listening after a pause
    recognition.interimResults = true;   // Get results as they are being processed
    recognition.lang = 'en-US';          // Set language

    recognition.onstart = () => {
        isListening = true;
        if (microphoneButton) microphoneButton.classList.add('listening');
        console.log("Speech recognition started.");
    };

    recognition.onresult = (event) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
        }

        // Display interim results in the input field for better UX, but only append final
        if (userInput) {
            // A possible UX: show interim in placeholder or a temporary spot
            // For now, let's just focus on final transcript for simplicity in this module
            // userInput.placeholder = interimTranscript || "Listening..."; 

            if (finalTranscript) {
                const currentText = userInput.value.trim();
                userInput.value = (currentText ? currentText + ' ' : '') + finalTranscript.trim();
                userInput.focus();
                autoAdjustTextareaHeight(userInput);
                // userInput.placeholder = "How can I help you today?"; // Reset placeholder
            }
        }
    };

    recognition.onerror = (event) => {
        console.error("Speech recognition error:", event.error);
        let errorMessage = `Speech recognition error: ${event.error}`;
        if (event.error === 'no-speech') {
            errorMessage = 'No speech detected. Please try again.';
        } else if (event.error === 'audio-capture') {
            errorMessage = 'Microphone problem. Please check your microphone.';
        } else if (event.error === 'not-allowed') {
            errorMessage = 'Microphone access denied. Please allow microphone access in browser settings.';
        }
        showNotification(errorMessage, "error");
        stopListening(); // Ensure listening state is reset
    };

    recognition.onend = () => {
        stopListening(); // Ensure UI and state are reset
        console.log("Speech recognition ended.");
        // if (userInput) userInput.placeholder = "How can I help you today?"; // Reset placeholder
    };
    
    speechRecognition = recognition; // Store the instance
    console.log("SpeechRecognition initialized.");
    return recognition;
}

/**
 * Toggles the listening state of speech recognition.
 */
export function toggleListening() {
    if (!speechRecognition) {
        showNotification("Voice input is not available or not initialized in this browser.", "warning");
        return;
    }
    // Accessing isAwaitingResponse: assuming it's made available globally by main.js
    // e.g., window.isAwaitingResponse
    if (window.isAwaitingResponse) {
        showNotification("Cannot start voice input while Eidos is responding.", "info");
        return;
    }

    if (isListening) {
        speechRecognition.stop();
        // onend will call stopListening() to update UI
    } else {
        try {
            if (userInput) userInput.value = ""; // Clear input field before starting new STT
            speechRecognition.start();
        } catch (e) {
            // This can happen if recognition is already starting or in an error state
            console.error("Error starting speech recognition:", e);
            showNotification("Could not start voice input. Please try again or check permissions.", "error");
            stopListening(); // Reset state
        }
    }
}

/**
 * Stops speech recognition and updates UI.
 * This is typically called by recognition.onend or recognition.onerror.
 */
export function stopListening() {
    isListening = false;
    if (microphoneButton) {
        microphoneButton.classList.remove('listening');
    }
    // It's good practice to ensure abort is called if recognition might be in an active state
    // and stop() wasn't called or didn't complete.
    if (speechRecognition && (speechRecognition.recognizing || speechRecognition.readyState === 1)) { // Check if actually running
         try {
             speechRecognition.abort();
             console.log("Speech recognition aborted by stopListening.");
         } catch(e) {
             console.warn("Error aborting speech recognition in stopListening:", e);
         }
    }
    // if (userInput) userInput.placeholder = "How can I help you today?"; // Reset placeholder
}

console.log("stt.js loaded.");