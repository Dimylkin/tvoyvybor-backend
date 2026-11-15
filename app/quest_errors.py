class QuestError(Exception):
    """A quest use-case failure that the HTTP layer can translate to a response."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)
