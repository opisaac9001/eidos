# eidos_agent/features/firmament/npcs/subconscious_reference_parser.py
import logging
import re
from typing import List, Tuple, Set, Pattern

logger = logging.getLogger(__name__)

# A very basic list of common English words that are often capitalized but aren't typically names.
# This list is far from exhaustive and primarily for the initial heuristic.
# It should be expanded or replaced by more robust NER or context-aware filtering.
COMMON_CAPITALIZED_WORDS: Set[str] = {
    "I", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    "Dr", "Mr", "Mrs", "Ms", "Prof", "Rev", "St", # Titles
    "The", "A", "An", "Is", "Was", "Were", "Will", "Do", "Does", "Did",
    "But", "Or", "So", "If", "Then", "Else", "Not", "And", "For", "Nor",
    "He", "She", "It", "They", "We", "You", "My", "His", "Her", "Its", "Our", "Their",
    "Who", "What", "When", "Where", "Why", "How",
    "Street", "Road", "Avenue", "Lane", "Drive", "Park", "City", "County", "State", # Common address parts
    "Inc", "Ltd", "Corp", "Co" # Company suffixes
}
# A small list of common first names to give the heuristic a bit more power initially.
# This would ideally be replaced or augmented by a proper NER system or a larger name dataset.
EXAMPLE_FIRST_NAMES: Set[str] = {
    "Alex", "Alice", "Bob", "Charlie", "David", "Eve", "Frank", "Grace", "Henry", "Ivy",
    "Jack", "Kate", "Liam", "Lara", "Mia", "Noah", "Olivia", "Owen", "Paul", "Quinn",
    "Ryan", "Sarah", "Tom", "Uma", "Victor", "Wendy", "Xavier", "Yara", "Zoe", "Jane",
    "John", "Mary", "James", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "William", "Elizabeth"
}

# Precompile regex for finding capitalized words for slight efficiency.
# This regex finds words starting with an uppercase letter, possibly followed by lowercase letters, apostrophes, or hyphens.
# It specifically looks for words that are typically name-like.
# Word boundary `\b` is used to ensure we match whole words.
CAPITALIZED_WORD_REGEX: Pattern[str] = re.compile(r"[A-Z][a-zA-Z'-]*")


def _heuristic_detect_names(thought: str) -> Set[str]:
    """
    Detects potential names in a thought string using simple heuristics.
    - Looks for capitalized words using a regex.
    - Cleans possessives (e.g., "Lara's" -> "Lara").
    - Prioritizes words found in a predefined list of common first names (EXAMPLE_FIRST_NAMES).
    - Excludes words found in a predefined list of common capitalized words (COMMON_CAPITALIZED_WORDS).
    - For other capitalized words not in common lists, they are considered potential names.

    This is a basic heuristic and prone to false positives/negatives.
    TODO: Replace this with a proper NER (Named Entity Recognition) system.
    """
    if not thought or not isinstance(thought, str):
        return set()

    potential_names: Set[str] = set()

    # Find all words matching the capitalized word pattern
    # Using a set to avoid processing duplicates from regex if word appears multiple times identically
    found_capitalized_words = set(CAPITALIZED_WORD_REGEX.findall(thought))

    for word in found_capitalized_words:
        # Clean possessives like "Lara's" -> "Lara"
        # Also handles cases like "Pathos'" -> "Pathos"
        if word.endswith("'s"):
            cleaned_word = word[:-2]
        elif word.endswith("'"):
            cleaned_word = word[:-1]
        else:
            cleaned_word = word

        # Rule 1: If it's a known common first name, it's a strong candidate.
        if cleaned_word in EXAMPLE_FIRST_NAMES:
            potential_names.add(cleaned_word)
            continue # Prioritize this, skip other checks for this word

        # Rule 2: If it's a common capitalized word (not a name), exclude it.
        if cleaned_word in COMMON_CAPITALIZED_WORDS:
            continue

        # Rule 3: If it's a capitalized word, not in common lists, consider it a potential name.
        # This is where most of the heuristic's less accurate guesses might come from.
        # Further filtering could be applied here (e.g., length, context), but kept simple for now.
        # A check for sentence starts was considered but adds complexity without full sentence tokenization.
        # The COMMON_CAPITALIZED_WORDS list should ideally handle most common sentence-starting capitalized words
        # that are not names (e.g., "The", "A", "Is").
        if cleaned_word: # Ensure cleaned_word is not empty after stripping
            potential_names.add(cleaned_word)

    # logger.debug(f"Heuristic name detection for thought '{thought[:50]}...' found: {potential_names}")
    return potential_names

