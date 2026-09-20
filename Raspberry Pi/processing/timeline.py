"""Small timestamped event log for experiments and playback."""


class EventTimeline:
    def __init__(self, events=None):
        self.events = list(events or [])

    def add(self, timestamp, kind, note="", payload=None, frame_index=None):
        event = {"timestamp": float(timestamp), "kind": kind, "note": note}
        if payload is not None:
            event["payload"] = payload
        if frame_index is not None:
            event["frame_index"] = int(frame_index)
        self.events.append(event)
        return event
