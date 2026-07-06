import os
import yaml

class ConfigManager:
    """
    The ConfigManager reads our 'config.yaml' recipe book.
    It makes sure all parts of our application know their settings.
    """
    def __init__(self, config_path=None):
        # By default, find the config.yaml in the project root directory
        if config_path is None:
            # __file__ is the path to this python file. We go up 3 folders to reach the root.
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            config_path = os.path.join(project_root, "config.yaml")
        
        self.config_path = config_path
        self._config = {}
        self.load_config()

    def load_config(self):
        """Loads configuration from yaml file, or uses defaults if file not found."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    self._config = yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Error loading config.yaml: {e}. Using defaults.")
                self._config = {}
        else:
            print(f"config.yaml not found at {self.config_path}. Using defaults.")
            self._config = {}
            
        # Ensure default directories exist
        self._ensure_directories()

    def get(self, key_path, default=None):
        """
        Get a config value using dot notation (e.g., 'observation.screenshot_interval').
        This makes it easy to look deep inside the configuration.
        """
        keys = key_path.split('.')
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def _ensure_directories(self):
        """Creates the folders specified in the config if they do not exist yet."""
        # Get log directory and observation output directory
        log_dir = self.get("logging.log_dir", "data/logs")
        obs_dir = self.get("observation.output_dir", "data/observations")
        
        # Create them locally relative to project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        
        full_log_dir = os.path.join(project_root, log_dir)
        full_obs_dir = os.path.join(project_root, obs_dir)
        
        os.makedirs(full_log_dir, exist_ok=True)
        os.makedirs(full_obs_dir, exist_ok=True)

# Create a singleton instance so we can import it directly elsewhere
config_manager = ConfigManager()
