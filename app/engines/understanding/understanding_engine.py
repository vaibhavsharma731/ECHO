import os
import json
from app.services.config.config_manager import config_manager
from app.services.logging.logger import logger
from app.services.utilities.window_helper import get_active_window_title

class WorkflowUnderstandingEngine:
    """
    WorkflowUnderstandingEngine reads the raw 'events.json' file, 
    compresses hundreds of clicks and keys into a list of readable steps, 
    and generates an AI summary of what the user did.
    """
    def __init__(self):
        pass

    def analyze_session(self, session_id: str) -> dict:
        """
        Reads raw events from session directory and groups them into 
        semantic, high-level steps for the user.
        """
        logger.info(f"WorkflowUnderstandingEngine: Starting analysis for session: {session_id}")
        
        # 1. Get session directory
        output_dir = config_manager.get("observation.output_dir", "data/observations")
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        session_dir = os.path.join(project_root, output_dir, session_id)
        events_json_path = os.path.join(session_dir, "events.json")

        if not os.path.exists(events_json_path):
            logger.error(f"WorkflowUnderstandingEngine: events.json not found at {events_json_path}")
            return {"error": "Session events file not found"}

        # 2. Read raw events
        try:
            with open(events_json_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
        except Exception as e:
            logger.error(f"WorkflowUnderstandingEngine: Failed to read events file: {e}")
            return {"error": str(e)}

        raw_events = session_data.get("events", [])
        
        # 3. Analyze and group events (Segmentation)
        steps = []
        unique_apps = set()
        
        # Temporary state for grouping keyboard typing
        current_typing = []
        typing_window = None
        typing_start_time = None
        
        def commit_typing():
            """Helper function to turn a list of keystrokes into a single text step."""
            nonlocal current_typing, typing_window, typing_start_time
            if not current_typing:
                return
            
            # Combine characters into a single string
            text = "".join(current_typing)
            steps.append({
                "action": f"Type '{text}'",
                "window": typing_window,
                "timestamp": typing_start_time
            })
            # Reset typing state
            current_typing = []
            typing_window = None
            typing_start_time = None

        for event in raw_events:
            event_type = event.get("type")
            active_win = event.get("active_window", "Desktop")
            timestamp = event.get("timestamp", 0.0)
            
            # Keep track of unique applications used
            app_name = active_win.split(" - ")[-1] # Try to get the main application name
            unique_apps.add(app_name)

            # A. Process Key Presses
            if event_type == "key_press":
                key = event.get("key", "")
                
                # If window changed or time gap > 3 seconds, save current typing first
                if typing_window and (typing_window != active_win or (timestamp - typing_start_time > 3.0)):
                    commit_typing()
                
                if not typing_window:
                    typing_window = active_win
                    typing_start_time = timestamp
                
                # Check for combination hotkeys (like ctrl+c or shift+a)
                if "+" in key:
                    commit_typing()
                    steps.append({
                        "action": f"Press Hotkey {key}",
                        "window": active_win,
                        "timestamp": timestamp,
                        "hotkey": key
                    })
                # Simplify standard keys
                elif len(key) == 1:
                    current_typing.append(key)
                elif key == "space":
                    current_typing.append(" ")
                elif key == "backspace":
                    if current_typing:
                        current_typing.pop() # Delete last typed char
                elif key == "enter":
                    commit_typing()
                    steps.append({
                        "action": "Press Enter",
                        "window": active_win,
                        "timestamp": timestamp
                    })
                # Ignore modifier keys (shift, ctrl, alt) on their own
                elif key in ["shift", "ctrl_l", "ctrl_r", "alt_l", "alt_r", "tab"]:
                    pass
                else:
                    # For other keys like esc, delete, arrows
                    commit_typing()
                    steps.append({
                        "action": f"Press {key.upper()}",
                        "window": active_win,
                        "timestamp": timestamp
                    })

            # B. Process Mouse Clicks
            elif event_type == "mouse_click":
                # Process click when it is released/committed (pressed is False)
                if not event.get("pressed", False):
                    commit_typing()
                    button = event.get("button", "left")
                    x = event.get("x", 0)
                    y = event.get("y", 0)
                    rel_x = event.get("rel_x", x)
                    rel_y = event.get("rel_y", y)
                    crop_file = event.get("crop_file", None)
                    
                    is_double_click = False
                    # Check if previous step was also a single click on the same button/window within 0.5s and 10px
                    if steps and "Click" in steps[-1]["action"] and "Double" not in steps[-1]["action"]:
                        last_step = steps[-1]
                        time_diff = timestamp - last_step["timestamp"]
                        dist = ((x - last_step.get("x", 0))**2 + (y - last_step.get("y", 0))**2)**0.5
                        
                        if time_diff < 0.5 and dist < 10 and button.upper() in last_step["action"]:
                            # Upgrade the previous step to a Double Click
                            last_step["action"] = f"Double Click {button.upper()} at relative ({last_step['rel_x']}, {last_step['rel_y']})"
                            last_step["double_click"] = True
                            is_double_click = True
                            
                    if not is_double_click:
                        steps.append({
                            "action": f"Click {button.upper()} at relative ({rel_x}, {rel_y})",
                            "window": active_win,
                            "timestamp": timestamp,
                            "rel_x": rel_x,
                            "rel_y": rel_y,
                            "x": x,
                            "y": y,
                            "double_click": False,
                            "crop_file": crop_file
                        })

            # B2. Process Mouse Drag and Drop
            elif event_type == "mouse_drag":
                commit_typing()
                button = event.get("button", "left")
                start_x = event.get("start_x", 0)
                start_y = event.get("start_y", 0)
                start_rel_x = event.get("start_rel_x", 0)
                start_rel_y = event.get("start_rel_y", 0)
                end_x = event.get("end_x", 0)
                end_y = event.get("end_y", 0)
                end_rel_x = event.get("end_rel_x", 0)
                end_rel_y = event.get("end_rel_y", 0)
                
                steps.append({
                    "action": f"Drag {button.upper()} from ({start_rel_x}, {start_rel_y}) to ({end_rel_x}, {end_rel_y})",
                    "window": active_win,
                    "timestamp": timestamp,
                    "start_rel_x": start_rel_x,
                    "start_rel_y": start_rel_y,
                    "end_rel_x": end_rel_x,
                    "end_rel_y": end_rel_y,
                    "button": button
                })

            # C. Process Mouse Scroll
            elif event_type == "mouse_scroll":
                commit_typing()
                dy = event.get("dy", 0)
                direction = "down" if dy < 0 else "up"
                steps.append({
                    "action": f"Scroll {direction}",
                    "window": active_win,
                    "timestamp": timestamp
                })

            # D. Process Screenshots
            elif event_type == "screenshot":
                # We save screenshots in our steps list so the AI remembers the screen state
                commit_typing()
                steps.append({
                    "action": f"Capture Screen state",
                    "window": active_win,
                    "file_path": event.get("file_path"),
                    "timestamp": timestamp
                })
                
        # Commit any leftover typing
        commit_typing()

        # 4. Generate metadata summaries
        apps_list = list(unique_apps)
        duration = raw_events[-1].get("timestamp", 0.0) if raw_events else 0.0
        
        # Simple rule-based name and goal guesser
        workflow_name, workflow_goal = self._suggest_name_and_goal(apps_list)
        
        # Calculate AI confidence (dummy heuristic for now)
        confidence = 0.95 if steps else 0.50

        summary = {
            "session_id": session_id,
            "workflow_name": workflow_name,
            "goal": workflow_goal,
            "apps_used": apps_list,
            "total_duration_sec": duration,
            "confidence_rating": confidence,
            "steps": steps
        }

        # 5. Save the summary inside the session folder
        summary_path = os.path.join(session_dir, "workflow_summary.json")
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=4)
            logger.info(f"WorkflowUnderstandingEngine: Saved summary to {summary_path}")
        except Exception as e:
            logger.error(f"WorkflowUnderstandingEngine: Failed to write summary JSON: {e}")

        return summary

    def _suggest_name_and_goal(self, apps: list) -> tuple:
        """Helper to guess a friendly name and goal based on apps used."""
        apps_lower = [a.lower() for a in apps]
        
        # Check if Chrome or Brave was used
        browser_used = any("chrome" in a or "brave" in a or "browser" in a for a in apps_lower)
        # Check if Notepad was used
        editor_used = any("notepad" in a or "editor" in a or "text" in a or "code" in a for a in apps_lower)
        
        if browser_used and editor_used:
            return "Data Extraction & Text Logging", "Download information from browser and log it to a text file."
        elif browser_used:
            return "Web Automation Task", "Navigate pages or perform online queries."
        elif editor_used:
            return "Text Document Editing", "Write or modify desktop documents."
        else:
            return "Desktop Workflow Automation", "Automate sequences on desktop application windows."
