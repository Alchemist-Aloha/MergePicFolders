import re

def natural_sort_key(text):
    """
    Generate a natural sort key for a string containing numbers.

    This function splits text at number boundaries and converts numeric
    segments to integers, allowing for "natural" sorting where "2" comes
    before "10" when sorting filenames or folder names with numbers.

    Args:
        text (str): The text to convert to a natural sort key

    Returns:
        list: A list of tagged tuples ``(segment_type, value)`` where
              ``segment_type`` distinguishes text (0) from numbers (1),
              suitable for use as a sort key

    Example:
        "folder10" will be sorted after "folder2" when using this key
    """
    return [
        (1, int(part)) if part.isdigit() else (0, part.lower())
        for part in re.split(r'(\d+)', text)
    ]
