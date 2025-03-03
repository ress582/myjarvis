import os
import uuid
import time
import requests
import asyncio
import datetime
import json
import threading
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_socketio import SocketIO, emit
import edge_tts
import speech_recognition as sr
import numpy as np
from io import BytesIO
import wave
import google.generativeai as genai
from pyngrok import ngrok
from pyngrok.conf import PyngrokConfig
from database import Database
from weather import WeatherService

# Configure logging
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'jaws.log')

logger = logging.getLogger('jaws')
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(console_handler)

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=60)

# Initialize database
db = Database()

# Initialize weather service
weather_service = WeatherService()



# Import configuration
from config import config

# Configure Gemini
genai.configure(api_key=config.gemini_api_key)
model = genai.GenerativeModel('gemini-1.5-flash-latest')

# Ensure the audio directory exists
AUDIO_DIR = os.path.join("static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Initialize speech recognizer
recognizer = sr.Recognizer()
recognizer.energy_threshold = 300  # Lower threshold for better sensitivity
recognizer.dynamic_energy_threshold = False  # Disable dynamic adjustment for faster processing

# --- Helper Functions ---
def check_auth(pw):
    return config.verify_password(pw)

def clean_response_text(text):
    """Remove markdown formatting from response text."""
    text = text.replace('**', '').replace('*', '')
    text = text.replace('__', '').replace('_', '')
    text = text.replace('```', '').replace('`', '')
    text = text.replace('# ', '').replace('## ', '').replace('### ', '')
    text = text.replace('>', '').replace('- ', '')
    return text

def get_current_time_context():
    """Get current time context for the AI to use in responses."""
    now = datetime.datetime.now()
    current_time = now.strftime("%I:%M %p")
    current_day = now.strftime("%A")
    current_date = now.strftime("%B %d, %Y")
    
    return {
        "time": current_time,
        "day": current_day,
        "date": current_date,
        "hour": now.hour,
        "minute": now.minute,
        "is_morning": 5 <= now.hour < 12,
        "is_afternoon": 12 <= now.hour < 17,
        "is_evening": 17 <= now.hour < 22,
        "is_night": now.hour >= 22 or now.hour < 5
    }

async def text_to_speech(text):
    audio_filename = os.path.join(AUDIO_DIR, f"audio_{uuid.uuid4().hex}.mp3")
    communicate = edge_tts.Communicate(text, config.tts_voice)
    await communicate.save(audio_filename)
    return audio_filename

def process_audio_data(audio_data, sample_rate=16000):
    try:
        if isinstance(audio_data, BytesIO):
            audio = sr.AudioFile(audio_data)
        else:
            audio = sr.AudioFile(BytesIO(audio_data))
            
        with audio as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = recognizer.record(source)
            
        try:
            text = recognizer.recognize_google(audio_data, language='en-US')
            if text.strip():
                return text
            raise sr.UnknownValueError("No speech detected")
        except sr.UnknownValueError as e:
            app.logger.warning(f"Speech recognition failed: {str(e)}")
            return ""
        except sr.RequestError as e:
            app.logger.error(f"Could not request results from speech recognition service: {str(e)}")
            return ""
    except Exception as e:
        app.logger.error(f"Error processing audio: {str(e)}")
        return ""

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')



@app.route('/schedule/<int:item_id>', methods=['DELETE'])
def delete_schedule_item(item_id):
    password = request.args.get('password')
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        success = db.delete_schedule_item(item_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Item not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Error deleting schedule item: {str(e)}'}), 500

@app.route('/fitness/workout/<int:workout_id>', methods=['DELETE'])
def delete_workout(workout_id):
    password = request.args.get('password')
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        success = db.delete_workout(workout_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Workout not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Error deleting workout: {str(e)}'}), 500

@app.route('/ai/suggestions', methods=['GET'])
def get_ai_suggestions():
    password = request.args.get('password')
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        schedule_items = db.get_upcoming_schedule(7)
        workouts = db.get_recent_workouts(10)
        
        prompt = f"Based on the following user data, suggest 3 activities or tasks that would complement their routine. Keep each suggestion under 100 characters.\n\n"
        
        if schedule_items:
            prompt += "Upcoming schedule:\n"
            for item in schedule_items[:5]:
                prompt += f"- {item['title']} on {item['date']} at {item['time']}\n"
        
        if workouts:
            prompt += "\nRecent workouts:\n"
            for workout in workouts[:5]:
                prompt += f"- {workout['exercise']}: {workout['reps']} reps at {workout['weight']} kg on {workout['date']}\n"
        
        prompt += "\nProvide 3 suggestions in a JSON array format with 'title' and 'description' fields."
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        import re
        json_match = re.search(r'\[\s*\{.*\}\s*\]', response_text, re.DOTALL)
        
        suggestions = []
        if json_match:
            try:
                import json
                suggestions = json.loads(json_match.group(0))
            except:
                suggestions = [
                    {"title": "Stay hydrated", "description": "Drink at least 8 glasses of water throughout your day"},
                    {"title": "Take breaks", "description": "Remember to take short breaks during work to stretch and rest your eyes"},
                    {"title": "Plan meals", "description": "Prepare healthy meals in advance for the week"}
                ]
        else:
            suggestions = [
                {"title": "Stay hydrated", "description": "Drink at least 8 glasses of water throughout your day"},
                {"title": "Take breaks", "description": "Remember to take short breaks during work to stretch and rest your eyes"},
                {"title": "Plan meals", "description": "Prepare healthy meals in advance for the week"}
            ]
        
        return jsonify({
            'suggestions': suggestions
        })
    except Exception as e:
        return jsonify({'error': f'Error getting AI suggestions: {str(e)}'}), 500

@app.route('/upload_audio', methods=['POST'])
def upload_audio():
    response = jsonify({})
    response.headers.update({
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Accept, Authorization',
        'Content-Type': 'application/json'
    })

    if not check_auth(request.form.get('password')):
        response.data = jsonify({'error': 'Invalid password'}).data
        return response, 403

    if 'audio' not in request.files:
        response.data = jsonify({'error': 'No audio file provided'}).data
        return response, 400

    try:
        audio_file = request.files['audio']
        audio_data = audio_file.read()
        
        if len(audio_data) == 0:
            response.data = jsonify({'error': 'Empty audio file'}).data
            return response, 400

        if audio_file.filename.lower().endswith('.wav'):
            text = process_audio_data(BytesIO(audio_data))
        else:
            temp_wav = BytesIO()
            with wave.open(temp_wav, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(audio_data)
            
            temp_wav.seek(0)
            text = process_audio_data(temp_wav)
        
        if not text:
            response.data = jsonify({'error': 'Could not transcribe audio. Please speak clearly and try again'}).data
            return response, 400
            
        response.data = jsonify({'text': text}).data
        return response

    except Exception as e:
        app.logger.error(f'Error processing audio: {str(e)}')
        response.data = jsonify({'error': 'Server error processing audio'}).data
        return response, 500

@app.route('/ask', methods=['POST', 'OPTIONS'])
def ask():
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        response.headers.update({
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Accept, Authorization',
            'Access-Control-Max-Age': '3600'
        })
        return response

    data = request.json
    if not data or not check_auth(data.get('password')):
        response = jsonify({'error': 'Unauthorized'})
        response.headers.update({
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json'
        })
        return response, 403

    query = data.get('query', '')
    if not query:
        return jsonify({'error': 'No query provided'}), 400

    today = datetime.date.today()
    today_conversations = db.get_conversations_for_date(today)
    recent_context = "\n".join([f"User: {c['query']}\nJAWS: {c['response']}" for c in today_conversations[-5:]])
    
    time_context = get_current_time_context()
    
    long_term_memory = db.get_long_term_memory()
    memory_context = "\n".join(long_term_memory) if long_term_memory else "No significant memory points."
    
    jaws_prompt = (
        f"You are J.A.W.S. (Just A Wicked System), a sophisticated, articulate, and highly capable AI assistant. "
        f"Your tone is calm, respectful, and efficient, with a touch of subtle humor. You have an encyclopedic knowledge of technology, science, "
        f"and general information. Your responses are precise, clear, and designed to help with any task. "
        f"The user's name is {db.get_user_name()}, and you should address them by name occasionally to personalize the interaction otherwise by sir. "
        f"You are called JAWS. Always respond in a courteous and engaging manner sometimes making jokes. "
        f"IMPORTANT: DO NOT use any markdown formatting in your responses. Never use asterisks (*), underscores (_), or other special characters for emphasis or formatting. "
        
        f"\n\nCurrent Time Context:\n"
        f"Current time: {time_context['time']}\n"
        f"Current day: {time_context['day']}\n"
        f"Current date: {time_context['date']}\n"
        f"Time of day: {' Morning' if time_context['is_morning'] else ' Afternoon' if time_context['is_afternoon'] else ' Evening' if time_context['is_evening'] else ' Night'}\n"
        
        f"\n\nRecent conversation context:\n{recent_context}\n\n"
        
        f"\n\nLong-term memory key points:\n{memory_context}\n\n"
        
        f"Special Instructions:\n"
        f"1. SCHEDULING: You MUST handle scheduling in this EXACT format:\n"
        f"   - When user mentions any scheduling intent (meetings, appointments, events, reminders)\n"
        f"   - ALWAYS extract these components: name, date, time, description\n"
        f"   - REQUIRED FORMAT: schedule/[name]/[date]/[time]/[description]\n"
        f"   - Time MUST be in 24-hour format (e.g., 14:30 not 2:30 PM)\n"
        f"   - Examples:\n"
        f"     schedule/Team Meeting/tomorrow/14:30/Weekly project update\n"
        f"     schedule/Dentist/2024-03-15/09:00/Regular checkup\n"
        f"   - If any component is missing, ASK the user for it\n\n"
        f" - NO MATTER WHAT UNLESS ABSOLUTELY NECCESARY YOU DO NOT ASK FOR INFORMATION NOT REQUIRED YOU ASSUME OR FIGURE OUT YOURSELF\n"
        
        f"2. NOTIFICATIONS: You MUST handle notifications in this EXACT format:\n"
        f"   - When setting reminders or notifications\n"
        f"   - REQUIRED FORMAT: notify/[time in 24-hour]/[message]\n"
        f"   - Time MUST be in 24-hour format (HH:MM)\n"
        f"   - Examples:\n"
        f"     notify/14:00/Prepare for team meeting\n"
        f"     notify/08:45/Take morning medication\n"
        f"   - ALWAYS suggest setting a notification for scheduled events\n"
        f"   - Default to 30 minutes before events unless specified otherwise\n\n"
        
        f"3. PROACTIVE ASSISTANCE:\n"
        f"   - ALWAYS suggest relevant notifications for scheduled items\n"
        f"   - For meetings: suggest prep time notifications\n"
        f"   - For appointments: suggest travel time notifications\n"
        f"   - For tasks: suggest deadline reminders\n"
        f"   - Ask about setting recurring events when appropriate\n\n"
        
        f"4. TIME AWARENESS:\n"
        f"   - sometimes reference current time in responses IF APPROPRIATE NOT EVERY SECOND eg after it is a new day from last conversation\n"
        f"   - Use 24-hour format for ALL time references\n"
        f"   - Consider time of day when suggesting notification times\n"
        f"   - Account for SCHOOL hours when scheduling\n\n"
    )
    
    if any(word in query.lower() for word in ['workout', 'exercise', 'fitness', 'gym', 'training']):
        recent_workouts = db.get_recent_workouts(5)
        if recent_workouts:
            jaws_prompt += f"\nRecent workout history:\n"
            for workout in recent_workouts:
                jaws_prompt += f"- {workout['exercise']}: {workout['reps']} reps at {workout['weight']} kg on {workout['date']}\n"
    
    appointment_keywords = ['appointment', 'meeting', 'schedule', 'event', 'reminder']
    time_pattern = r'\b(?:at|on|for)\s+(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)|\d{1,2}(?::\d{2})?)\b'
    date_pattern = r'\b(?:today|tomorrow|next\s+\w+|\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?))\b'
    
    import re
    has_appointment = any(keyword in query.lower() for keyword in appointment_keywords)
    has_time = bool(re.search(time_pattern, query, re.IGNORECASE))
    has_date = bool(re.search(date_pattern, query, re.IGNORECASE))
    
    if has_appointment and (has_time or has_date):
        jaws_prompt += f"\nNote: The user mentioned an appointment. Please suggest adding it to their schedule and ask for any missing details (date/time).\n"
    
    try:
        full_prompt = jaws_prompt + query
        
        response = model.generate_content(full_prompt)
        response_text = response.text.strip()
        
        response_text = clean_response_text(response_text)
        
        # Check for scheduling and notification tags in the response
        schedule_match = re.search(r'schedule/([^/]+)/([^/]+)/([^/]+)/([^\n]+)', response_text)
        notify_match = re.search(r'notify/([^/]+)/([^\n]+)', response_text)
        
        if schedule_match:
            name = schedule_match.group(1)
            date = schedule_match.group(2)
            time = schedule_match.group(3)
            description = schedule_match.group(4)
            
            # Convert relative dates to absolute dates
            if date.lower() == 'today':
                date = datetime.date.today().isoformat()
            elif date.lower() == 'tomorrow':
                date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
            elif date.lower().startswith('next '):
                weekdays = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6}
                target_day = weekdays.get(date.lower().replace('next ', ''))
                if target_day is not None:
                    today = datetime.date.today()
                    days_ahead = target_day - today.weekday()
                    if days_ahead <= 0:
                        days_ahead += 7
                    date = (today + datetime.timedelta(days=days_ahead)).isoformat()
            
            # Add the schedule item
            schedule_item = db.add_schedule_item(name, date, time, description)
            response_text = response_text.replace(schedule_match.group(0), '')
            response_text += f"\n\nI've added this to your schedule: {name} on {date} at {time}"
        
        if notify_match:
            notify_time = notify_match.group(1)
            notify_message = notify_match.group(2)
            
            # Convert notify_time to datetime
            try:
                notify_time_obj = datetime.datetime.strptime(notify_time, '%H:%M').time()
                notify_date = datetime.date.today()
                notify_datetime = datetime.datetime.combine(notify_date, notify_time_obj)
                
                # If the time has already passed today, schedule for tomorrow
                if notify_datetime < datetime.datetime.now():
                    notify_date = notify_date + datetime.timedelta(days=1)
                    notify_datetime = datetime.datetime.combine(notify_date, notify_time_obj)
                
                # Add notification to schedule
                notification_title = "Notification"
                db.add_schedule_item(notification_title, notify_date.isoformat(), notify_time, notify_message)
                
                response_text = response_text.replace(notify_match.group(0), '')
                response_text += f"\n\nI'll notify you at {notify_time}: {notify_message}"
            except ValueError:
                app.logger.error(f'Invalid notification time format: {notify_time}')
                response_text += f"\n\nI couldn't set up the notification due to an invalid time format."
        
        db.add_conversation(query, response_text)
        
        audio_file_path = asyncio.run(text_to_speech(response_text))
        
        audio_url = "/" + audio_file_path.replace("\\", "/")
        
        def cleanup_audio():
            time.sleep(300)
            try:
                if os.path.exists(audio_file_path):
                    os.remove(audio_file_path)
            except Exception as e:
                app.logger.error(f'Error cleaning up audio file: {str(e)}')
        
        cleanup_thread = threading.Thread(target=cleanup_audio)
        cleanup_thread.daemon = True
        cleanup_thread.start()
        
        return jsonify({
            'response': response_text,
            'audio_file': audio_url
        })
        
    except Exception as e:
        return jsonify({
            'error': f'An error occurred: {str(e)}'
        }), 500

@app.route('/schedule', methods=['POST'])
def add_schedule():
    data = request.json
    if not data or not check_auth(data.get('password')):
        return jsonify({'error': 'Unauthorized'}), 403
    
    title = data.get('title')
    date = data.get('date')
    time = data.get('time')
    description = data.get('description', '')
    
    if not all([title, date, time]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        datetime.datetime.strptime(date, '%Y-%m-%d')
        
        schedule_item = db.add_schedule_item(title, date, time, description)
        return jsonify({
            'success': True,
            'item': schedule_item
        })
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    except Exception as e:
        return jsonify({'error': f'Error adding schedule: {str(e)}'}), 500

@app.route('/schedule/<date>', methods=['GET'])
def get_schedule(date):
    password = request.args.get('password')
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        datetime.datetime.strptime(date, '%Y-%m-%d')
        
        schedule = db.get_schedule_for_date(date)
        return jsonify({
            'date': date,
            'schedule': schedule
        })
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    except Exception as e:
        return jsonify({'error': f'Error getting schedule: {str(e)}'}), 500

@app.route('/fitness/workout', methods=['POST'])
def add_workout():
    data = request.json
    if not data or not check_auth(data.get('password')):
        return jsonify({'error': 'Unauthorized'}), 403
    
    exercise = data.get('exercise')
    reps = data.get('reps')
    weight = data.get('weight')
    date = data.get('date')
    
    if not all([exercise, reps, weight]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        reps = int(reps)
        weight = float(weight)
        
        workout = db.add_workout(exercise, reps, weight, date)
        return jsonify({
            'success': True,
            'workout': workout
        })
    except ValueError:
        return jsonify({'error': 'Invalid data types. Reps must be an integer, weight must be a number'}), 400
    except Exception as e:
        return jsonify({'error': f'Error adding workout: {str(e)}'}), 500

@app.route('/fitness/progress/<exercise>', methods=['GET'])
def get_fitness_progress(exercise):
    password = request.args.get('password')
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        progress = db.calculate_fitness_progress(exercise)
        response = jsonify(progress)
        response.headers.update({
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Accept, Authorization'
        })
        return response
    except Exception as e:
        error_response = jsonify({'error': f'Error getting progress: {str(e)}'})
        error_response.headers.update({
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Accept, Authorization'
        })
        return error_response, 500

@app.route('/nutrition/goals', methods=['POST'])
def set_nutrition_goals():
    data = request.json
    if not data or not check_auth(data.get('password')):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        calories = int(data.get('calories', 0))
        protein = int(data.get('protein', 0))
        carbs = int(data.get('carbs', 0))
        fats = int(data.get('fats', 0))
        goal_type = data.get('goal_type', '')
        
        goals = db.set_nutrition_goals(calories, protein, carbs, fats, goal_type)
        return jsonify({
            'success': True,
            'goals': goals
        })
    except ValueError:
        return jsonify({'error': 'Invalid data types. Nutritional values must be numbers'}), 400
    except Exception as e:
        return jsonify({'error': f'Error setting nutrition goals: {str(e)}'}), 500

@app.route('/nutrition/log', methods=['POST'])
def log_food_intake():
    data = request.json
    if not data or not check_auth(data.get('password')):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        food_name = data.get('food_name')
        calories = int(data.get('calories', 0))
        protein = float(data.get('protein', 0))
        carbs = float(data.get('carbs', 0))
        fats = float(data.get('fats', 0))
        
        if not food_name:
            return jsonify({'error': 'Food name is required'}), 400
        
        log_entry = db.log_food_intake(food_name, calories, protein, carbs, fats)
        return jsonify({
            'success': True,
            'log': log_entry
        })
    except ValueError:
        return jsonify({'error': 'Invalid data types. Nutritional values must be numbers'}), 400
    except Exception as e:
        return jsonify({'error': f'Error logging food intake: {str(e)}'}), 500

@app.route('/nutrition/weight', methods=['POST'])
def log_weight():
    data = request.json
    if not data or not check_auth(data.get('password')):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        weight = float(data.get('weight'))
        date = data.get('date')
        
        log_entry = db.log_weight(weight, date)
        return jsonify({
            'success': True,
            'log': log_entry
        })
    except ValueError:
        return jsonify({'error': 'Invalid data type. Weight must be a number'}), 400
    except Exception as e:
        return jsonify({'error': f'Error logging weight: {str(e)}'}), 500

@app.route('/nutrition/summary', methods=['GET'])
def get_nutrition_summary():
    password = request.args.get('password')
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        date = request.args.get('date')
        summary = db.get_nutrition_summary(date)
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': f'Error getting nutrition summary: {str(e)}'}), 500

@app.route('/nutrition/weight-history', methods=['GET'])
def get_weight_history():
    password = request.args.get('password')
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        days = int(request.args.get('days', 30))
        history = db.get_weight_history(days)
        return jsonify({
            'history': history
        })
    except ValueError:
        return jsonify({'error': 'Invalid days parameter'}), 400
    except Exception as e:
        return jsonify({'error': f'Error getting weight history: {str(e)}'}), 500

@app.route('/schedule/upcoming', methods=['GET'])
def get_upcoming_schedule():
    password = request.args.get('password')
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        days = int(request.args.get('days', 7))
        schedule = db.get_upcoming_schedule(days)
        
        # Add notification status for each item
        now = datetime.datetime.now()
        for item in schedule:
            item_datetime = datetime.datetime.strptime(f"{item['date']} {item['time']}", "%Y-%m-%d %H:%M")
            time_until = item_datetime - now
            
            # Add notification flags for different time thresholds
            item['notifications'] = {
                'one_day': time_until.total_seconds() <= 86400,  # 24 hours
                'one_hour': time_until.total_seconds() <= 3600,  # 1 hour
                'fifteen_min': time_until.total_seconds() <= 900  # 15 minutes
            }
        
        return jsonify({
            'schedule': schedule
        })
    except ValueError:
        return jsonify({'error': 'Invalid days parameter'}), 400
    except Exception as e:
        return jsonify({'error': f'Error getting upcoming schedule: {str(e)}'}), 500

@app.route('/movies/preference', methods=['POST'])
def add_movie_preference():
    data = request.json
    if not data or not check_auth(data.get('password')):
        return jsonify({'error': 'Unauthorized'}), 403
    
    genre = data.get('genre')
    title = data.get('title')
    rating = data.get('rating')
    
    if not genre:
        return jsonify({'error': 'Missing genre'}), 400
    
    try:
        db.add_movie_preference(genre, title, rating)
        return jsonify({
            'success': True
        })
    except Exception as e:
        return jsonify({'error': f'Error adding movie preference: {str(e)}'}), 500

@app.route('/movies/recommendations', methods=['GET'])
def get_movie_recommendations():
    password = request.args.get('password')
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        genres = db.get_movie_preferences()
        
        if not genres:
            return jsonify({
                'preferred_genres': [],
                'recommendations': []
            })
        
        top_genres = genres[:3]
        genres_text = ", ".join(top_genres)
        
        prompt = f"Suggest 5 movies in the following genres: {genres_text}. Return the results as a JSON array with each movie having 'title', 'genre', and 'description' fields. Keep descriptions brief (under 100 characters)."
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        import re
        json_match = re.search(r'\[\s*\{.*\}\s*\]', response_text, re.DOTALL)
        
        recommendations = []
        if json_match:
            try:
                import json
                recommendations = json.loads(json_match.group(0))
            except:
                recommendations = [
                    {"title": f"Recommendation for {genre}", "genre": genre, "description": "AI-generated recommendation"}
                    for genre in top_genres
                ]
        else:
            recommendations = [
                {"title": f"Recommendation for {genre}", "genre": genre, "description": "AI-generated recommendation"}
                for genre in top_genres
            ]
        
        return jsonify({
            'preferred_genres': genres,
            'recommendations': recommendations
        })
    except Exception as e:
        return jsonify({'error': f'Error getting movie recommendations: {str(e)}'}), 500

@app.route('/weather/current', methods=['GET'])
def get_current_weather():
    password = request.args.get('password')
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    city = request.args.get('city')
    if not city:
        return jsonify({'error': 'City parameter is required'}), 400
    
    units = request.args.get('units', 'metric')
    
    try:
        weather_data = weather_service.get_current_weather(city, units)
        return jsonify(weather_data)
    except Exception as e:
        return jsonify({'error': f'Error getting weather data: {str(e)}'}), 500

@app.route('/weather/forecast', methods=['GET'])
def get_weather_forecast():
    password = request.args.get('password')
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    city = request.args.get('city')
    if not city:
        return jsonify({'error': 'City parameter is required'}), 400
    
    days = request.args.get('days', 5, type=int)
    units = request.args.get('units', 'metric')
    
    try:
        forecast_data = weather_service.get_forecast(city, days, units)
        return jsonify(forecast_data)
    except Exception as e:
        return jsonify({'error': f'Error getting forecast data: {str(e)}'}), 500

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/fitness/advice', methods=['GET'])
def get_fitness_advice():
    password = request.args.get('password', '')
    if not password:
        return jsonify({
            'error': 'Please provide your access code to get fitness advice',
            'require_password': True
        }), 403
    
    if not check_auth(password):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        workouts = db.get_recent_workouts(10)
        
        if not workouts or len(workouts) < 2:
            return jsonify({
                'advice': 'Not enough workout data to provide personalized advice.',
                'recommendations': [
                    'Start tracking your workouts regularly',
                    'Aim for at least 3 workouts per week',
                    'Include both cardio and strength training'
                ]
            })
        
        prompt = f"Based on the following workout history, provide personalized fitness advice and 3-5 specific recommendations. Keep the advice under 200 words.\n\n"
        
        prompt += "Recent workouts:\n"
        for workout in workouts:
            prompt += f"- {workout['exercise']}: {workout['reps']} reps at {workout['weight']} kg on {workout['date']}\n"
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        import re
        
        advice = response_text
        recommendations = [
            "Continue your current workout routine",
            "Focus on proper form and technique",
            "Ensure adequate rest between workouts"
        ]
        
        rec_match = re.search(r'recommendations?:?\s*(?:\n\s*[-*]\s*(.+))+', response_text, re.IGNORECASE)
        if rec_match:
            all_recs = re.findall(r'[-*]\s*(.+)', response_text)
            if all_recs:
                recommendations = all_recs
                advice = re.sub(r'recommendations?:?\s*(?:\n\s*[-*]\s*.+)+', '', response_text, flags=re.IGNORECASE).strip()
        
        return jsonify({
            'advice': advice,
            'recommendations': recommendations
        })
    except Exception as e:
        return jsonify({'error': f'Error getting fitness advice: {str(e)}'}), 500

@app.route('/delete-audio', methods=['POST'])
def delete_audio():
    data = request.json
    if not data or not check_auth(data.get('password')):
        return jsonify({'error': 'Unauthorized'}), 403
    
    audio_file = data.get('audio_file')
    if not audio_file:
        return jsonify({'error': 'No audio file specified'}), 400
    
    # Ensure the audio file path is within the static/audio directory
    if not audio_file.startswith('/static/audio/'):
        return jsonify({'error': 'Invalid audio file path'}), 400
    
    # Convert URL path to absolute file system path
    file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), audio_file.lstrip('/')))
    
    # Verify the file path is within the static/audio directory
    audio_dir = os.path.abspath(AUDIO_DIR)
    if not file_path.startswith(audio_dir):
        return jsonify({'error': 'Invalid audio file path'}), 400
    
    try:
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            # Verify file was actually deleted
            if os.path.exists(file_path):
                raise Exception('Failed to delete file')
            return jsonify({'success': True, 'message': 'Audio file deleted successfully'})
        else:
            return jsonify({'error': 'Audio file not found'}), 404
    except Exception as e:
        app.logger.error(f'Error deleting audio file {file_path}: {str(e)}')
        return jsonify({'error': f'Server error deleting audio file: {str(e)}'}), 500

if __name__ == '__main__':
    # Check if running on Render or similar cloud platform
    is_production = os.environ.get('RENDER') == 'true'
    port = int(os.environ.get('PORT', 3000))
    
    if is_production:
        # Cloud deployment mode - no ngrok needed
        print(f"Running in production mode on port {port}")
        socketio.run(app, host='0.0.0.0', port=port, debug=False)
    else:
        # Local development mode - use ngrok
        ngrok_config = PyngrokConfig()
        
        # Set ngrok auth token if available
        if hasattr(config, 'ngrok_auth_token') and config.ngrok_auth_token:
            ngrok_config.auth_token = config.ngrok_auth_token
        
        # Start ngrok tunnel
        tunnel = None
        try:
            # Use port 3000 for better compatibility with UserLand
            port = 3000 if os.path.exists('/data/data/tech.ula') else 5000
            tunnel = ngrok.connect(port, config=ngrok_config)
            print(f"\nNgrok tunnel established! Public URL: {tunnel}")
        except Exception as e:
            print(f"Error establishing ngrok tunnel: {str(e)}")
            tunnel = None

        try:
            # Run the Flask app with conditional SSL
            is_userland = os.path.exists('/data/data/tech.ula')
            ssl_files_exist = os.path.exists('ssl/cert.pem') and os.path.exists('ssl/key.pem')
            
            if is_userland or not ssl_files_exist:
                print("Running without SSL (UserLand mode or SSL files not found)")
                socketio.run(app, host='0.0.0.0', port=port, debug=False)
            else:
                print("Running with SSL")
                socketio.run(app, host='0.0.0.0', port=port, debug=True, ssl_context=('ssl/cert.pem', 'ssl/key.pem'))
        finally:
            # Ensure ngrok tunnel is closed when the server stops
            if tunnel:
                print("Closing ngrok tunnel...")
                try:
                    ngrok.disconnect(tunnel)
                    ngrok.kill()
                except Exception as e:
                    print(f"Error closing ngrok tunnel: {str(e)}")
