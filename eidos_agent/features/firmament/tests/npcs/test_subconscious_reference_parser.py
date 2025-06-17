# eidos_agent/features/firmament/tests/npcs/test_subconscious_reference_parser.py

import unittest
from typing import List, Tuple, Set # Added Set for _heuristic_detect_names if tested directly

# Attempt to import the functions to be tested.
# This structure tries to make it runnable if tests are in eidos_agent/features/firmament/tests/npcs/
# and the module is eidos_agent/features/firmament/npcs/
# Or if run from a project root where eidos_agent is in PYTHONPATH.
try:
    # Path assuming tests are run from a root that has eidos_agent in PYTHONPATH
    # e.g., python -m unittest eidos_agent.features.firmament.tests.npcs.test_subconscious_reference_parser
    from eidos_agent.features.firmament.npcs.subconscious_reference_parser import extract_character_references, _heuristic_detect_names, COMMON_CAPITALIZED_WORDS, EXAMPLE_FIRST_NAMES
except ImportError: # pragma: no cover
    # Fallback for running the test file directly from its own directory,
    # assuming 'firmament' is a sibling to 'tests' directory, and 'npcs' is under 'firmament'.
    # This might require adjusting PYTHONPATH (e.g., `PYTHONPATH=. python test_subconscious_reference_parser.py`)
    # Or, if the test runner handles paths well.
    try:
        from ....npcs.subconscious_reference_parser import extract_character_references, _heuristic_detect_names, COMMON_CAPITALIZED_WORDS, EXAMPLE_FIRST_NAMES
    except ImportError: # Final fallback if structure is different or path issues persist
        print("CRITICAL: Could not resolve imports for subconscious_reference_parser in test. Using dummy functions.")
        print("Ensure that the test runner is invoked from the project root, or PYTHONPATH is configured correctly.")
        # Define dummy functions so the test file can at least be parsed
        extract_character_references = lambda thoughts, known_names: [] # type: ignore
        _heuristic_detect_names = lambda thought: set() # type: ignore
        COMMON_CAPITALIZED_WORDS: Set[str] = set() # type: ignore
        EXAMPLE_FIRST_NAMES: Set[str] = set() # type: ignore


