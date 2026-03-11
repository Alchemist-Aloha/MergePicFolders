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
        list: A list where numeric segments are converted to integers,
              suitable for use as a sort key

    Example:
        "folder10" will be sorted after "folder2" when using this key
    """
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
