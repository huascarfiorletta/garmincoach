import json
import os
import keyring
from garminconnect import Garmin
from datetime import date, timedelta

SERVICE_NAME = "GarminCoach"

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

    def fetch_user_data(self, email, password, days=7):
        cache_file = os.path.join(self.cache_dir, f"{email}_data.json")
        
        client = self.get_client(email, password)
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        activities = client.get_activities_by_date(
            start_date.isoformat(), end_date.isoformat(), ""
        )
        
        # Fetch some more details like stats
        stats = client.get_stats(end_date.isoformat())
        
        data = {
            "activities": activities,
            "stats": stats,
            "fetch_date": end_date.isoformat()
        }
        
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=4)
            
        return data

    def get_cached_data(self, email):
        cache_file = os.path.join(self.cache_dir, f"{email}_data.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                return json.load(f)
        return None
