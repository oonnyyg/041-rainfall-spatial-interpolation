"""Error type carrying a location describing which input is invalid."""


class InputError(Exception):
    """Raised for invalid configuration or observation input.

    ``location`` identifies the offending field/row, e.g.
    ``"config: stations[2].x"`` or ``"observations.csv row 5"``.
    """

    def __init__(self, message: str, location: str = ""):
        if location:
            full = f"{location}: {message}"
        else:
            full = message
        super().__init__(full)
        self.message = message
        self.location = location
