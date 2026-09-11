#!/usr/bin/env python3
"""
Check if tools.json adheres to .editorconfig rules.
Rules for *.json files:
- indent_style = tab
- indent_size = 1
- charset = utf-8
- end_of_line = lf
- insert_final_newline = true
- trim_trailing_whitespace = true
"""
import sys
import json
import re


def _update_depth(stripped, depth, in_string, escape_next):
    """
    Return the updated (depth, in_string, escape_next) after processing one
    stripped line, counting only braces/brackets that appear outside strings.

    This is the single source of truth for depth tracking used by all checks
    in this module.
    """
    line_in_string = in_string
    line_escape_next = escape_next
    open_count = 0
    close_count = 0

    for char in stripped:
        if line_escape_next:
            line_escape_next = False
            continue

        if char == '\\':
            line_escape_next = True
            continue

        if char == '"':
            line_in_string = not line_in_string
            continue

        if not line_in_string:
            if char == '{' or char == '[':
                open_count += 1
            elif char == '}' or char == ']':
                close_count += 1

    new_depth = max(0, depth + (open_count - close_count))
    return new_depth, line_in_string, line_escape_next


def check_json_structural_indentation(text, lines):
    """
    Check if JSON structural indentation adheres to tab-based rules.
    Validates that braces, brackets, and their contents are properly indented.
    Uses JSON structure to identify which entry errors belong to.
    """
    errors = []

    # Try to parse JSON to get entry information
    try:
        data = json.loads(text)
        is_array = isinstance(data, list)
    except json.JSONDecodeError as e:
        errors.append(f"ERROR: Invalid JSON - {e}")
        return errors

    # Track expected indentation depth and current entry
    depth = 0
    in_string = False
    escape_next = False
    current_entry_index = None
    current_entry_title = None

    for i, line in enumerate(lines, 1):
        # Skip the final empty line
        if i == len(lines) and line == '':
            continue

        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            continue

        # Track which entry we're in based on depth
        # At depth 1, we're inside a top-level array entry
        if is_array and depth == 1 and (stripped == '{' or stripped.startswith('{')):
            current_entry_index = 0 if current_entry_index is None else current_entry_index + 1
            if current_entry_index < len(data):
                current_entry_title = data[current_entry_index].get('title')
            else:
                current_entry_title = None
        elif depth == 0:
            # Outside of any entry
            current_entry_index = None
            current_entry_title = None

        # Count leading tabs and check for mixed indentation
        leading_tabs = 0
        has_mixed_indentation = False
        for j, char in enumerate(line):
            if char == '\t':
                leading_tabs += 1
            elif char == ' ':
                # Found space in indentation area - this is an error
                if current_entry_index is not None and current_entry_title:
                    errors.append(
                        f"ERROR: Entry #{current_entry_index} ('{current_entry_title}'): Line {i} has space character in indentation "
                        f"(position {j+1}): tabs and spaces should not be mixed"
                    )
                elif current_entry_index is not None:
                    errors.append(
                        f"ERROR: Entry #{current_entry_index}: Line {i} has space character in indentation "
                        f"(position {j+1}): tabs and spaces should not be mixed"
                    )
                else:
                    errors.append(
                        f"ERROR: Line {i} has space character in indentation "
                        f"(position {j+1}): tabs and spaces should not be mixed"
                    )
                has_mixed_indentation = True
                break
            else:
                # First non-whitespace character
                break

        # Determine expected indentation based on the line content
        # Lines that decrease depth (closing braces/brackets)
        if stripped.startswith('}') or stripped.startswith(']'):
            expected_depth = depth - 1
        else:
            expected_depth = depth

        # Guard against negative depth (malformed JSON structure)
        if expected_depth < 0:
            expected_depth = 0

        # Check if indentation matches expected depth (skip if mixed indentation already reported)
        if not has_mixed_indentation and leading_tabs != expected_depth:
            # Get context for error message
            context = stripped[:50] + '...' if len(stripped) > 50 else stripped

            # Use entry information from structural tracking
            if current_entry_index is not None and current_entry_title:
                errors.append(
                    f"ERROR: Entry #{current_entry_index} ('{current_entry_title}'): Line {i} has incorrect indentation: "
                    f"expected {expected_depth} tab(s), found {leading_tabs} tab(s) - '{context}'"
                )
            elif current_entry_index is not None:
                errors.append(
                    f"ERROR: Entry #{current_entry_index}: Line {i} has incorrect indentation: "
                    f"expected {expected_depth} tab(s), found {leading_tabs} tab(s) - '{context}'"
                )
            else:
                errors.append(
                    f"ERROR: Line {i} has incorrect indentation: "
                    f"expected {expected_depth} tab(s), found {leading_tabs} tab(s) - '{context}'"
                )

        # Update depth for the next line
        depth, in_string, escape_next = _update_depth(stripped, depth, in_string, escape_next)

    return errors


