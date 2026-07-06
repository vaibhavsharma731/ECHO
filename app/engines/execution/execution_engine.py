import os
import json
import time
import torch
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, KeyCode, Controller as KeyboardController

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
        pass

    def run_workflow(self, session_id: str, safety_engine, explainability_engine) -> bool:
        """
        Loads the trained model weights and executes the recorded sequence.
        """
        logger.info(f"ExecutionEngine: Initializing playback for session: {session_id}")
        
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
        try:
            with open(window_map_path, 'r', encoding='utf-8') as f:
                window_map = json.load(f)
            with open(summary_path, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)
        except Exception as e:
            logger.error(f"ExecutionEngine: Failed to load configuration files: {e}")
            return False

        steps = workflow_data.get("steps", [])
        if not steps:
            logger.error("ExecutionEngine: No steps found in workflow_summary.json. Nothing to run.")
            return False

        # Load PyTorch MLP
        model = WorkflowMLP(input_dim=3, hidden_dim=16, num_classes=4)
        try:
            model.load_state_dict(torch.load(model_path))
            model.eval() # Set model to evaluation mode
        except Exception as e:
            logger.error(f"ExecutionEngine: Failed to load PyTorch model weights: {e}")
            return False

        # 3. Setup controllers
        mouse_ctrl = MouseController()
        keyboard_ctrl = KeyboardController()
        
        # Start safety panic key monitor
        safety_engine.start_safety_monitor()

        logger.info("=========================================")
        logger.info("🤖 AUTONOMOUS AGENT PLAYBACK ACTIVE")
        logger.info("=========================================")
        
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
                    
                    # Reconstruct absolute coordinate based on target window position
                    win_left = win.left if win is not None else 0
                    win_top = win.top if win is not None else 0
                    
                    target_x = win_left + rel_x
                    target_y = win_top + rel_y
                    
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
            target_title_lower = target_title.lower()
            
            # Desktop/Taskbar activation is skipped
            if target_title_lower in ["desktop", "taskbar", "unknown"]:
                return None
                
            def clean_title(t):
                return t.strip("* ").lower()
                
            all_wins = gw.getAllWindows()
            for win in all_wins:
                if win.title:
                    c_title = clean_title(win.title)
                    t_title = clean_title(target_title)
                    if t_title in c_title or c_title in t_title:
                        # Restore if minimized
                        try:
                            if win.isMinimized:
                                win.restore()
                        except Exception:
                            pass
                        # Activate/Focus
                        try:
                            win.activate()
                        except Exception:
                            pass
                        logger.info(f"🤖 Auto-Activated window: '{win.title}'")
                        time.sleep(0.3) # Wait for window focus
                        return win
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
