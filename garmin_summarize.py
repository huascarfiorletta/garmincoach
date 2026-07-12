"""
Takes the raw Garmin Connect JSON blob (top-level "activities": [...] and
"stats": {...}) and returns a much smaller JSON with the SAME structure,
field names, nesting, and value formats as the original -- just with the
unneeded keys stripped out. Nothing is renamed, reshaped, unit-converted,
or reformatted.

Conceptually each kept field corresponds to a JSONPath like:
    $.activities[*].distance
    $.activities[*].hrTimeInZone_4
    $.activities[*].splitSummaries[*].averageSpeed
    $.stats.bodyBatteryHighestValue
    $.stats.bodyBatteryActivityEventList[*].bodyBatteryImpact

The implementation below does plain key-whitelisting (no jsonpath-ng
dependency needed) which is equivalent for this "pick these fields, keep
everything else's shape" use case, and is easier to read/edit.

LAP DATA
--------
The activity-summary payload itself has no true per-km/lap array with
HR, power, cadence, GCT, etc -- only:
  - lapCount: a number
  - splitSummaries[]: distance/duration/speed/elevation aggregated by
    *split type* (e.g. all RUN splits combined, all WALK splits combined)

Real per-lap data (lap 1, lap 2, ... each with its own HR/power/cadence/
GCT) comes from a separate Garmin endpoint -- `get_activity_splits()` in
python-garminconnect, which returns {"lapDTOs": [...]}. If the caller
attaches that list to an activity as `activity["laps"]` *before* calling
summarize_garmin_data(), it gets pruned to LAP_FIELDS and kept in the
output the same way splitSummaries is. If no "laps" key is present,
it's simply omitted -- nothing is fabricated.
"""

import json


# --------------------------------------------------------------------------
# field whitelists (original Garmin key names, unchanged)
# --------------------------------------------------------------------------

ACTIVITY_FIELDS = [
    # identity / context
    "activityId", "activityName", "startTimeLocal", "locationName",
    # summary metrics
    "distance", "duration", "elevationGain", "elevationLoss",
    "averageSpeed", "maxSpeed", "calories",
    "averageHR", "maxHR",
    "avgPower", "maxPower", "normPower",
    "averageRunningCadenceInStepsPerMinute", "maxRunningCadenceInStepsPerMinute",
    "averageBikingCadenceInRevPerMinute", "maxBikingCadenceInRevPerMinute",
    "avgStrideLength",
    "avgVerticalOscillation", "avgVerticalRatio",
    "avgGroundContactTime", "avgGroundContactBalance",
    "aerobicTrainingEffect", "anaerobicTrainingEffect", "trainingEffectLabel",
    "activityTrainingLoad",
    "vO2MaxValue",
    "lapCount", "hasSplits",
    "hrTimeInZone_1", "hrTimeInZone_2", "hrTimeInZone_3", "hrTimeInZone_4", "hrTimeInZone_5",
    "powerTimeInZone_1", "powerTimeInZone_2", "powerTimeInZone_3", "powerTimeInZone_4",
    "powerTimeInZone_5", "powerTimeInZone_6", "powerTimeInZone_7",
    "splitSummaries",
]

ACTIVITY_TYPE_FIELDS = ["typeKey"]

SPLIT_FIELDS = [
    "splitType", "noOfSplits", "distance", "duration",
    "averageSpeed", "maxSpeed",
    "totalAscent", "elevationLoss", "averageElevationGain", "maxElevationGain",
]

STATS_FIELDS = [
    "calendarDate", "restingHeartRate", "lastSevenDaysAvgRestingHeartRate",
    # body battery
    "bodyBatteryHighestValue", "bodyBatteryLowestValue", "bodyBatteryMostRecentValue",
    "bodyBatteryChargedValue", "bodyBatteryDrainedValue",
    "bodyBatteryDuringSleep", "bodyBatteryAtWakeTime",
    # stress
    "averageStressLevel", "maxStressLevel",
    "restStressPercentage", "lowStressPercentage", "mediumStressPercentage", "highStressPercentage",
    # sleep
    "sleepingSeconds",
    # respiration
    "avgWakingRespirationValue", "highestRespirationValue",
    "lowestRespirationValue", "latestRespirationValue",
    # SpO2
    "averageSpo2", "lowestSpo2", "latestSpo2",
    # recovery events
    "bodyBatteryActivityEventList",
]

RECOVERY_EVENT_FIELDS = [
    "eventType", "eventStartTimeGmt", "durationInMilliseconds",
    "bodyBatteryImpact", "shortFeedback", "activityName",
]


# --------------------------------------------------------------------------
# generic helper
# --------------------------------------------------------------------------

def _pick(d: dict, keys: list) -> dict:
    """Return a new dict containing only the given keys (that are present),
    preserving original key names and values untouched."""
    return {k: d[k] for k in keys if k in d}


# --------------------------------------------------------------------------
# per-section filters
# --------------------------------------------------------------------------

def _filter_activity(activity: dict) -> dict:
    out = _pick(activity, ACTIVITY_FIELDS)

    if "activityType" in activity:
        out["activityType"] = _pick(activity["activityType"], ACTIVITY_TYPE_FIELDS)

    if "splitSummaries" in activity:
        out["splitSummaries"] = [_pick(s, SPLIT_FIELDS) for s in activity["splitSummaries"]]

    if "laps" in activity:
        out["laps"] = activity["laps"]

    return out


def _filter_stats(stats: dict) -> dict:
    out = _pick(stats, STATS_FIELDS)

    if "bodyBatteryActivityEventList" in stats:
        out["bodyBatteryActivityEventList"] = [
            _pick(e, RECOVERY_EVENT_FIELDS) for e in stats["bodyBatteryActivityEventList"]
        ]

    return out


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------

def summarize_garmin_data(data: dict, include_wellness: bool = True) -> dict:
    """
    Prune the raw Garmin JSON down to the useful coaching fields, keeping
    the original structure, key names, nesting, and value formats intact.

    Parameters
    ----------
    data : dict
        Raw payload with "activities": [...] and "stats": {...}.
    include_wellness : bool
        If True (default), keep the optional "stats" block (body battery,
        stress, sleep, respiration, SpO2, recovery events). If False, it's
        omitted entirely.

    Returns
    -------
    dict with the same top-level shape as the input ("fetch_date",
    "activities", "stats"), just pruned to relevant fields.
    """
    result = {}

    if "fetch_date" in data:
        result["fetch_date"] = data["fetch_date"]

    if "activities" in data:
        result["activities"] = [_filter_activity(a) for a in data["activities"]]

    if include_wellness and "stats" in data:
        result["stats"] = _filter_stats(data["stats"])

    return result


if __name__ == "__main__":
    import sys

    src_path = sys.argv[1] if len(sys.argv) > 1 else "garmin_raw.json"
    with open(src_path, "r") as f:
        raw = json.load(f)

    compact = summarize_garmin_data(raw)
    print(json.dumps(compact, indent=2))