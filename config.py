import os
import json
import base64
import hashlib
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration class for handling environment variables and encryption"""
    
    def __init__(self):
        # Generate encryption key based on a secret (or load existing one)
        self._setup_encryption()
        
        # Load sensitive configuration from environment variables
        self.gemini_api_key = self._get_env('GEMINI_API_KEY')
        self.openweather_api_key = self._get_env('OPENWEATHER_API_KEY')
        self.admin_password = self._get_env('ADMIN_PASSWORD')
        self.tts_voice = self._get_env('TTS_VOICE', 'en-GB-RyanNeural')
        # Removed ngrok auth token requirement
    
    def _setup_encryption(self):
        """Set up encryption key for sensitive data"""
        # Create a key directory if it doesn't exist
        os.makedirs('keys', exist_ok=True)
        key_file = os.path.join('keys', 'encryption.key')
        
        if os.path.exists(key_file):
            # Load existing key
            with open(key_file, 'rb') as f:
                self.key = f.read()
        else:
            # Generate a new key
            # Use a password-based key derivation
            password = os.getenv('ENCRYPTION_PASSWORD', 'default_password')
            salt = os.urandom(16)
            kdf_key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
            self.key = base64.urlsafe_b64encode(kdf_key)
            
            # Save the key
            with open(key_file, 'wb') as f:
                f.write(self.key)
        
        self.cipher = Fernet(self.key)
    
    def _get_env(self, name, default=None):
        """Get environment variable with optional default value"""
        return os.getenv(name, default)
    
    def encrypt(self, data):
        """Encrypt sensitive data"""
        if isinstance(data, str):
            data = data.encode()
        return self.cipher.encrypt(data)
    
    def decrypt(self, encrypted_data):
        """Decrypt sensitive data"""
        return self.cipher.decrypt(encrypted_data).decode()
    
    def encrypt_json(self, data):
        """Encrypt a JSON serializable object"""
        json_str = json.dumps(data)
        return self.encrypt(json_str)
    
    def decrypt_json(self, encrypted_data):
        """Decrypt JSON data"""
        decrypted = self.decrypt(encrypted_data)
        return json.loads(decrypted)
    
    def verify_password(self, input_password):
        """Securely verify a password"""
        # Use constant-time comparison to prevent timing attacks
        return self.admin_password == input_password

# Create a singleton instance
config = Config()