def check_unicode_escapes(text, data):
    """
    Check if JSON file contains unnecessary Unicode escape sequences.
    Characters like ç, ê, etc. should be stored as-is, not as \\u00e7, \\u00ea.
    This requires ensure_ascii=False when using json.dump().
    """
    errors = []

    # Common Unicode escape patterns for Latin characters with diacritics (U+0000 to U+00FF)
    # These should be written directly, not escaped
    unicode_escape_pattern = re.compile(r'\\u00[0-9a-fA-F]{2}')

    # Find all Unicode escape sequences - only proceed if any are found
    if not unicode_escape_pattern.search(text):
        return errors

    lines = text.split('\n')
    depth = 0
    in_string = False
    escape_next = False
    current_entry_index = None
    current_entry_title = None
    is_array = isinstance(data, list)
    field_name_pattern = re.compile(r'^\s*"([^"]+)"\s*:')

    for i, line in enumerate(lines, 1):
        if i == len(lines) and line == '':
            continue

        stripped = line.strip()
        if not stripped:
            continue

        if is_array and depth == 1 and (stripped == '{' or stripped.startswith('{')):
            current_entry_index = 0 if current_entry_index is None else current_entry_index + 1
            if current_entry_index < len(data):
                current_entry_title = data[current_entry_index].get('title')
            else:
                current_entry_title = None
        elif depth == 0:
            current_entry_index = None
            current_entry_title = None

        if unicode_escape_pattern.search(line):
            field_match = field_name_pattern.match(line)
            field_name = field_match.group(1) if field_match else "unknown"

            if current_entry_index is not None and current_entry_title:
                errors.append(
                    f"ERROR: Entry #{current_entry_index} ('{current_entry_title}'): "
                    f"Line {i} contains Unicode escape sequences in field '{field_name}'. "
                    f"Use ensure_ascii=False in json.dump() to preserve special characters."
                )
            elif current_entry_index is not None:
                errors.append(
                    f"ERROR: Entry #{current_entry_index}: "
                    f"Line {i} contains Unicode escape sequences in field '{field_name}'. "
                    f"Use ensure_ascii=False in json.dump() to preserve special characters."
                )
            else:
                errors.append(
                    f"ERROR: Line {i} contains Unicode escape sequences. "
                    f"Use ensure_ascii=False in json.dump() to preserve special characters."
                )

        # Update depth for the next line
        depth, in_string, escape_next = _update_depth(stripped, depth, in_string, escape_next)

    return errors


def check_editorconfig(json_file):
    """Check if JSON file adheres to .editorconfig rules."""
    errors = []

    try:
        with open(json_file, 'rb') as f:
            content = f.read()

        # Check charset (UTF-8)
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            errors.append("ERROR: File is not UTF-8 encoded")
            print('\n'.join(errors))
            return False

        # Check end_of_line (LF)
        if b'\r\n' in content:
            errors.append("ERROR: File contains CRLF line endings (should be LF)")
        elif b'\r' in content:
            errors.append("ERROR: File contains CR line endings (should be LF)")

        # Check insert_final_newline
        if not content.endswith(b'\n'):
            errors.append("ERROR: File does not end with a newline")

        # Check trim_trailing_whitespace and indent_style (tabs)
        lines = text.split('\n')

        # Parse JSON to get entry information for error messages
        try:
            data = json.loads(text)
            is_array = isinstance(data, list)
        except (json.JSONDecodeError, Exception):
            data = None
            is_array = False

        # Track current entry while checking each line
        depth = 0
        in_string = False
        escape_next = False
        current_entry_index = None
        current_entry_title = None

        for i, line in enumerate(lines, 1):
            # Skip the final empty line (result of file ending with \n)
            if i == len(lines) and line == '':
                continue

            stripped = line.strip()

            # Track which entry we're in based on depth
            if is_array and data and depth == 1 and (stripped == '{' or stripped.startswith('{')):
                current_entry_index = 0 if current_entry_index is None else current_entry_index + 1
                if current_entry_index < len(data):
                    current_entry_title = data[current_entry_index].get('title')
                else:
                    current_entry_title = None
            elif depth == 0:
                current_entry_index = None
                current_entry_title = None

            # Check trailing whitespace
            if line.rstrip() != line:
                if current_entry_index is not None and current_entry_title:
                    errors.append(f"ERROR: Entry #{current_entry_index} ('{current_entry_title}'): Line {i} has trailing whitespace")
                elif current_entry_index is not None:
                    errors.append(f"ERROR: Entry #{current_entry_index}: Line {i} has trailing whitespace")
                else:
                    errors.append(f"ERROR: Line {i} has trailing whitespace")

            # Check for spaces used for indentation (should be tabs)
            if line.startswith(' '):
                if current_entry_index is not None and current_entry_title:
                    errors.append(f"ERROR: Entry #{current_entry_index} ('{current_entry_title}'): Line {i} uses spaces for indentation (should use tabs)")
                elif current_entry_index is not None:
                    errors.append(f"ERROR: Entry #{current_entry_index}: Line {i} uses spaces for indentation (should use tabs)")
                else:
                    errors.append(f"ERROR: Line {i} uses spaces for indentation (should use tabs)")

            # Update depth for the next line
            if stripped:
                depth, in_string, escape_next = _update_depth(stripped, depth, in_string, escape_next)

        # Check JSON structural indentation
        structural_errors = check_json_structural_indentation(text, lines)
        errors.extend(structural_errors)

        # Check for Unicode escape sequences (if JSON is valid)
        if data is not None:
            unicode_errors = check_unicode_escapes(text, data)
            errors.extend(unicode_errors)

        if errors:
            print('\n'.join(errors))
            return False

        print("SUCCESS: File adheres to .editorconfig rules")
        return True

    except FileNotFoundError:
        print(f"ERROR: File '{json_file}' not found")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: check_editorconfig.py <json_file>")
        sys.exit(1)

    success = check_editorconfig(sys.argv[1])
    sys.exit(0 if success else 1)
