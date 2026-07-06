import threading
from pynput import keyboard
from app.services.logging.logger import logger

class SafetyEngine:
    """
    SafetyEngine is our security guard.
    If the user presses the 'Esc' key during autonomous execution,
    the SafetyEngine immediately sounds the alarm and stops the computer from moving.
    """
    def __init__(self):
        self.panic_triggered = False
        self.keyboard_listener = None

    def start_safety_monitor(self):
        """Starts monitoring for the Esc panic key."""
        self.panic_triggered = False
        logger.info("SafetyEngine: Monitor active. Press 'ESC' key at any time to PANIC stop.")
        
        self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
        self.keyboard_listener.start()

    def stop_safety_monitor(self):
        """Stops the safety monitor keyboard listener."""
        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
        logger.info("SafetyEngine: Monitor deactivated.")

    def check_safety(self):
        """Raises an exception if the panic key has been triggered."""
        if self.panic_triggered:
            logger.critical("SAFETY PANIC INTERRUPT: Stopping all execution immediately!")
            raise KeyboardInterrupt("Emergency panic button pressed!")

    def _on_key_press(self, key):
        # Check if the user pressed Escape
        if key == keyboard.Key.esc:
            self.panic_triggered = True
            logger.warning("SafetyEngine: Esc pressed! Emergency stop requested.")
