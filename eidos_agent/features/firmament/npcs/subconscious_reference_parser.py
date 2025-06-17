# eidos_agent/features/firmament/npcs/subconscious_reference_parser.py
import logging
import re
from typing import List, Tuple, Set, Dict, Any, Pattern # Added Dict, Any

logger = logging.getLogger(__name__)

COMMON_CAPITALIZED_WORDS: Set[str] = {
    "I", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    "Dr", "Mr", "Mrs", "Ms", "Prof", "Rev", "St",
    "The", "A", "An", "Is", "Was", "Were", "Will", "Do", "Does", "Did",
    "But", "Or", "So", "If", "Then", "Else", "Not", "And", "For", "Nor",
    "He", "She", "It", "They", "We", "You", "My", "His", "Her", "Its", "Our", "Their",
    "Who", "What", "When", "Where", "Why", "How",
    "Street", "Road", "Avenue", "Lane", "Drive", "Park", "City", "County", "State",
    "Inc", "Ltd", "Corp", "Co"
}
EXAMPLE_FIRST_NAMES: Set[str] = {
    "Alex", "Alice", "Bob", "Charlie", "David", "Eve", "Frank", "Grace", "Henry", "Ivy",
    "Jack", "Kate", "Liam", "Lara", "Mia", "Noah", "Olivia", "Owen", "Paul", "Quinn",
    "Ryan", "Sarah", "Tom", "Uma", "Victor", "Wendy", "Xavier", "Yara", "Zoe", "Jane",
    "John", "Mary", "James", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "William", "Elizabeth"
}
CAPITALIZED_WORD_REGEX: Pattern[str] = re.compile(r"\b[A-Z][a-zA-Z'-]*\b")


def _heuristic_detect_names(thought: str) -> Set[str]:
    """
    Detects potential names in a thought string using simple heuristics.
    Returns a set of verbatim capitalized words found that are candidates for being names.
    """
    if not thought or not isinstance(thought, str):
        return set()

    potential_verbatim_names: Set[str] = set()
    found_capitalized_words = set(CAPITALIZED_WORD_REGEX.findall(thought))

    for verbatim_word in found_capitalized_words:
        # Clean possessives for checking against common lists and example names
        if verbatim_word.endswith("'s"):
            cleaned_word_for_check = verbatim_word[:-2]
        elif verbatim_word.endswith("'"):
            cleaned_word_for_check = verbatim_word[:-1]
        else:
            cleaned_word_for_check = verbatim_word

        if not cleaned_word_for_check: # Skip if cleaning resulted in empty string
            continue

        # Rule 1: If the cleaned version is an example first name, add the original verbatim word.
        if cleaned_word_for_check in EXAMPLE_FIRST_NAMES:
            potential_verbatim_names.add(verbatim_word)
            continue

        # Rule 2: If the cleaned version is a common capitalized word (not a name), exclude it.
        if cleaned_word_for_check in COMMON_CAPITALIZED_WORDS:
            continue

        # Rule 3: If it's capitalized, not in common lists, consider the original verbatim word.
        potential_verbatim_names.add(verbatim_word)

    # logger.debug(f"Heuristic name detection for thought '{thought[:50]}...' found verbatim: {potential_verbatim_names}")
    return potential_verbatim_names

def extract_character_references(
    recent_thoughts: List[str],
    known_npc_profiles: List[Dict[str, Any]] # Changed parameter
) -> List[Tuple[str, str]]:
    """
    Monitors a list of recent thought strings for mentions of potential character names
    that are not already known (i.e., their names are not found in `known_npc_profiles`).

    Args:
        recent_thoughts (List[str]): A list of thought strings from the SubconsciousNode.
        known_npc_profiles (List[Dict[str, Any]]): A list of profile dictionaries
                                                   for NPCs already known. Each profile
                                                   is expected to have a "name" key (string).
    Returns:
        List[Tuple[str, str]]: A list of tuples, where each tuple is:
                                (verbatim_detected_name, thought_content_where_found).
                                The `verbatim_detected_name` is the name as it was capitalized
                                in the thought.
                                Returns an empty list if no new references are found.
    """
    if not recent_thoughts:
        return []

    normalized_known_display_names: Set[str] = set()
    if not isinstance(known_npc_profiles, list): # Basic type check
        logger.warning("extract_character_references: known_npc_profiles is not a list. Treating as no known NPCs.")
    else:
        for profile in known_npc_profiles:
            if isinstance(profile, dict):
                name = profile.get("name") # Get the display name
                if isinstance(name, str) and name.strip():
                    normalized_known_display_names.add(name.strip().lower())
                else: # pragma: no cover
                    logger.debug(f"Known NPC profile (ID: {profile.get('id', 'Unknown ID')}) missing 'name' or name is invalid.")
            # else: # pragma: no cover
                # logger.warning(f"Item in known_npc_profiles is not a dictionary: {profile}")

    # logger.debug(f"Extracting. Known display names (normalized): {normalized_known_display_names}")

    extracted_new_references: List[Tuple[str, str]] = []
    already_extracted_this_batch_normalized: Set[str] = set()

    for thought_content in recent_thoughts:
        if not thought_content or not isinstance(thought_content, str):
            # logger.warning(f"Skipping invalid thought content: {thought_content}")
            continue

        detected_verbatim_names_in_thought = _heuristic_detect_names(thought_content)

        for verbatim_name in detected_verbatim_names_in_thought:
            # For checking against known list and batch list, use a normalized version
            # AND clean possessives from the verbatim name for this check.
            if verbatim_name.endswith("'s"):
                normalized_check_name = verbatim_name[:-2].strip().lower()
            elif verbatim_name.endswith("'"):
                normalized_check_name = verbatim_name[:-1].strip().lower()
            else:
                normalized_check_name = verbatim_name.strip().lower()

            if not normalized_check_name: # Skip if normalization resulted in empty string
                continue

            if normalized_check_name not in normalized_known_display_names and \
               normalized_check_name not in already_extracted_this_batch_normalized:

                # logger.info(f"Found potential new character reference: '{verbatim_name}' in thought: '{thought_content[:70]}...'")
                extracted_new_references.append((verbatim_name, thought_content))
                already_extracted_this_batch_normalized.add(normalized_check_name)

    # if extracted_new_references:
        # logger.info(f"Extraction complete. Found {len(extracted_new_references)} potential new character references.")

    return extracted_new_references