def extract_character_references(
    recent_thoughts: List[str],
    known_npc_names_or_ids: List[str] # Can be names or IDs, will be normalized
) -> List[Tuple[str, str]]:
    """
    Monitors a list of recent thought strings for mentions of potential character names
    that are not already known (i.e., not in `known_npc_names_or_ids`).

    Args:
        recent_thoughts (List[str]): A list of thought strings from the SubconsciousNode.
        known_npc_names_or_ids (List[str]): A list of names or unique IDs of NPCs already
                                             known/registered. These will be normalized
                                             for case-insensitive comparison.

    Returns:
        List[Tuple[str, str]]: A list of tuples, where each tuple is:
                                (detected_name_verbatim, thought_content_where_found).
                                The `detected_name_verbatim` is the name as it was capitalized
                                in the thought (before normalization for checking against knowns).
                                Returns an empty list if no new references are found.
    """
    if not recent_thoughts:
        return []

    extracted_new_references: List[Tuple[str, str]] = []

    # Normalize known NPC names/IDs for efficient, case-insensitive lookup.
    # This assumes IDs might also be used and should be treated like names for matching here.
    normalized_known_set: Set[str] = {name.strip().lower() for name in known_npc_names_or_ids if name and isinstance(name, str)}

    # To avoid repeatedly adding the same *newly discovered* name from different thoughts within this batch
    # This set will store the normalized versions of names already added to extracted_new_references
    # in the current call to this function.
    newly_extracted_normalized_names_this_batch: Set[str] = set()

    # logger.debug(f"Extracting character references. Known (normalized): {normalized_known_set}")

    for thought_content in recent_thoughts:
        if not thought_content or not isinstance(thought_content, str):
            logger.warning(f"Skipping invalid thought content (not a string or empty): {thought_content}")
            continue

        # Use the heuristic to detect all potential capitalized names in this thought
        detected_potential_names_in_thought = _heuristic_detect_names(thought_content)

        for verbatim_name in detected_potential_names_in_thought:
            normalized_detected_name = verbatim_name.strip().lower() # Normalize for checking

            if not normalized_detected_name: # Skip if normalization resulted in empty string
                continue

            # Check if this normalized detected name is NOT in the set of known names
            # AND also NOT already extracted in this current batch of thoughts.
            if normalized_detected_name not in normalized_known_set and \
               normalized_detected_name not in newly_extracted_normalized_names_this_batch:

                logger.info(f"Found potential new character reference: '{verbatim_name}' "
                            f"in thought: '{thought_content[:70]}...' "
                            f"(Normalized: '{normalized_detected_name}')")

                extracted_new_references.append((verbatim_name, thought_content))
                newly_extracted_normalized_names_this_batch.add(normalized_detected_name)
                # Add to this batch's set to avoid duplicates FROM THIS SAME BATCH.
                # If "Jane" is new and appears in thought 1 and thought 2, she's added once.

    if extracted_new_references:
        logger.info(f"Extraction complete. Found {len(extracted_new_references)} potential new character references in this batch.")
    # else:
        # logger.debug("Extraction complete. No new character references found in this batch.")

    return extracted_new_references

