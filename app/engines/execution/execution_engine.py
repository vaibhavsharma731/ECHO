import os
import json
import time
import torch
import cv2
import numpy as np
from PIL import ImageGrab
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, KeyCode, Controller as KeyboardController

from app.services.config.config_manager import config_manager
from app.services.logging.logger import logger
from app.services.utilities.window_helper import get_active_window_title
from app.models.workflow_model import WorkflowMLP

class ExecutionEngine:
    """
    ExecutionEngine loads a trained PyTorch model and executes 
    the steps autonomously on the user's desktop, using pynput controllers
    and relative coordinates for robustness.
    """
    def __init__(self):
        self.launched_apps = set()

    def run_workflow(self, session_id: str, safety_engine, explainability_engine) -> bool:
        """
        Loads the trained model weights and executes the recorded sequence.
        """
        logger.info(f"ExecutionEngine: Initializing playback for session: {session_id}")
        
        try:
            # 1. Setup paths
            output_dir = config_manager.get("observation.output_dir", "data/observations")
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            
            # Model files path
            model_save_dir = os.path.join(project_root, "data", "trained_models", session_id)
            model_path = os.path.join(model_save_dir, "model.pth")
            window_map_path = os.path.join(model_save_dir, "window_map.json")
            
            # Original steps summary path
            session_dir = os.path.join(project_root, output_dir, session_id)
            summary_path = os.path.join(session_dir, "workflow_summary.json")

            # Check files exist
            if not (os.path.exists(model_path) and os.path.exists(window_map_path) and os.path.exists(summary_path)):
                logger.error("ExecutionEngine: Missing required model or workflow files for playback.")
                return False

            # 2. Load model weights, window map, and steps list
            with open(window_map_path, 'r', encoding='utf-8') as f:
                window_map = json.load(f)
            with open(summary_path, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)

            steps = workflow_data.get("steps", [])
            if not steps:
                logger.error("ExecutionEngine: No steps found in workflow_summary.json. Nothing to run.")
                return False

            # Load PyTorch MLP
            model = WorkflowMLP(input_dim=3, hidden_dim=16, num_classes=4)
            model.load_state_dict(torch.load(model_path))
            model.eval() # Set model to evaluation mode
        except Exception as e:
            logger.error(f"ExecutionEngine: Initialization error: {e}")
            return False

        # 3. Setup controllers
        mouse_ctrl = MouseController()
        keyboard_ctrl = KeyboardController()
        
        # Start safety panic key monitor
        safety_engine.start_safety_monitor()

        logger.info("=========================================")
        logger.info("🤖 AUTONOMOUS AGENT PLAYBACK ACTIVE")
        logger.info("=========================================")
        
        self.launched_apps.clear()
        last_action_id = 0.0
        success = True
        
        try:
            for idx, step in enumerate(steps):
                # A. Check safety halt condition first
                safety_engine.check_safety()
                
                action_desc = step.get("action", "")
                timestamp = step.get("timestamp", 0.0)
                target_win_title = step.get("window", "Desktop")
                
                # Skip taskbar/desktop clicks only if we successfully launch/focus the target app
                if ("taskbar" in target_win_title.lower() or "desktop" in target_win_title.lower() or "unknown" in target_win_title.lower()) and "Click" in action_desc:
                    next_real_win = None
                    for future_step in steps[idx+1:]:
                        f_win = future_step.get("window", "")
                        if f_win and not any(sys_name in f_win.lower() for sys_name in ["taskbar", "desktop", "unknown"]):
                            next_real_win = f_win
                            break
                    if next_real_win:
                        logger.info(f"🤖 Attempting to launch target app directly: '{next_real_win}'...")
                        win = self._activate_window(next_real_win)
                        if win is not None:
                            logger.info("🤖 App focused successfully. Bypassing taskbar click.")
                            last_action_id = 0.0
                            time.sleep(0.3)
                            continue
                        else:
                            logger.warning("🤖 Auto-launch failed. Falling back to recorded Taskbar/Desktop click coordinates...")
                
                # B. Query desktop state (Perception)
                current_window = get_active_window_title()
                
                # Map current window to ID using fuzzy match
                window_id = self._find_window_id(current_window, window_map)
                
                # C. Neural Network Inference
                # Input Vector: [Window ID, Elapsed Time, Previous Action ID]
                feature_vector = [window_id, timestamp, last_action_id]
                inputs = torch.tensor(feature_vector, dtype=torch.float32)
                
                with torch.no_grad():
                    logits = model(inputs)
                    predicted_class = int(torch.argmax(logits).item())
                
                # D. Print AI explanation to the user
                explainability_engine.explain_action(logits, predicted_class, step)

                # E. Action Execution
                if "Click" in action_desc:
                    # Activate window first to bring it to front
                    win = self._activate_window(target_win_title)
                    
                    # Read relative coordinate settings
                    rel_x = step.get("rel_x", 0)
                    rel_y = step.get("rel_y", 0)
                    
                    # Reconstruct default absolute coordinate based on target window position
                    win_left = win.left if win is not None else 0
                    win_top = win.top if win is not None else 0
                    target_x = win_left + rel_x
                    target_y = win_top + rel_y
                    
                    # Visual template matching (Version 2)
                    crop_file = step.get("crop_file")
                    if crop_file:
                        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                        crop_path = os.path.join(project_root, "data", "trained_models", session_id, crop_file)
                        if os.path.exists(crop_path):
                            try:
                                template = cv2.imread(crop_path, cv2.IMREAD_GRAYSCALE)
                                if template is not None:
                                    # Capture live screen
                                    screen = ImageGrab.grab()
                                    screen_np = np.array(screen)
                                    screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_RGB2GRAY)
                                    
                                    # Perform OpenCV matching
                                    res = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
                                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                                    
                                    if max_val >= 0.8:
                                        h, w = template.shape
                                        target_x = max_loc[0] + w // 2
                                        target_y = max_loc[1] + h // 2
                                        logger.info(f"🤖 Vision Engine: Visual match successful! Score: {max_val:.2f} at ({target_x}, {target_y})")
                                    else:
                                        logger.warning(f"🤖 Vision Engine: Low match confidence ({max_val:.2f} < 0.80). Falling back to relative coordinate.")
                            except Exception as e:
                                logger.warning(f"🤖 Vision Engine error: {e}. Falling back to relative coordinate.")
                    
                    is_double = "Double" in action_desc or step.get("double_click", False)
                    button = Button.right if "RIGHT" in action_desc else Button.left
                    
                    if is_double:
                        logger.info(f"🤖 Executing: Double Click relative ({rel_x}, {rel_y}) -> absolute ({target_x}, {target_y})")
                        mouse_ctrl.position = (target_x, target_y)
                        time.sleep(0.2)
                        # Manual double click sequence with time buffer is highly robust on Windows
                        mouse_ctrl.press(button)
                        mouse_ctrl.release(button)
                        time.sleep(0.05)
                        mouse_ctrl.press(button)
                        mouse_ctrl.release(button)
                    else:
                        logger.info(f"🤖 Executing: 1x Click relative ({rel_x}, {rel_y}) -> absolute ({target_x}, {target_y})")
                        mouse_ctrl.position = (target_x, target_y)
                        time.sleep(0.2)
                        mouse_ctrl.click(button, 1)
                        
                    last_action_id = 0.0
                    
                elif "Drag" in action_desc:
                    win = self._activate_window(target_win_title)
                    
                    start_rel_x = step.get("start_rel_x", 0)
                    start_rel_y = step.get("start_rel_y", 0)
                    end_rel_x = step.get("end_rel_x", 0)
                    end_rel_y = step.get("end_rel_y", 0)
                    
                    win_left = win.left if win is not None else 0
                    win_top = win.top if win is not None else 0
                    
                    start_x = win_left + start_rel_x
                    start_y = win_top + start_rel_y
                    end_x = win_left + end_rel_x
                    end_y = win_top + end_rel_y
                    
                    logger.info(f"🤖 Executing Drag: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
                    
                    # Move to start, click hold, slide to end, and release
                    mouse_ctrl.position = (start_x, start_y)
                    time.sleep(0.2)
                    mouse_ctrl.press(Button.left)
                    time.sleep(0.2)
                    mouse_ctrl.position = (end_x, end_y)
                    time.sleep(0.2)
                    mouse_ctrl.release(Button.left)
                    
                    last_action_id = 0.0
                    
                elif "Hotkey" in action_desc:
                    self._activate_window(target_win_title)
                    hotkey = step.get("hotkey", "")
                    logger.info(f"🤖 Executing Hotkey: {hotkey}")
                    
                    parts = hotkey.split("+")
                    modifiers = parts[:-1]
                    main_key = parts[-1]
                    
                    mod_map = {
                        "ctrl": Key.ctrl,
                        "shift": Key.shift,
                        "alt": Key.alt,
                        "cmd": Key.cmd
                    }
                    
                    # Press all modifiers
                    for mod in modifiers:
                        if mod in mod_map:
                            keyboard_ctrl.press(mod_map[mod])
                            
                    # Tap the main key using KeyCode wrapper for character inputs
                    if len(main_key) == 1:
                        char_code = KeyCode.from_char(main_key.lower())
                        keyboard_ctrl.press(char_code)
                        keyboard_ctrl.release(char_code)
                    else:
                        if hasattr(Key, main_key):
                            keyboard_ctrl.press(getattr(Key, main_key))
                            keyboard_ctrl.release(getattr(Key, main_key))
                            
                    # Release all modifiers in reverse
                    for mod in reversed(modifiers):
                        if mod in mod_map:
                            keyboard_ctrl.release(mod_map[mod])
                            
                    last_action_id = 1.0
                    
                elif "Type" in action_desc:
                    # Activate window first to make sure typing reaches correct app focus
                    self._activate_window(target_win_title)
                    
                    # Parse text from action string: "Type 'text'"
                    text = action_desc.replace("Type '", "")[:-1]
                    logger.info(f"🤖 Executing: Type string: '{text}'")
                    keyboard_ctrl.type(text)
                    
                    last_action_id = 1.0
                    
                elif "Press" in action_desc:
                    # Activate window first
                    self._activate_window(target_win_title)
                    
                    # Special keys (e.g. "Press BACKSPACE" -> "backspace")
                    key_name = action_desc.replace("Press ", "").lower()
                    logger.info(f"🤖 Executing: Key press: {key_name}")
                    
                    if hasattr(Key, key_name):
                        keyboard_ctrl.press(getattr(Key, key_name))
                        keyboard_ctrl.release(getattr(Key, key_name))
                    elif len(key_name) == 1:
                        # Character key fallback
                        char_code = KeyCode.from_char(key_name)
                        keyboard_ctrl.press(char_code)
                        keyboard_ctrl.release(char_code)
                    else:
                        logger.warning(f"🤖 Unknown special key: {key_name}")
                        
                    last_action_id = 1.0
                    
                elif "Scroll" in action_desc:
                    self._activate_window(target_win_title)
                    direction = "down" if "down" in action_desc else "up"
                    dy = -2 if direction == "down" else 2
                    logger.info(f"🤖 Executing: Scroll {direction}")
                    mouse_ctrl.scroll(0, dy)
                    
                    last_action_id = 2.0
                    
                elif "Screen" in action_desc:
                    # Screenshots are just recorded checkpoints, we don't replay them
                    logger.info("🤖 Executing: Verify screen state checkpoint (No action required)")
                    last_action_id = 3.0
                    
                # Custom step delay for snappy, responsive playback feel
                if "Screen" in action_desc:
                    time.sleep(0.1) # Instant skip for screenshot checkpoints
                else:
                    time.sleep(0.8) # Quick 0.8s pause for physical coordinates/focus rendering

        except KeyboardInterrupt:
            logger.critical("ExecutionEngine: Playback aborted by safety panic stop!")
            success = False
        except Exception as e:
            logger.error(f"ExecutionEngine: Playback error: {e}")
            success = False
        finally:
            # Stop the safety keyboard monitor
            safety_engine.stop_safety_monitor()

        logger.info("=========================================")
        logger.info("🤖 PLAYBACK SYSTEM INACTIVE")
        logger.info("=========================================")
        return success

    def _activate_window(self, target_title: str):
        """Finds the window matching target_title, activates it, and brings it to front."""
        try:
            import pygetwindow as gw
            import subprocess
            import webbrowser
            target_title_lower = target_title.lower()
            
            # Desktop/Taskbar activation is skipped
            if target_title_lower in ["desktop", "taskbar", "unknown"]:
                return None
                
            def clean_title(t):
                return t.strip("* ").lower()
                
            def find_window():
                all_wins = gw.getAllWindows()
                for win in all_wins:
                    if win.title:
                        c_title = clean_title(win.title)
                        t_title = clean_title(target_title)
                        if t_title in c_title or c_title in t_title:
                            try:
                                if win.isMinimized:
                                    win.restore()
                            except Exception:
                                pass
                            try:
                                win.activate()
                            except Exception:
                                pass
                            logger.info(f"🤖 Auto-Activated window: '{win.title}'")
                            time.sleep(0.3)
                            return win
                return None

            # Try to activate if already open
            win = find_window()
            if win is not None:
                return win

            # If not open, check if we have already spawned this app signature in this session
            # to prevent multiple duplicate swarms of windows
            app_sig = None
            if "notepad" in target_title_lower:
                app_sig = "notepad"
            elif "explorer" in target_title_lower or "folder" in target_title_lower:
                app_sig = "explorer"
            elif "edge" in target_title_lower or "chrome" in target_title_lower or "brave" in target_title_lower or "browser" in target_title_lower:
                app_sig = "browser"

            if app_sig and app_sig not in self.launched_apps:
                logger.info(f"🤖 Target window '{target_title}' not open. Spawning {app_sig} (Safe Auto-Launch)...")
                self.launched_apps.add(app_sig)
                
                if app_sig == "notepad":
                    subprocess.Popen(["notepad.exe"])
                elif app_sig == "explorer":
                    subprocess.Popen(["explorer.exe"])
                elif app_sig == "browser":
                    # Look up Brave or Chrome locally, else fallback to default browser
                    launched_spec = False
                    brave_paths = [
                        os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                        os.path.expandvars(r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                        os.path.expandvars(r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                    ]
                    for path in brave_paths:
                        if os.path.exists(path):
                            subprocess.Popen([path])
                            launched_spec = True
                            break
                    if not launched_spec:
                        webbrowser.open("https://www.google.com")

                # Poll for the window to load (max 3.0s)
                for _ in range(30):
                    time.sleep(0.1)
                    win = find_window()
                    if win is not None:
                        return win
            else:
                if app_sig:
                    logger.warning(f"🤖 Target window '{target_title}' not open, but {app_sig} was already spawned. Skipping duplicate launch.")

        except Exception as e:
            logger.warning(f"ExecutionEngine: Failed to activate window '{target_title}': {e}")
        return None

    def _find_window_id(self, title: str, window_map: dict) -> float:
        """Fuzzy match window title against the window mapping keys."""
        if title in window_map:
            return float(window_map[title])
            
        title_lower = title.lower()
        for ref_title, idx in window_map.items():
            ref_lower = ref_title.lower()
            if ref_lower in title_lower or title_lower in ref_lower:
                return float(idx)
                
        # If no match found, return a default out-of-bounds float
        return -1.0
