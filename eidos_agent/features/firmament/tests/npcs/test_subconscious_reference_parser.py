# eidos_agent/features/firmament/tests/npcs/test_subconscious_reference_parser.py

import unittest
from typing import List, Tuple, Dict, Any, Set # Added Dict, Any, Set

# Flexible import attempts for the module under test
try:
    # Path assuming tests are run from project root (e.g., python -m unittest discover ...)
    from eidos_agent.features.firmament.npcs.subconscious_reference_parser import extract_character_references, _heuristic_detect_names
except ImportError: # pragma: no cover
    # Fallback for running directly from tests/npcs or similar relative structures
    try:
        from ....features.firmament.npcs.subconscious_reference_parser import extract_character_references, _heuristic_detect_names
    except ImportError:
        try:
            from ...npcs.subconscious_reference_parser import extract_character_references, _heuristic_detect_names
        except ImportError:
            try:
                from ..npcs.subconscious_reference_parser import extract_character_references, _heuristic_detect_names
            except ImportError:
                print("CRITICAL: Could not resolve imports for subconscious_reference_parser in test. Using dummy functions.")
                extract_character_references = lambda thoughts, known_profiles: [] # type: ignore
                _heuristic_detect_names = lambda thought: set() # type: ignore


class TestSubconsciousReferenceParser(unittest.TestCase):

    def test_extract_new_character_references(self):
        print("Running: test_extract_new_character_references")
        thoughts = ["I met Lara today.", "Bob was there too.", "Then a new person, Charlie, arrived."]
        known_npc_profiles = [{"name": "Lara", "id": "lara01"}]
        # Expected: Bob and Charlie are new. Lara is known.
        # _heuristic_detect_names for "I met Lara today." -> {"Lara"} (Known after normalization)
        # _heuristic_detect_names for "Bob was there too." -> {"Bob"} (New)
        # _heuristic_detect_names for "Then a new person, Charlie, arrived." -> {"Charlie"} (New)
        expected = [("Bob", "Bob was there too."), ("Charlie", "Then a new person, Charlie, arrived.")]
        result = extract_character_references(thoughts, known_npc_profiles)
        self.assertCountEqual(result, expected, f"Result: {result}, Expected: {expected}")

    def test_no_new_references_if_all_known(self):
        print("Running: test_no_new_references_if_all_known")
        thoughts = ["Alice and Bob had a meeting.", "My friend Bob also mentioned it."]
        known_npc_profiles = [{"name": "Alice", "id": "alice01"}, {"name": "Bob", "id": "bob01"}]
        expected: List[Tuple[str, str]] = []
        self.assertEqual(extract_character_references(thoughts, known_npc_profiles), expected)

    def test_empty_thoughts_list(self):
        print("Running: test_empty_thoughts_list")
        thoughts: List[str] = []
        known_npc_profiles = [{"name": "Alice", "id": "alice01"}]
        expected: List[Tuple[str, str]] = []
        self.assertEqual(extract_character_references(thoughts, known_npc_profiles), expected)

    def test_empty_known_npcs_list(self):
        print("Running: test_empty_known_npcs_list")
        # Assuming "David" and "Eve" are detectable by heuristic and not common words.
        # "Eve" is in EXAMPLE_FIRST_NAMES, "David" might be caught as capitalized.
        thoughts = ["David introduced Eve."]
        known_npc_profiles: List[Dict[str, Any]] = []
        expected = [("David", "David introduced Eve."), ("Eve", "David introduced Eve.")]
        result = extract_character_references(thoughts, known_npc_profiles)
        self.assertCountEqual(result, expected, f"Result: {result}, Expected: {expected}")

    def test_case_insensitivity_for_known_npcs_via_profile_name(self):
        print("Running: test_case_insensitivity_for_known_npcs_via_profile_name")
        thoughts = ["Frank spoke to Grace."] # Assuming "Grace" is detectable.
        known_npc_profiles = [{"name": "frank", "id": "frank01"}]
        expected = [("Grace", "Frank spoke to Grace.")]
        result = extract_character_references(thoughts, known_npc_profiles)
        self.assertCountEqual(result, expected, f"Result: {result}, Expected: {expected}")

    def test_possessive_handling_still_works(self):
        print("Running: test_possessive_handling_still_works")
        thoughts = ["Lara's new discovery was amazing."]
        known_npc_profiles: List[Dict[str, Any]] = []
        # _heuristic_detect_names returns "Lara's" (verbatim)
        # extract_character_references normalizes "Lara's" to "lara" for checks.
        # So, "Lara's" (verbatim) is returned if "lara" is new.
        expected_verbatim_name = "Lara's"

        result = extract_character_references(thoughts, known_npc_profiles)
        self.assertTrue(any(name == expected_verbatim_name for name, thought_str in result),
                        f"Expected verbatim '{expected_verbatim_name}' to be extracted. Got: {result}")

    def test_common_capitalized_words_filtered_with_profiles(self):
        print("Running: test_common_capitalized_words_filtered_with_profiles")
        # "Monday", "The" are in COMMON_CAPITALIZED_WORDS. "Helper" is not.
        thoughts = ["On Monday, the new Helper arrived.", "The situation is critical."]
        known_npc_profiles: List[Dict[str, Any]] = []
        result = extract_character_references(thoughts, known_npc_profiles)

        found_helper = any(name == "Helper" for name, thought_str in result)
        found_monday = any(name == "Monday" for name, thought_str in result)

        self.assertTrue(found_helper, "Expected 'Helper' to be detected.")
        self.assertFalse(found_monday, "Expected 'Monday' to be filtered out.")

    def test_example_first_names_prioritized_with_profiles(self):
        print("Running: test_example_first_names_prioritized_with_profiles")
        thoughts = ["Then Eve walked in. What a surprise!"] # Eve is in EXAMPLE_FIRST_NAMES
        known_npc_profiles: List[Dict[str, Any]] = []
        expected = [("Eve", "Then Eve walked in. What a surprise!")]
        result = extract_character_references(thoughts, known_npc_profiles)
        self.assertCountEqual(result, expected, f"Result: {result}, Expected: {expected}")

    def test_no_clear_names_with_profiles(self):
        print("Running: test_no_clear_names_with_profiles")
        thoughts = ["The weather is nice.", "Let's go for a walk."]
        known_npc_profiles = [{"name": "Someone", "id": "someone01"}]
        expected: List[Tuple[str, str]] = []
        self.assertEqual(extract_character_references(thoughts, known_npc_profiles), expected)

    def test_multiple_new_names_in_one_thought_with_profiles(self):
        print("Running: test_multiple_new_names_in_one_thought_with_profiles")
        thoughts = ["Did Tom tell Wendy about the plan involving Xavier?"]
        known_npc_profiles = [{"name": "Tom", "id": "tom01"}]
        expected = [
            ("Wendy", "Did Tom tell Wendy about the plan involving Xavier?"),
            ("Xavier", "Did Tom tell Wendy about the plan involving Xavier?")
        ]
        result = extract_character_references(thoughts, known_npc_profiles)
        self.assertCountEqual(result, expected, f"Result: {result}, Expected: {expected}")

    def test_profile_missing_name_key_is_handled(self):
        print("Running: test_profile_missing_name_key_is_handled")
        thoughts = ["A thought about UnknownPerson."] # Assuming UnknownPerson is detected
        known_npc_profiles = [{"id": "kg01", "description": "A known guy without a name field."}]
        # "UnknownPerson" is new because no valid names are in known_npc_profiles.
        expected = [("UnknownPerson", "A thought about UnknownPerson.")]
        result = extract_character_references(thoughts, known_npc_profiles)
        self.assertCountEqual(result, expected, f"Result: {result}, Expected: {expected}")

    def test_profile_with_empty_name_string_is_handled(self):
        print("Running: test_profile_with_empty_name_string_is_handled")
        thoughts = ["Another thought about PersonX."] # Assuming PersonX is detected
        known_npc_profiles = [{"name": "", "id": "empty_name_id"}]
        # "PersonX" is new as empty string "" in known_profiles is ignored.
        expected = [("PersonX", "Another thought about PersonX.")]
        result = extract_character_references(thoughts, known_npc_profiles)
        self.assertCountEqual(result, expected, f"Result: {result}, Expected: {expected}")

    def test_profile_with_non_string_name_is_handled(self):
        print("Running: test_profile_with_non_string_name_is_handled")
        thoughts = ["A final thought about CharacterY."] # Assuming CharacterY is detected
        known_npc_profiles = [{"name": 123, "id": "int_name_id"}] # Non-string name
        # "CharacterY" is new as non-string name in known_profiles is ignored.
        expected = [("CharacterY", "A final thought about CharacterY.")]
        result = extract_character_references(thoughts, known_npc_profiles)
        self.assertCountEqual(result, expected, f"Result: {result}, Expected: {expected}")

    def test_profiles_with_mixed_validity(self):
        print("Running: test_profiles_with_mixed_validity")
        thoughts = ["Alex mentioned Beta and Gamma.", "Beta is also known as BetaTest."]
        known_npc_profiles = [
            {"name": "Alex", "id": "alex01"},      # Alex is known
            {"id": "no_name_profile"},             # Invalid profile (no name)
            {"name": 12345, "id": "bad_name_type"}, # Invalid profile (name not string)
            {"name": "  ", "id": "empty_name"},    # Invalid profile (name is empty string after strip)
            {"name": "BetaTest", "id": "beta01"}   # BetaTest is known
        ]
        # "Alex" is known.
        # "Beta" will be detected. "BetaTest" is known, so "Beta" (normalized from "BetaTest") should be seen as known.
        #   Correction: _heuristic_detect_names returns "Beta", normalized "beta".
        #   known_npc_profiles has "BetaTest", normalized "betatest".
        #   "beta" is not in {"alex", "betatest"}. So "Beta" should be new.
        # "Gamma" will be detected and is new.
        expected = [
            ("Beta", "Alex mentioned Beta and Gamma."),
            ("Gamma", "Alex mentioned Beta and Gamma."),
            ("Beta", "Beta is also known as BetaTest.") # "Beta" is still new based on above logic
        ]
        # Let's refine the logic for the "Beta is also known as BetaTest."
        # If "Beta" was already extracted from the first thought, it won't be from the second by current extract_character_references.
        # So, only one "Beta" entry.
        expected_refined = [
            ("Beta", "Alex mentioned Beta and Gamma."), # First mention of new name "Beta"
            ("Gamma", "Alex mentioned Beta and Gamma.")  # First mention of new name "Gamma"
        ]

        result = extract_character_references(thoughts, known_npc_profiles)
        self.assertCountEqual(result, expected_refined, f"Result: {result}, Expected: {expected_refined}")


if __name__ == '__main__': # pragma: no cover
    unittest.main(verbosity=2)
