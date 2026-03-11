from MergePicFolders.utils import natural_sort_key

def test_natural_sort_key_simple_numbers():
    assert natural_sort_key("2") < natural_sort_key("10")
    assert natural_sort_key("02") < natural_sort_key("10")

def test_natural_sort_key_alphanumeric():
    assert natural_sort_key("file2.txt") < natural_sort_key("file10.txt")
    assert natural_sort_key("folder1") < natural_sort_key("folder2") < natural_sort_key("folder10")

def test_natural_sort_key_multiple_numeric_segments():
    assert natural_sort_key("1.2.2") < natural_sort_key("1.2.10")
    assert natural_sort_key("1.10.2") > natural_sort_key("1.2.10")

def test_natural_sort_key_case_insensitivity():
    # The current implementation uses .lower() for non-digit parts
    assert natural_sort_key("abc") == natural_sort_key("ABC")
    assert natural_sort_key("File2") < natural_sort_key("file10")

def test_natural_sort_key_no_numbers():
    assert natural_sort_key("abc") < natural_sort_key("def")

def test_natural_sort_key_empty_string():
    assert natural_sort_key("") == [""]

def test_natural_sort_key_only_numbers():
    assert natural_sort_key("123") == ["", 123, ""]

def test_natural_sort_list_sorting():
    items = ["file10.txt", "file2.txt", "file1.txt", "FILE1.txt"]
    sorted_items = sorted(items, key=natural_sort_key)
    # Expected: file1.txt and FILE1.txt will be equal in terms of sort key,
    # but their relative order will be preserved if using stable sort.
    # Actually, natural_sort_key("file1.txt") == ["file", 1, ".txt"]
    # and natural_sort_key("FILE1.txt") == ["file", 1, ".txt"]
    assert sorted_items[0].lower() == "file1.txt"
    assert sorted_items[1].lower() == "file1.txt"
    assert sorted_items[2] == "file2.txt"
    assert sorted_items[3] == "file10.txt"
