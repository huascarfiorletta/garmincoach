import json
import os
import keyring
from garminconnect import Garmin
from datetime import date, timedelta

from garmin_summarize import summarize_garmin_data

SERVICE_NAME = "GarminCoach"

# download additional useful fields
# optional to save password in keychain, default no, so that no permissions are requested (spooks users)


class GarminManager:
    def __init__(self, cache_dir=".cache"):
        self.cache_dir = cache_dir
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def save_password(self, email, password):
        keyring.set_password(SERVICE_NAME, email, password)
        print("Password saved to keychain.")

    def get_password(self, email):
        """
        Retrieves the password for a given email from the system keychain.
        If not found, prompts the user and saves it to the keychain.
        
        Note: This program can only access passwords it has stored itself
        under the specified SERVICE_NAME and email. It cannot access passwords
        stored by other, unrelated applications due to security restrictions.
        """
        password = keyring.get_password(SERVICE_NAME, email)
        return password

    def get_client(self, email, password):
        try:
            client = Garmin(email, password)
            client.login()
            return client
        except Exception as e:
            raise ConnectionError(f"Failed to authenticate with Garmin: {e}")

    def fetch_activity_laps(self, client, activity_id):
        """
        Fetch the real per-lap data for a single activity (lap-by-lap HR,
        power, cadence, pace, GCT, etc), as opposed to the split-type
        aggregates already embedded in the activity summary.

        Returns a list of lap dicts (Garmin's "lapDTOs"), or an empty list
        if the activity has no laps or the request fails.
        """
        try:
            splits = client.get_activity_splits(activity_id)
            return (splits or {}).get("lapDTOs", [])
        except Exception as e:
            print(f"Warning: could not fetch laps for activity {activity_id}: {e}")
            return []

    def fetch_user_data(self, email, password, days=7):
        cache_file = os.path.join(self.cache_dir, f"{email}_data.json")
        
        client = self.get_client(email, password)
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        activities = client.get_activities_by_date(
            start_date.isoformat(), end_date.isoformat(), ""
        )
        
        # Fetch real per-lap data for each activity and attach it before
        # pruning, so summarize_garmin_data() can keep it.
        for activity in activities:
            activity_id = activity.get("activityId")
            if activity_id is not None:
                activity["laps"] = self.fetch_activity_laps(client, activity_id)

        # Fetch some more details like stats
        stats = client.get_stats(end_date.isoformat())
        
        data = {
            "activities": activities,
            "stats": stats,
            "fetch_date": end_date.isoformat()
        }

        with open(cache_file, "w") as f:
            json.dump(data, f, indent=4)

        # Prune down to the coaching-relevant fields, keeping the same
        # structure/key names as the raw Garmin payload (see garmin_summarize.py)
        data = summarize_garmin_data(data)

        return data

    def get_cached_data(self, email):
        cache_file = os.path.join(self.cache_dir, f"{email}_data.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                return json.load(f)
        return None
