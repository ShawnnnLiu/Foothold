"""Recording sleeper twin: tests never really sleep, they assert the pacing."""


class RecordingSleeper:
    def __init__(self) -> None:
        self.durations: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.durations.append(seconds)
