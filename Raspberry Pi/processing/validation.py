"""Simple one-to-one comparisons with engineering annotations."""

import math

import numpy as np

from processing.roi import roi_centre


def reposition_validation(events, detections, match_window_s):
    annotations = [event for event in events if event.get("kind") == "annotation" and
                   event.get("payload", {}).get("type") == "Known reposition"]
    candidates = []
    for annotation_index, annotation in enumerate(annotations):
        for detection_index, detection in enumerate(detections):
            error = detection["timestamp"] - annotation["timestamp"]
            if abs(error) <= match_window_s:
                candidates.append((abs(error), annotation_index, detection_index, error))
    used_annotations, used_detections = set(), set()
    matches = []
    for _distance, annotation_index, detection_index, error in sorted(candidates):
        if annotation_index in used_annotations or detection_index in used_detections:
            continue
        annotation = annotations[annotation_index]
        detection = detections[detection_index]
        matches.append({"annotation_timestamp": annotation["timestamp"],
                        "detection_timestamp": detection["timestamp"],
                        "timing_error_s": error,
                        "note": annotation.get("note", "")})
        used_annotations.add(annotation_index)
        used_detections.add(detection_index)
    missed = [event["timestamp"] for index, event in enumerate(annotations)
              if index not in used_annotations]
    unpaired = [event["timestamp"] for index, event in enumerate(detections)
                if index not in used_detections]
    return {"matched": len(matches), "missed": len(missed), "unpaired": len(unpaired),
            "matches": matches, "missed_annotations": missed,
            "unpaired_detections": unpaired}


def compare_hotspot_roi(roi, tracks):
    expected = {(int(row), int(col)) for row, col in np.argwhere(roi)}
    center = roi_centre(roi)
    choices = []
    for track in tracks:
        overlap = len(expected & track["cells"]) / len(expected)
        distance = math.dist(center, track["centroid"])
        choices.append((-overlap, distance, track["id"], track))
    if not choices:
        return {"detected": False, "hotspot_id": None, "overlap": 0.0,
                "centroid_distance_cells": None, "observed_duration_s": None,
                "prior_duration_unknown": True}
    _negative_overlap, distance, track_id, track = min(choices)
    overlap = -_negative_overlap
    return {"detected": overlap > 0, "hotspot_id": track_id if overlap > 0 else None,
            "overlap": overlap, "centroid_distance_cells": distance,
            "observed_duration_s": track["total_active_s"],
            "prior_duration_unknown": track["started_before_session"]}