if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.INFO) # Use INFO for cleaner output, DEBUG for more detail

    logger.info("--- Testing Subconscious Reference Parser ---")

    # Example known NPCs (can be names or IDs, will be normalized by the function)
    # Add self (Pathos) to known to avoid self-referencing as "new"
    current_known_npcs = ["Mailman Bob", "Alice Wonderland", "Pathos", "Dr. Emily Carter"]

    # Example thoughts from SubconsciousNode
    thoughts_batch_1 = [
        "I wonder if Lara still works at the cafe. Lara Croft is a legend.", # Lara (new), Lara Croft (new, variant)
        "Need to call Bob about that thing. No, not Mailman Bob, the other Bob.", # Bob (new, ambiguous but heuristic will pick it up)
        "Dr. Smith mentioned a new theory today. Smith seems very knowledgeable.", # Smith (new)
        "The weather today is nice. Alice said she'd be gardening.", # Alice (known, variant "Alice Wonderland")
        "Maybe I should ask Jane for help with this problem. Jane is smart.", # Jane (new)
        "I saw a post from Charlie online.", # Charlie (new)
        "This reminds me of something Pathos once said.", # Pathos (known)
        "A book by Herbert might be useful.", # Herbert (new)
        "The cat, Mittens, is very fluffy. Mittens is always around.", # Mittens (new, potential pet name)
        "I am I, and you are you. The quick brown fox.", # Test common words, no names expected
        "What about Eve? Is Eve coming?", # Eve (new, in EXAMPLE_FIRST_NAMES)
        "The Grand Hotel is a landmark. But Hotel California is just a song.", # Grand, Hotel, California (potential false positives by basic heuristic)
        "Met Mr. Black and Ms. White today. Also, Professor Plum.", # Black, White, Plum (new, titles should be handled by COMMON_CAPITALIZED_WORDS, but names themselves are new)
        "Pathos's favorite food is pizza.", # Pathos (known), check possessive stripping
        "Is it Monday already? Oh, I forgot it's June!" # Common capitalized words
    ]

    logger.info(f"Known NPCs/IDs before parsing (raw): {current_known_npcs}")

    newly_found_references = extract_character_references(thoughts_batch_1, current_known_npcs)

    if newly_found_references:
        logger.info("\n--- Potential New Character References Found (Batch 1) ---")
        for name, thought in newly_found_references:
            logger.info(f"  Name: '{name}' (from thought: '{thought}')")
    else:
        logger.info("\nNo new character references found in Batch 1.")

    # Simulate these new names being added to the known list for the next batch
    updated_known_npcs = current_known_npcs + [ref[0] for ref in newly_found_references]

    thoughts_batch_2 = [
        "Lara mentioned she's going to the library.", # Lara should now be known
        "That new guy, Alex, seems interesting.", # Alex (new, if not in previous batch's EXAMPLE_FIRST_NAMES)
        "Talked to Jane again. She's helpful.", # Jane should be known
        "I think Bob from accounting is different from the Bob I called earlier." # Bob (known, but context is different)
    ]
    logger.info(f"\nKnown NPCs/IDs before Batch 2 (raw): {updated_known_npcs}")

    newly_found_references_batch_2 = extract_character_references(thoughts_batch_2, updated_known_npcs)

    if newly_found_references_batch_2:
        logger.info("\n--- Potential New Character References Found (Batch 2) ---")
        for name, thought in newly_found_references_batch_2:
            logger.info(f"  Name: '{name}' (from thought: '{thought}')")
    else:
        logger.info("\nNo new character references found in Batch 2.")


    logger.info("\n--- Testing Edge Cases ---")
    test_edge_cases = [
        ("Dr. Strange is strange.", ["Strange"]), # Dr. should be ignored
        ("Ask Mr. Robot.", ["Robot"]),
        ("The quick brown Fox jumped.", ["Fox"]), # Fox might be a name
        ("I live on Penny Lane.", ["Penny", "Lane"]), # Lane is common, Penny might be a name
        ("My cat is named Max.", ["Max"]), # Max is common name
        ("Is it May or June?", []), # Common month names
    ]
    for thought, expected_names in test_edge_cases:
        refs = extract_character_references([thought], []) # No known NPCs for these specific small tests
        detected = sorted([r[0] for r in refs])
        logger.info(f"Thought: '{thought}', Expected: {sorted(expected_names)}, Detected: {detected}")
        # Basic check, perfect matching is hard with heuristics
        # This simply checks if the detected names are a superset of (or equal to) minimal expected names for simplicity here.
        # For a real test, you'd be more precise.
        # assert all(e_name in detected for e_name in expected_names)


    logger.info("\nSubconscious Reference Parser __main__ tests completed.")
