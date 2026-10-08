def slugify(text: str) -> str:
    """Turn text into an ASCII slug."""
    cleaned = []
    previous_hyphen = False
    for char in text.strip():
        if char.isalnum():
            cleaned.append(char)
            previous_hyphen = False
        elif char in " _-" and cleaned and not previous_hyphen:
            cleaned.append("-")
            previous_hyphen = True
    return "".join(cleaned).strip("-")
