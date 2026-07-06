import os
import json
import time
import threading
from datetime import datetime
from PIL import ImageGrab
from pynput import mouse, keyboard

from app.services.config.config_manager import config_manager
from app.services.logging.logger import logger
from app.services.events.event_bus import event_bus
from app.services.utilities.window_helper import get_active_window_title

class ObservationEngine:
    """
    ObservationEngine is the observer (or the camera cook) of ECHO.
    It runs background listeners to capture keyboard, mouse, and screen activity,
    and saves them as a structured learning demonstration session.
    """
    def __init__(self):
        self._is_observing = False
        
        # Thread handles and synchronization
        self.mouse_listener = None
        self.keyboard_listener = None
        self.screenshot_thread = None
        self._lock = threading.Lock()
        
        # Session state
        self.session_id = None
        self.session_dir = None
        self.start_time_epoch = 0.0
        self.events = []
        
        # Track active modifier keys for shortcuts (e.g. Ctrl, Shift, Alt)
        self.active_modifiers = set()
        self._drag_start = None

    def start_observation(self):
        """Starts recording mouse clicks, movement, keystrokes, and screen captures."""
        with self._lock:
            if self._is_observing:
                logger.warning("ObservationEngine: Already recording!")
                return
                
            logger.info("ObservationEngine: Starting recording session...")
            self._is_observing = True
            self.events = []
            self.start_time_epoch = time.time()
            
            # 1. Create a unique folder for this recording session
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session_id = f"session_{timestamp}"
            
            output_dir = config_manager.get("observation.output_dir", "data/observations")
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            self.session_dir = os.path.join(project_root, output_dir, self.session_id)
            os.makedirs(self.session_dir, exist_ok=True)
            
            logger.info(f"ObservationEngine: Storing session data in: {self.session_dir}")

            # 2. Start the keyboard listener (runs in its own thread)
            self.keyboard_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self.keyboard_listener.start()

            # 3. Start the mouse listener (runs in its own thread)
            self.mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click,
                on_scroll=self._on_mouse_scroll
            )
            self.mouse_listener.start()

            # 4. Start the screenshot capture loop (runs in its own thread)
            self.screenshot_thread = threading.Thread(target=self._screenshot_loop, daemon=True)
            self.screenshot_thread.start()

            # 5. Broadcast to the rest of the application that observation has started
            event_bus.publish("OBSERVATION_STARTED", {"session_id": self.session_id, "session_dir": self.session_dir})

    def stop_observation(self):
        """Stops the recording listeners and saves all data to disk."""
        with self._lock:
            if not self._is_observing:
                logger.warning("ObservationEngine: No active recording to stop!")
                return
                
            logger.info("ObservationEngine: Stopping recording session...")
            self._is_observing = False

            # Stop the pynput listeners
            if self.keyboard_listener:
                self.keyboard_listener.stop()
                self.keyboard_listener = None
                
            if self.mouse_listener:
                self.mouse_listener.stop()
                self.mouse_listener = None
            
            # Wait for screenshot thread to finish if running
            if self.screenshot_thread:
                self.screenshot_thread.join(timeout=2.0)
                self.screenshot_thread = None

            # Save the list of events to JSON
            self._save_session_data()

            # Broadcast that the session has stopped and is saved
            event_bus.publish("OBSERVATION_STOPPED", {"session_id": self.session_id, "session_dir": self.session_dir})
            
            # Reset session info
            self.session_id = None
            self.session_dir = None

    def is_observing(self) -> bool:
        """Returns True if the engine is currently recording."""
        return self._is_observing

    def _record_event(self, event_dict):
        """Helper to append an event with thread-safety."""
        with self._lock:
            self.events.append(event_dict)

    def _get_elapsed_time(self) -> float:
        """Gets time in seconds since recording started."""
        return round(time.time() - self.start_time_epoch, 3)

    def _get_relative_coords(self, x, y):
        """Calculates coordinates relative to the top-left of the active window."""
        try:
            import pygetwindow as gw
            win = gw.getActiveWindow()
            if win is not None:
                return x - win.left, y - win.top
        except Exception:
            pass
        return x, y

    # --- Listener Callback Functions ---

    def _on_key_press(self, key):
        if not self._is_observing:
            return
        try:
            if hasattr(key, 'char') and key.char is not None:
                ord_val = ord(key.char)
                # Convert ASCII control codes (1-26) back to matching alphabetical chars (a-z)
                if 1 <= ord_val <= 26:
                    key_str = chr(ord_val + 96)
                else:
                    key_str = key.char
            else:
                key_str = key.name
        except Exception:
            try:
                key_str = str(key)
            except Exception:
                key_str = "unknown"
            
        clean_key = key_str.replace("Key.", "")
        
        # Check if it is a modifier key
        if clean_key in ["ctrl", "ctrl_l", "ctrl_r", "shift", "shift_r", "shift_l", "alt", "alt_l", "alt_r", "cmd", "cmd_r"]:
            normalized_mod = "ctrl" if "ctrl" in clean_key else ("shift" if "shift" in clean_key else ("alt" if "alt" in clean_key else "cmd"))
            self.active_modifiers.add(normalized_mod)
            return # Don't log single modifier press to avoid noise
            
        # Check if modifiers are active
        if self.active_modifiers:
            mod_prefix = "+".join(sorted(list(self.active_modifiers)))
            combo_key = f"{mod_prefix}+{clean_key}"
            self._record_event({
                "type": "key_press",
                "timestamp": self._get_elapsed_time(),
                "active_window": get_active_window_title(),
                "key": combo_key
            })
        else:
            self._record_event({
                "type": "key_press",
                "timestamp": self._get_elapsed_time(),
                "active_window": get_active_window_title(),
                "key": clean_key
            })

    def _on_key_release(self, key):
        if not self._is_observing:
            return
        try:
            key_str = key.char if hasattr(key, 'char') and key.char is not None else key.name
        except AttributeError:
            key_str = str(key)
            
        clean_key = key_str.replace("Key.", "")
        normalized_mod = "ctrl" if "ctrl" in clean_key else ("shift" if "shift" in clean_key else ("alt" if "alt" in clean_key else "cmd"))
        
        if normalized_mod in self.active_modifiers:
            self.active_modifiers.discard(normalized_mod)
            return # Don't log modifier releases
            
        self._record_event({
            "type": "key_release",
            "timestamp": self._get_elapsed_time(),
            "active_window": get_active_window_title(),
            "key": clean_key
        })



    def _on_mouse_click(self, x, y, button, pressed):
        if not self._is_observing:
            return
            
        rel_x, rel_y = self._get_relative_coords(x, y)
        
        if pressed:
            self._drag_start = (x, y, rel_x, rel_y)
        else:
            # Check if we have a drag start event
            if self._drag_start is not None:
                start_x, start_y, start_rel_x, start_rel_y = self._drag_start
                self._drag_start = None
                
                # Calculate distance
                import math
                dist = math.sqrt((x - start_x)**2 + (y - start_y)**2)
                
                if dist > 15:
                    # Log as a mouse drag
                    self._record_event({
                        "type": "mouse_drag",
                        "timestamp": self._get_elapsed_time(),
                        "active_window": get_active_window_title(),
                        "start_x": start_x,
                        "start_y": start_y,
                        "start_rel_x": start_rel_x,
                        "start_rel_y": start_rel_y,
                        "end_x": x,
                        "end_y": y,
                        "end_rel_x": rel_x,
                        "end_rel_y": rel_y,
                        "button": button.name
                    })
                    return

            # Grab visual crop centered on click point (40x40 pixel bbox)
            crop_filename = None
            try:
                # Capture screen box using PIL (bounding box: left, top, right, bottom)
                bbox = (max(0, x - 20), max(0, y - 20), x + 20, y + 20)
                crop_img = ImageGrab.grab(bbox=bbox)
                
                timestamp = int(time.time() * 1000)
                crop_filename = f"crop_{timestamp}.png"
                crop_path = os.path.join(self.session_dir, crop_filename)
                crop_img.save(crop_path, format="PNG")
            except Exception as e:
                logger.warning(f"ObservationEngine: Failed to capture visual crop: {e}")
                
            # Log as a standard mouse click
            self._record_event({
                "type": "mouse_click",
                "timestamp": self._get_elapsed_time(),
                "active_window": get_active_window_title(),
                "x": x,
                "y": y,
                "rel_x": rel_x,
                "rel_y": rel_y,
                "button": button.name,
                "pressed": False,
                "crop_file": crop_filename
            })

    def _on_mouse_scroll(self, x, y, dx, dy):
        if not self._is_observing:
            return
        rel_x, rel_y = self._get_relative_coords(x, y)
        self._record_event({
            "type": "mouse_scroll",
            "timestamp": self._get_elapsed_time(),
            "active_window": get_active_window_title(),
            "x": x,
            "y": y,
            "rel_x": rel_x,
            "rel_y": rel_y,
            "dx": dx,
            "dy": dy
        })

    # --- Screen Capture Loop ---

    def _screenshot_loop(self):
        """Periodically grabs screen images in the background."""
        screenshot_count = 0
        interval = config_manager.get("observation.screenshot_interval", 1.0)
        image_format = config_manager.get("observation.screenshot_format", "jpeg")
        quality = config_manager.get("observation.screenshot_quality", 80)
        
        logger.info(f"ObservationEngine: Screenshot thread started. Interval: {interval}s")
        
        while self._is_observing:
            start_time = time.time()
            
            try:
                # Capture screen using Pillow
                screenshot = ImageGrab.grab()
                
                ext = "jpg" if image_format.lower() == "jpeg" else image_format.lower()
                filename = f"screenshot_{screenshot_count:04d}.{ext}"
                filepath = os.path.join(self.session_dir, filename)
                
                # Save screenshot to disk
                if image_format.lower() in ["jpg", "jpeg"]:
                    screenshot.save(filepath, format="JPEG", quality=quality)
                else:
                    screenshot.save(filepath, format="PNG")
                
                # Record the screenshot event
                self._record_event({
                    "type": "screenshot",
                    "timestamp": self._get_elapsed_time(),
                    "active_window": get_active_window_title(),
                    "file_path": filename
                })
                
                screenshot_count += 1
            except Exception as e:
                logger.error(f"ObservationEngine: Failed to capture screen: {e}")
                
            # Perform a responsive sleep (checks if stopped every 0.1 seconds)
            elapsed_work = time.time() - start_time
            sleep_remain = max(0.0, interval - elapsed_work)
            
            steps = int(sleep_remain / 0.1)
            for _ in range(steps):
                if not self._is_observing:
                    break
                time.sleep(0.1)
            else:
                # Remaining fractions of sleep
                time.sleep(sleep_remain % 0.1)

        logger.info("ObservationEngine: Screenshot thread stopped.")

    # --- Storage Function ---

    def _save_session_data(self):
        """Saves all logged actions into events.json."""
        if not self.session_dir:
            return
            
        json_path = os.path.join(self.session_dir, "events.json")
        logger.info(f"ObservationEngine: Saving {len(self.events)} events to {json_path}...")
        
        session_metadata = {
            "session_id": self.session_id,
            "start_time": datetime.fromtimestamp(self.start_time_epoch).isoformat(),
            "total_events": len(self.events),
            "events": self.events
        }
        
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(session_metadata, f, indent=4)
            logger.info("ObservationEngine: Session data saved successfully.")
        except Exception as e:
            logger.error(f"ObservationEngine: Failed to save session events: {e}")
