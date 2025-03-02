import os
import json
import datetime
from typing import Dict, List, Any, Optional

class Database:
    """Database class for storing user data, conversation history, schedules, and fitness tracking."""
    
    def __init__(self, db_file="user_data.json"):
        self.db_file = db_file
        self.data = self._load_data()
        
        # Initialize default data structure if it doesn't exist
        if not self.data:
            self.data = {
                "user": {
                    "name": "Rowan",  # Default name as per requirements
                    "preferences": {}
                },
                "conversations": [],
                "schedule": [],
                "fitness": {
                    "workouts": [],
                    "goals": {},
                    "nutrition": {
                        "goals": {
                            "calories": 0,
                            "protein": 0,
                            "carbs": 0,
                            "fats": 0,
                            "goal_type": ""
                        },
                        "logs": [],
                        "weight_logs": []
                    }
                },
                "movie_preferences": []
            }
            self._save_data()
    
    def _load_data(self) -> Dict:
        """Load data from the JSON file."""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    def _save_data(self) -> None:
        """Save data to the JSON file."""
        with open(self.db_file, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def add_conversation(self, query: str, response: str) -> None:
        """Add a conversation entry to the history."""
        conversation = {
            "timestamp": datetime.datetime.now().isoformat(),
            "query": query,
            "response": response,
            "key_points": self._extract_key_points(query, response)
        }
        self.data["conversations"].append(conversation)
        
        # Keep only the last 5 conversations within 24 hours for efficiency
        self._prune_conversations()
            
        self._save_data()
        
    def _extract_key_points(self, query: str, response: str) -> list:
        """Extract key points from a conversation for long-term memory."""
        # Simple extraction of potential key information based on keywords
        key_points = []
        
        # Keywords that might indicate important information
        important_keywords = [
            "remember", "don't forget", "important", "schedule", "appointment", 
            "meeting", "event", "reminder", "preference", "like", "dislike",
            "favorite", "birthday", "anniversary", "deadline"
        ]
        
        # Check for sentences containing important keywords
        combined_text = query + " " + response
        sentences = combined_text.split(".")
        
        for sentence in sentences:
            sentence = sentence.strip()
            if any(keyword in sentence.lower() for keyword in important_keywords) and len(sentence) > 10:
                key_points.append(sentence)
                
        return key_points
    
    def _prune_conversations(self) -> None:
        """Prune conversations to keep only the last 5 within 24 hours."""
        now = datetime.datetime.now()
        
        # First, extract key points from older conversations to preserve important information
        preserved_key_points = []
        conversations_to_keep = []
        
        for conv in self.data["conversations"]:
            try:
                conv_time = datetime.datetime.fromisoformat(conv["timestamp"])
                time_diff = now - conv_time
                
                # If conversation is within 24 hours, keep it for context
                if time_diff.total_seconds() < 24 * 60 * 60:
                    conversations_to_keep.append(conv)
                # Otherwise, preserve any key points
                elif "key_points" in conv and conv["key_points"]:
                    preserved_key_points.extend(conv["key_points"])
            except (ValueError, TypeError):
                # If timestamp parsing fails, keep the conversation to be safe
                conversations_to_keep.append(conv)
        
        # Keep only the 5 most recent conversations
        if len(conversations_to_keep) > 5:
            conversations_to_keep = conversations_to_keep[-5:]
            
        # Store the preserved key points in a special memory section if not already there
        if "long_term_memory" not in self.data:
            self.data["long_term_memory"] = {}
            
        if "key_points" not in self.data["long_term_memory"]:
            self.data["long_term_memory"]["key_points"] = []
            
        # Add unique key points to long-term memory
        for point in preserved_key_points:
            if point not in self.data["long_term_memory"]["key_points"]:
                self.data["long_term_memory"]["key_points"].append(point)
                
        # Replace conversations with pruned list
        self.data["conversations"] = conversations_to_keep
    
    def get_recent_conversations(self, limit: int = 5) -> List[Dict]:
        """Get the most recent conversations (default: last 5)."""
        return self.data["conversations"][-limit:]
        
    def get_long_term_memory(self) -> List[str]:
        """Get the preserved key points from long-term memory."""
        if "long_term_memory" in self.data and "key_points" in self.data["long_term_memory"]:
            return self.data["long_term_memory"]["key_points"]
        return []
    
    def get_conversations_for_date(self, date: datetime.date) -> List[Dict]:
        """Get conversations for a specific date."""
        date_str = date.isoformat().split('T')[0]  # Get just the date part
        return [conv for conv in self.data["conversations"] 
                if conv["timestamp"].startswith(date_str)]
    
    def add_schedule_item(self, title: str, date: str, time: str, description: str = "") -> Dict:
        """Add a scheduled item to the calendar."""
        schedule_item = {
            "id": len(self.data["schedule"]) + 1,
            "title": title,
            "date": date,
            "time": time,
            "description": description,
            "completed": False
        }
        self.data["schedule"].append(schedule_item)
        self._save_data()
        return schedule_item
    
    def get_schedule_for_date(self, date: str) -> List[Dict]:
        """Get all scheduled items for a specific date."""
        return [item for item in self.data["schedule"] if item["date"] == date]
    
    def get_upcoming_schedule(self, days: int = 7) -> List[Dict]:
        """Get upcoming scheduled items for the next X days."""
        today = datetime.date.today()
        upcoming_dates = [(today + datetime.timedelta(days=i)).isoformat() for i in range(days)]
        return [item for item in self.data["schedule"] if item["date"] in upcoming_dates]
    
    def mark_schedule_completed(self, schedule_id: int, completed: bool = True) -> bool:
        """Mark a scheduled item as completed or not completed."""
        for item in self.data["schedule"]:
            if item["id"] == schedule_id:
                item["completed"] = completed
                self._save_data()
                return True
        return False
        
    def delete_schedule_item(self, schedule_id: int) -> bool:
        """Delete a scheduled item by its ID."""
        for i, item in enumerate(self.data["schedule"]):
            if item["id"] == schedule_id:
                self.data["schedule"].pop(i)
                self._save_data()
                return True
        return False
        
    def delete_workout(self, workout_id: int) -> bool:
        """Delete a workout entry by its ID."""
        for i, workout in enumerate(self.data["fitness"]["workouts"]):
            if workout["id"] == workout_id:
                self.data["fitness"]["workouts"].pop(i)
                self._save_data()
                return True
        return False
    
    def add_workout(self, exercise: str, reps: int, weight: float, date: str = None) -> Dict:
        """Add a workout entry to fitness tracking."""
        if date is None:
            date = datetime.date.today().isoformat()
            
        workout = {
            "id": len(self.data["fitness"]["workouts"]) + 1,
            "date": date,
            "exercise": exercise,
            "reps": reps,
            "weight": weight
        }
        self.data["fitness"]["workouts"].append(workout)
        self._save_data()
        return workout
    
    def get_exercise_progress(self, exercise: str) -> List[Dict]:
        """Get progress history for a specific exercise."""
        return [w for w in self.data["fitness"]["workouts"] if w["exercise"].lower() == exercise.lower()]
    
    def calculate_fitness_progress(self, exercise: str) -> Dict:
        """Calculate progress for a specific exercise."""
        exercise_data = self.get_exercise_progress(exercise)
        
        if not exercise_data or len(exercise_data) < 2:
            return {"status": "insufficient_data", "message": "Need more workout data to calculate progress"}
        
        # Sort by date
        exercise_data.sort(key=lambda x: x["date"])
        
        first_workout = exercise_data[0]
        latest_workout = exercise_data[-1]
        
        # Calculate progress
        weight_change = latest_workout["weight"] - first_workout["weight"]
        weight_change_percent = (weight_change / first_workout["weight"]) * 100 if first_workout["weight"] > 0 else 0
        
        reps_change = latest_workout["reps"] - first_workout["reps"]
        reps_change_percent = (reps_change / first_workout["reps"]) * 100 if first_workout["reps"] > 0 else 0
        
        # Calculate volume (weight × reps) change
        first_volume = first_workout["weight"] * first_workout["reps"]
        latest_volume = latest_workout["weight"] * latest_workout["reps"]
        volume_change_percent = ((latest_volume - first_volume) / first_volume) * 100 if first_volume > 0 else 0
        
        return {
            "status": "success",
            "exercise": exercise,
            "first_date": first_workout["date"],
            "latest_date": latest_workout["date"],
            "weight_change": weight_change,
            "weight_change_percent": weight_change_percent,
            "reps_change": reps_change,
            "reps_change_percent": reps_change_percent,
            "volume_change_percent": volume_change_percent,
            "on_track": volume_change_percent > 0
        }
    
    def add_movie_preference(self, genre: str, title: str = None, rating: int = None) -> None:
        """Add a movie preference to help with recommendations."""
        preference = {
            "timestamp": datetime.datetime.now().isoformat(),
            "genre": genre
        }
        
        if title:
            preference["title"] = title
            
        if rating and 1 <= rating <= 10:
            preference["rating"] = rating
            
        self.data["movie_preferences"].append(preference)
        self._save_data()
    
    def get_movie_preferences(self) -> List[str]:
        """Get list of preferred movie genres based on history."""
        genres = {}
        
        for pref in self.data["movie_preferences"]:
            genre = pref["genre"]
            if genre in genres:
                genres[genre] += 1
            else:
                genres[genre] = 1
                
        # Sort genres by frequency
        sorted_genres = sorted(genres.items(), key=lambda x: x[1], reverse=True)
        return [genre for genre, _ in sorted_genres]
    
    def delete_schedule_item(self, item_id: int) -> bool:
        """Delete a schedule item by its ID."""
        for i, item in enumerate(self.data["schedule"]):
            if item["id"] == item_id:
                self.data["schedule"].pop(i)
                self._save_data()
                return True
        return False

    def delete_workout(self, workout_id: int) -> bool:
        """Delete a workout by its ID."""
        for i, workout in enumerate(self.data["fitness"]["workouts"]):
            if workout["id"] == workout_id:
                self.data["fitness"]["workouts"].pop(i)
                self._save_data()
                return True
        return False

    def get_recent_workouts(self, limit: int = 10) -> List[Dict]:
        """Get the most recent workouts."""
        workouts = sorted(self.data["fitness"]["workouts"], key=lambda x: x["date"], reverse=True)
        return workouts[:limit]

    def get_user_name(self) -> str:
        """Get the user's name."""
        return self.data["user"]["name"]
    
    def set_user_preference(self, key: str, value: Any) -> None:
        """Set a user preference."""
        self.data["user"]["preferences"][key] = value
        self._save_data()
    
    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        return self.data["user"]["preferences"].get(key, default)

    def set_nutrition_goals(self, calories: int, protein: int, carbs: int, fats: int, goal_type: str) -> Dict:
        """Set nutrition goals for the user."""
        nutrition_goals = {
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fats": fats,
            "goal_type": goal_type  # 'cut', 'bulk', or 'maintain'
        }
        self.data["fitness"]["nutrition"]["goals"] = nutrition_goals
        self._save_data()
        return nutrition_goals

    def log_food_intake(self, food_name: str, calories: int, protein: float = 0, carbs: float = 0, fats: float = 0) -> Dict:
        """Log food intake with nutritional information."""
        log_entry = {
            "id": len(self.data["fitness"]["nutrition"]["logs"]) + 1,
            "timestamp": datetime.datetime.now().isoformat(),
            "food_name": food_name,
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fats": fats
        }
        self.data["fitness"]["nutrition"]["logs"].append(log_entry)
        self._save_data()
        return log_entry

    def log_weight(self, weight: float, date: str = None) -> Dict:
        """Log user's weight measurement."""
        if date is None:
            date = datetime.date.today().isoformat()

        log_entry = {
            "id": len(self.data["fitness"]["nutrition"]["weight_logs"]) + 1,
            "date": date,
            "weight": weight
        }
        self.data["fitness"]["nutrition"]["weight_logs"].append(log_entry)
        self._save_data()
        return log_entry

    def get_nutrition_summary(self, date: str = None) -> Dict:
        """Get nutrition summary for a specific date."""
        if date is None:
            date = datetime.date.today().isoformat()

        # Filter logs for the specified date
        daily_logs = [log for log in self.data["fitness"]["nutrition"]["logs"]
                     if log["timestamp"].startswith(date)]

        # Calculate totals
        total_calories = sum(log["calories"] for log in daily_logs)
        total_protein = sum(log["protein"] for log in daily_logs)
        total_carbs = sum(log["carbs"] for log in daily_logs)
        total_fats = sum(log["fats"] for log in daily_logs)

        goals = self.data["fitness"]["nutrition"]["goals"]
        
        return {
            "date": date,
            "total_calories": total_calories,
            "total_protein": total_protein,
            "total_carbs": total_carbs,
            "total_fats": total_fats,
            "remaining_calories": goals["calories"] - total_calories if goals["calories"] > 0 else 0,
            "remaining_protein": goals["protein"] - total_protein if goals["protein"] > 0 else 0,
            "goal_type": goals["goal_type"],
            "logs": daily_logs
        }

    def get_weight_history(self, days: int = 30) -> List[Dict]:
        """Get weight history for the specified number of days."""
        weight_logs = sorted(self.data["fitness"]["nutrition"]["weight_logs"],
                           key=lambda x: x["date"])
        return weight_logs[-days:] if days > 0 else weight_logs

    def reset_daily_nutrition(self) -> None:
        """Reset daily nutrition logs and archive them."""
        today = datetime.date.today()
        yesterday = (today - datetime.timedelta(days=1)).isoformat()
        
        # Get yesterday's logs
        yesterday_logs = [log for log in self.data["fitness"]["nutrition"]["logs"]
                         if log["timestamp"].startswith(yesterday)]
        
        # Archive yesterday's logs if any exist
        if yesterday_logs:
            if "nutrition_history" not in self.data["fitness"]:
                self.data["fitness"]["nutrition_history"] = {}
            
            self.data["fitness"]["nutrition_history"][yesterday] = {
                "logs": yesterday_logs,
                "summary": self.get_nutrition_summary(yesterday)
            }
        
        # Clear current logs that are older than today
        self.data["fitness"]["nutrition"]["logs"] = [
            log for log in self.data["fitness"]["nutrition"]["logs"]
            if log["timestamp"].startswith(today.isoformat())
        ]
        
        self._save_data()