class TestSubconsciousReferenceParser(unittest.TestCase):

    def test_extract_new_character_references(self):
        thoughts = ["I met Lara today.", "Bob was there too.", "Then a new person, Charlie, arrived."]
        known_npcs = ["Lara"] # Lara is known, Bob and Charlie are new

        # The order of extraction depends on thought processing order and then word order within thought.
        # _heuristic_detect_names returns a set, but extract_character_references iterates thoughts sequentially.
        # If "Bob" is found first in "Bob was there too.", it's added. Then "Charlie".
        expected = [("Bob", "Bob was there too."), ("Charlie", "Then a new person, Charlie, arrived.")]

        result = extract_character_references(thoughts, known_npcs)
        self.assertCountEqual(result, expected, "Failed basic new character extraction.")

    def test_no_new_references_if_all_known(self):
        thoughts = ["Alice and Bob had a meeting.", "My friend Bob also mentioned it."]
        known_npcs = ["Alice", "Bob"] # All potentially detected names are known
        expected = []
        self.assertEqual(extract_character_references(thoughts, known_npcs), expected, "Should find no new refs if all are known.")

    def test_empty_thoughts_list(self):
        thoughts: List[str] = []
        known_npcs = ["Alice"]
        expected: List[Tuple[str,str]] = []
        self.assertEqual(extract_character_references(thoughts, known_npcs), expected, "Empty thoughts list should yield no refs.")

    def test_empty_known_npcs_list(self):
        thoughts = ["David introduced Eve."] # Assuming David and Eve are detectable by heuristic
        known_npcs: List[str] = []
        # Both David and Eve should be new. Order can vary based on internal set iteration from heuristic.
        expected = [("David", "David introduced Eve."), ("Eve", "David introduced Eve.")]

        result = extract_character_references(thoughts, known_npcs)
        self.assertCountEqual(result, expected, "All detected names should be new if known_npcs is empty.")


    def test_case_insensitivity_for_known_npcs(self):
        thoughts = ["Frank spoke to Grace."] # Frank known (lowercase), Grace new
        known_npcs = ["frank"]
        expected = [("Grace", "Frank spoke to Grace.")]
        result = extract_character_references(thoughts, known_npcs)
        self.assertCountEqual(result, expected, "Known NPC check should be case-insensitive.")

    def test_possessive_handling_in_heuristic(self):
        # This tests _heuristic_detect_names indirectly.
        # Assumes "Lara" is not in COMMON_CAPITALIZED_WORDS but might be in EXAMPLE_FIRST_NAMES or just caught as capitalized.
        thoughts = ["Lara's new discovery was amazing.", "Is this Pathos's idea?"]
        known_npcs = ["Pathos"] # Pathos is known, Lara is new
        expected_name = "Lara"

        result = extract_character_references(thoughts, known_npcs)
        # Check that "Lara" was extracted, not "Lara's"
        found_lara = any(name == expected_name for name, thought_str in result)
        self.assertTrue(found_lara, f"Expected '{expected_name}' to be extracted cleanly from possessive.")
        self.assertFalse(any("Lara's" in name for name, thought_str in result), "Possessive form 'Lara's' should not be extracted as name.")
        self.assertFalse(any("Pathos's" in name for name, thought_str in result), "Possessive of known NPC 'Pathos's' should not be extracted.")


    def test_common_capitalized_words_filtered(self):
        # Assumes "Monday", "The" are in COMMON_CAPITALIZED_WORDS.
        # "Helper" is assumed not to be, and thus a potential name if capitalized.
        thoughts = ["On Monday, the new Helper arrived.", "The situation is critical."]
        known_npcs = []

        result = extract_character_references(thoughts, known_npcs)

        found_helper = any(name == "Helper" for name, thought_str in result)
        found_monday = any(name == "Monday" for name, thought_str in result)
        found_the = any(name == "The" for name, thought_str in result)

        self.assertTrue(found_helper, "Expected 'Helper' (uncommon capitalized) to be detected.")
        self.assertFalse(found_monday, "Expected 'Monday' (common capitalized) to be filtered out.")
        self.assertFalse(found_the, "Expected 'The' (common capitalized) at sentence start to be filtered out.")


    def test_example_first_names_prioritized_and_extracted_if_new(self):
        # Assumes "Eve" is in EXAMPLE_FIRST_NAMES.
        thoughts = ["Then Eve walked in. What a surprise!"]
        known_npcs = [] # Eve is new
        expected = [("Eve", "Then Eve walked in. What a surprise!")]
        result = extract_character_references(thoughts, known_npcs)
        self.assertCountEqual(result, expected, "'Eve' from EXAMPLE_FIRST_NAMES should be extracted as new.")

        # Now test if Eve is known
        known_npcs_with_eve = ["Eve"]
        result_eve_known = extract_character_references(thoughts, known_npcs_with_eve)
        self.assertEqual(len(result_eve_known), 0, "'Eve' should not be extracted if already known.")


    def test_no_clear_names_in_simple_sentences(self):
        thoughts = ["The weather is nice today.", "Let's go for a short walk outside."]
        known_npcs = ["SomeoneRandom"] # Some known NPC to ensure list isn't empty by default
        expected = []
        self.assertEqual(extract_character_references(thoughts, known_npcs), expected, "Simple sentences without names should yield no refs.")

    def test_multiple_new_names_in_one_thought(self):
        thoughts = ["Did Tom tell Wendy about the plan involving Xavier?"]
        known_npcs = ["Tom"] # Tom is known; Wendy and Xavier are new.
        # Heuristic should pick up Wendy and Xavier. Order might vary due to set from heuristic.
        expected = [
            ("Wendy", "Did Tom tell Wendy about the plan involving Xavier?"),
            ("Xavier", "Did Tom tell Wendy about the plan involving Xavier?")
        ]
        result = extract_character_references(thoughts, known_npcs)
        self.assertCountEqual(result, expected, "Multiple new names in one thought not extracted correctly.")

    def test_direct_heuristic_detection_for_specific_cases(self):
        # Directly test the _heuristic_detect_names function for more fine-grained checks.
        if not callable(_heuristic_detect_names) or _heuristic_detect_names.__name__ == '<lambda>': # Check if using dummy
            self.skipTest("_heuristic_detect_names function not available for direct test (likely import error).")

        # Case 1: Simple name
        names1 = _heuristic_detect_names("A thought about Lara.")
        self.assertIn("Lara", names1)

        # Case 2: Name with title, title should be excluded by COMMON_CAPITALIZED_WORDS
        names2 = _heuristic_detect_names("Dr. Strange is here.")
        self.assertIn("Strange", names2)
        self.assertNotIn("Dr", names2)

        # Case 3: Common word capitalized mid-sentence (should usually be excluded if in COMMON_CAPITALIZED_WORDS)
        # but if not, it might be caught. "Next" is not in the current list.
        names3 = _heuristic_detect_names("What is Next for us?")
        if "Next" not in COMMON_CAPITALIZED_WORDS: # Depending on current list
            self.assertIn("Next", names3, "'Next' (if not common) might be picked up by heuristic.")
        else:
            self.assertNotIn("Next", names3, "'Next' (if common) should be filtered.")


    def test_name_at_sentence_start_if_also_example_name(self):
        # "Frank" is in EXAMPLE_FIRST_NAMES
        thoughts = ["Frank was here. Then he left."]
        known_npcs = []
        result = extract_character_references(thoughts, known_npcs)
        self.assertTrue(any(name == "Frank" for name, _ in result),
                        "Name from EXAMPLE_FIRST_NAMES should be caught even at sentence start.")

    def test_common_word_at_sentence_start_is_filtered(self):
        # "The" is in COMMON_CAPITALIZED_WORDS
        thoughts = ["The cat sat on the mat."]
        known_npcs = []
        result = extract_character_references(thoughts, known_npcs)
        self.assertFalse(any(name == "The" for name, _ in result),
                         "Common word 'The' at sentence start should be filtered.")


if __name__ == '__main__': # pragma: no cover
    unittest.main(verbosity=2)
