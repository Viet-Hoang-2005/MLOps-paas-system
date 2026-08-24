import uuid


class UUIDConverter:
    regex = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"

    def to_python(self, value):
        return uuid.UUID(value)

    def to_url(self, value):
        return str(value)
