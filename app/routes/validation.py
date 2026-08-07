def parse_positive_int_set(values) -> set[int]:
    parsed = set()
    for value in values:
        try:
            parsed_value = int(value)
        except (TypeError, ValueError):
            raise ValueError("positive integer IDs are required") from None
        if parsed_value <= 0:
            raise ValueError("positive integer IDs are required")
        parsed.add(parsed_value)
    return parsed
