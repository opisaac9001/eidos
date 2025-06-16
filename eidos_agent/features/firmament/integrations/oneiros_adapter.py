# eidos_agent/features/firmament/integrations/oneiros_adapter.py

# This module serves as an adapter to interface with the Oneiros dream generation module.
# It will be responsible for triggering dream generation based on context (e.g., recent
# memories, current mood) and retrieving the generated dream content.

import random

class OneirosAdapter:
    def __init__(self, oneiros_config: dict = None):
        """
        Initializes the OneirosAdapter.
        In a real implementation, this might load dream generation models or
        connect to an Oneiros service.

        Args:
            oneiros_config (dict, optional): Configuration for the Oneiros module.
                                             Defaults to None.
        """
        self.config = oneiros_config if oneiros_config else {}
        self.model_loaded = False
        self._initialize_oneiros_engine()
        print(f"OneirosAdapter initialized. Model Loaded: {self.model_loaded}. Config: {self.config}")

    def _initialize_oneiros_engine(self):
        """
        Placeholder for loading dream generation models or setting up the engine.
        """
        if self.config.get("model_path") or self.config.get("use_default_model", True):
            print(f"OneirosAdapter: Initializing Oneiros engine with config: {self.config} (simulated)")
            # Simulate successful model loading
            self.model_loaded = True
        else:
            print("OneirosAdapter: No model configuration. Dream generation will be very basic.")
            self.model_loaded = False
        return self.model_loaded

    def generate_dream(self, context: dict = None) -> str:
        """
        Simulates generating a dream narrative via the Oneiros module.

        Args:
            context (dict, optional): Contextual information that might influence
                                      dream generation. This could include keys like
                                      'recent_memories' (list of strings/objects),
                                      'current_mood' (string or dict),
                                      'significant_events' (list). Defaults to None.

        Returns:
            str: The generated dream content as a string narrative.
        """
        print(f"OneirosAdapter: generate_dream() called. Context provided: {bool(context)}")
        if context:
            print(f"  Context details: {str(context)[:200]}{'...' if len(str(context)) > 200 else ''}")


        if not self.model_loaded and not self.config.get("allow_basic_fallback", True):
            return "Dream generation engine not available."

        # Simplified placeholder logic for dream generation
        dream_themes = ["flying", "being chased", "falling", "discovery", "solving puzzles", "meeting mysterious figures"]
        dream_settings = ["a surreal landscape", "a familiar place behaving strangely", "a futuristic city", "a dark forest", "underwater"]

        chosen_theme = random.choice(dream_themes)
        chosen_setting = random.choice(dream_settings)
        dream_content = f"Pathos dreamt of {chosen_theme} in {chosen_setting}."

        # Incorporate context in a very basic way for placeholder
        if context:
            if "recent_memories" in context and context["recent_memories"]:
                # Example: pick a keyword from a recent memory
                first_memory_content = str(context["recent_memories"][0]) # Assuming memories are strings or have str representation
                keywords = first_memory_content.split()
                if keywords:
                    dream_content += f" It seemed related to '{random.choice(keywords)}'."

            if context.get("current_mood") == "anxious":
                dream_content += " The dream had an unsettling and anxious atmosphere."
            elif context.get("current_mood") == "joyful":
                dream_content += " The dream felt joyful and liberating."

            if context.get("significant_events"):
                event_summary = str(context["significant_events"][0]) # Take the first one for simplicity
                dream_content += f" Elements of '{event_summary[:30]}{'...' if len(event_summary)>30 else ''}' were present."

        # Fallback example from prompt if specific context keys match
        if context and context.get("recent_event") == "mail_delivery":
            dream_content = "Pathos dreamt of receiving an endless stream of packages, each one larger than the last. Some packages whispered secrets."
        elif context and context.get("mood") == "confused": # Note: prompt used "mood", I used "current_mood" above
            dream_content = "Pathos had a confusing dream about solving a riddle in a house with shifting rooms and staircases that led nowhere."

        print(f"OneirosAdapter: Dream generated (simulated): \"{dream_content[:100]}{'...' if len(dream_content) > 100 else ''}\"")
        return dream_content

    # Placeholder for other Oneiros interactions
    # def analyze_dream_sentiment(dream_content: str) -> dict:
    #     """ Analyzes a dream narrative for emotional content. """
    #     pass

if __name__ == '__main__':
    print("--- Testing OneirosAdapter ---")

    print("\n1. Initializing with default configuration:")
    oneiros_adapter = OneirosAdapter()

    print("\n2. Generating a default dream (no context):")
    dream1 = oneiros_adapter.generate_dream()
    print(f"   Dream 1: {dream1}")

    print("\n3. Generating a dream with specific context (recent event 'mail_delivery'):")
    context_event = {"recent_event": "mail_delivery", "current_mood": "anxious"}
    dream2 = oneiros_adapter.generate_dream(context=context_event)
    print(f"   Dream 2: {dream2}")

    print("\n4. Generating a dream with specific context (mood 'confused'):")
    context_mood = {"mood": "confused", "recent_memories": ["The world feels upside down today."]}
    dream3 = oneiros_adapter.generate_dream(context=context_mood)
    print(f"   Dream 3: {dream3}")

    print("\n5. Generating a dream with more detailed context:")
    detailed_context = {
        "recent_memories": [
            "Saw a strange car earlier.",
            "Read a book about ancient civilizations."
        ],
        "current_mood": "curious",
        "significant_events": ["Received an unexpected gift."]
    }
    dream4 = oneiros_adapter.generate_dream(context=detailed_context)
    print(f"   Dream 4: {dream4}")

    print("\n6. Initializing with specific model config (simulated):")
    model_config = {"model_path": "/models/oneiros/dream_model_v2.pkl", "use_default_model": False}
    oneiros_adapter_custom = OneirosAdapter(oneiros_config=model_config)
    dream5 = oneiros_adapter_custom.generate_dream(context={"current_mood": "peaceful"})
    print(f"   Dream 5 (custom config): {dream5}")

    print("\n--- OneirosAdapter testing finished ---")