if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.INFO) # Use INFO for cleaner output, DEBUG for detailed heuristic steps
    logger_parser = logging.getLogger('eidos_agent.features.firmament.npcs.subconscious_reference_parser')
    logger_parser.setLevel(logging.DEBUG) # Enable DEBUG specifically for this module if needed

    logger.info("--- Testing Subconscious Reference Parser (Updated with Profile Input) ---")

    current_known_npc_profiles = [
        {"id": "bob1", "name": "Mailman Bob", "description": "Our friendly mail carrier."},
        {"id": "alice2", "name": "Alice Wonderland", "occupation": "Dreamer"},
        {"id": "pathos_self", "name": "Pathos", "role": "Protagonist"}, # Add self to known
        {"id": "dr_ecarter", "name": "Dr. Emily Carter", "field": "Physics"} # Known by full name with title
    ]

    thoughts_batch_1 = [
        "I wonder if Lara still works at the cafe. Lara Croft is a legend.", # Lara, Lara Croft
        "Need to call Bob about that thing. No, not Mailman Bob, the other Bob.", # Bob
        "Dr. Smith mentioned a new theory today. Smith seems very knowledgeable.", # Smith
        "The weather today is nice. Alice said she'd be gardening.", # Alice (known)
        "Maybe I should ask Jane for help with this problem. Jane is smart.", # Jane
        "I saw a post from Charlie online.", # Charlie
        "This reminds me of something Pathos once said.", # Pathos (known)
        "A book by Herbert might be useful.", # Herbert
        "Lara's cat, Mittens, is very fluffy. Mittens is always around.", # Mittens (Lara already extracted or new)
        "I am I, and you are you. The quick brown fox.",
        "What about Eve? Is Eve coming?", # Eve
        "The Grand Hotel is a landmark. But Hotel California is just a song.", # Grand, Hotel, California (potential false positives)
        "Met Mr. Black and Ms. White today. Also, Professor Plum.", # Black, White, Plum
        "Pathos's favorite food is pizza.", # Pathos (known)
        "Is it Monday already? Oh, I forgot it's June!",
        "Talked to Dr. Carter about her latest research.", # Dr. Carter / Carter (known variant)
        "I think Alice Wonderland is a great name." # Alice Wonderland (known)
    ]

    logger.info(f"Known NPC Profiles (names): {[p.get('name') for p in current_known_npc_profiles]}")
    newly_found_references = extract_character_references(thoughts_batch_1, current_known_npc_profiles)

    print("\n--- Potential New Character References Found (Batch 1) ---")
    if newly_found_references:
        for name, thought in newly_found_references:
            print(f"  Name: '{name}' (from thought: '{thought}')")
    else:
        print("  No new character references found in Batch 1.")

    # Simulate these new names being added to the known list for the next batch
    # For simulation, we just need the 'name' field in the profile structure.
    updated_known_npc_profiles = current_known_npc_profiles + [{"name": ref[0]} for ref in newly_found_references]

    thoughts_batch_2 = [
        "Lara mentioned she's going to the library.", # Lara should now be known
        "That new guy, Alex, seems interesting.", # Alex (new, if not in previous batch's EXAMPLE_FIRST_NAMES and caught)
        "Talked to Jane again. She's helpful.", # Jane should be known
        "I think Bob from accounting is different from the Bob I called earlier." # Bob (known, but context is different - still "Bob")
    ]
    logger.info(f"\nKnown NPC Profiles for Batch 2 (names): {[p.get('name') for p in updated_known_npc_profiles]}")

    newly_found_references_batch_2 = extract_character_references(thoughts_batch_2, updated_known_npc_profiles)

    print("\n--- Potential New Character References Found (Batch 2) ---")
    if newly_found_references_batch_2:
        for name, thought in newly_found_references_batch_2:
            print(f"  Name: '{name}' (from thought: '{thought}')")
    else:
        print("  No new character references found in Batch 2.")

    logger.info("\n--- Testing Edge Cases with Profile Input ---")
    test_edge_cases_profiles = [
        ("Dr. Strange is strange.", [], [("Strange", "Dr. Strange is strange.")])
    ]
    for thought, known_profiles_minimal, expected_refs_tuples in test_edge_cases_profiles:
        refs = extract_character_references([thought], known_profiles_minimal)
        detected_verbatim = sorted([r[0] for r in refs])
        expected_verbatim = sorted([r_expected[0] for r_expected in expected_refs_tuples])
        print(f"Thought: '{thought}', Known: {[p.get('name') for p in known_profiles_minimal]}, Expected Verbatim: {expected_verbatim}, Detected Verbatim: {detected_verbatim}")
        assert detected_verbatim == expected_verbatim

    logger.info("\nSubconscious Reference Parser __main__ (updated with profile input) tests completed.")
