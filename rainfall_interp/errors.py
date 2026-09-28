"""Error type carrying a location for invalid input reporting."""


class InputError(Exception):
    """Raised when configuration or observation input is invalid.

    ``location`` is a human-readable pointer such as a JSON path or CSV
    ``row N`` descriptor; ``message`` describes the problem.
    """

    def __init__(self, message: str, location: str = "<input>") -> None:
        self.location = location
        super().__init__(f"{location}: {message}")
