import os
import json
import shutil
import threading
import time
import customtkinter as ctk

from app.controller.orchestrator import Orchestrator
from app.services.events.event_bus import event_bus
from app.services.logging.logger import logger

class EchoGuiApp(ctk.CTk):
    """
    EchoGuiApp is the visual dashboard (the waiter interface) of ECHO.
    It provides controls to observe, train, save, load, and execute tasks.
    """
    def __init__(self, orchestrator: Orchestrator):
        super().__init__()
        self.orchestrator = orchestrator
        self.session_id = None
        
        # Setup workspace paths
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.library_dir = os.path.join(self.project_root, "data", "task_library")
        os.makedirs(self.library_dir, exist_ok=True)
        
        # 1. Page Configuration (Sleek Dark Mode)
        self.title("ECHO - AI Desktop Apprentice")
        self.geometry("720x600")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        # Grid layout config
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # 2. Top Header Title (Row 0)
        self.title_label = ctk.CTkLabel(
            self, 
            text="ECHO: Human Observation Agent", 
            font=ctk.CTkFont(family="Arial", size=24, weight="bold"),
            text_color="#1F6AA5"
        )
        self.title_label.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="ew")

        # 3. Task Library Loader Panel (Row 1)
        self.library_frame = ctk.CTkFrame(self)
        self.library_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        self.library_frame.grid_columnconfigure(1, weight=1)
        
        self.lbl_lib = ctk.CTkLabel(
            self.library_frame, 
            text="📁 Task Library:", 
            font=ctk.CTkFont(family="Arial", size=13, weight="bold")
        )
        self.lbl_lib.grid(row=0, column=0, padx=(15, 5), pady=10, sticky="w")
        
        self.task_menu = ctk.CTkOptionMenu(
            self.library_frame,
            command=self._on_task_selected,
            values=["No saved tasks"]
        )
        self.task_menu.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        
        self.btn_refresh_lib = ctk.CTkButton(
            self.library_frame,
            text="🔄 Refresh",
            width=80,
            command=self._populate_saved_tasks
        )
        self.btn_refresh_lib.grid(row=0, column=2, padx=(5, 15), pady=10, sticky="e")

        # 4. Status Display Panel (Row 2)
        self.status_frame = ctk.CTkFrame(self)
        self.status_frame.grid(row=2, column=0, padx=20, pady=5, sticky="ew")
        self.status_frame.grid_columnconfigure(0, weight=1)
        
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Status: Idle (Ready to Record)",
            font=ctk.CTkFont(family="Arial", size=14, weight="bold"),
            text_color="#A9A9A9"
        )
        self.status_label.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        # 5. Main Logs & Action Step Textbox (Row 3)
        self.log_box = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.grid(row=3, column=0, padx=20, pady=5, sticky="nsew")
        self.log_box.insert("0.0", "Welcome to ECHO AI Desktop Apprentice CLI & GUI.\n\n"
                                   "Instructions:\n"
                                   "1. Click 'Start Observing' to demonstrate a task.\n"
                                   "2. Perform clicks/typing on your PC, then return and click 'Stop'.\n"
                                   "3. Click 'Teach Assistant' to train the PyTorch model.\n"
                                   "4. Click 'Perform Task' to run the automation.\n\n"
                                   "Press 'ESC' at any time during execution to abort playback.\n"
                                   "---------------------------------------------------\n")

        # 6. Save Current Task Panel (Row 4)
        self.save_frame = ctk.CTkFrame(self)
        self.save_frame.grid(row=4, column=0, padx=20, pady=5, sticky="ew")
        self.save_frame.grid_columnconfigure(1, weight=1)
        
        self.lbl_save_name = ctk.CTkLabel(
            self.save_frame,
            text="💾 Save Trained Task As:",
            font=ctk.CTkFont(family="Arial", size=13, weight="bold")
        )
        self.lbl_save_name.grid(row=0, column=0, padx=(15, 5), pady=10, sticky="w")
        
        self.entry_task_name = ctk.CTkEntry(
            self.save_frame,
            placeholder_text="Enter task name (e.g. Google_Search)"
        )
        self.entry_task_name.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        
        self.btn_save_task = ctk.CTkButton(
            self.save_frame,
            text="Save to Library",
            width=120,
            command=self._save_task_action,
            fg_color="#1F6AA5",
            hover_color="#144870"
        )
        self.btn_save_task.grid(row=0, column=2, padx=(5, 15), pady=10, sticky="e")

        # 7. Bottom Buttons Panel (Row 5)
        self.buttons_frame = ctk.CTkFrame(self)
        self.buttons_frame.grid(row=5, column=0, padx=20, pady=(5, 15), sticky="ew")
        self.buttons_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # BUTTON A: Observe Me
        self.btn_observe = ctk.CTkButton(
            self.buttons_frame,
            text="Start Observing",
            command=self._start_observe_action,
            fg_color="#2E7D32",
            hover_color="#1B5E20"
        )
        self.btn_observe.grid(row=0, column=0, padx=10, pady=12)

        # BUTTON B: Stop Observing
        self.btn_stop = ctk.CTkButton(
            self.buttons_frame,
            text="Stop & Analyze",
            command=self._stop_observe_action,
            fg_color="#C62828",
            hover_color="#B71C1C",
            state="disabled"
        )
        self.btn_stop.grid(row=0, column=1, padx=10, pady=12)

        # BUTTON C: Teach Assistant
        self.btn_teach = ctk.CTkButton(
            self.buttons_frame,
            text="Teach Assistant",
            command=self._teach_action,
            fg_color="#1565C0",
            hover_color="#0D47A1",
            state="disabled"
        )
        self.btn_teach.grid(row=0, column=2, padx=10, pady=12)

        # BUTTON D: Perform Task
        self.btn_play = ctk.CTkButton(
            self.buttons_frame,
            text="Perform Task",
            command=self._play_action,
            fg_color="#E65100",
            hover_color="#E65100",
            state="disabled"
        )
        self.btn_play.grid(row=0, column=3, padx=10, pady=12)

        # Load saved tasks list at start
        self._populate_saved_tasks()

        # Subscribe to event bus
        self._register_event_listeners()

    def _register_event_listeners(self):
        event_bus.subscribe("OBSERVATION_STARTED", self._on_observe_started)
        event_bus.subscribe("OBSERVATION_STOPPED", self._on_observe_stopped)
        event_bus.subscribe("WORKFLOW_UNDERSTOOD", self._on_workflow_understood)

    def _populate_saved_tasks(self):
        """Finds all subfolders inside data/task_library and fills the dropdown menu."""
        try:
            if not os.path.exists(self.library_dir):
                os.makedirs(self.library_dir, exist_ok=True)
                
            tasks = [f for f in os.listdir(self.library_dir) if os.path.isdir(os.path.join(self.library_dir, f))]
            
            if not tasks:
                self.task_menu.configure(values=["No saved tasks"])
                self.task_menu.set("No saved tasks")
            else:
                values = ["Select Task..."] + sorted(tasks)
                self.task_menu.configure(values=values)
                self.task_menu.set("Select Task...")
        except Exception as e:
            logger.error(f"EchoGuiApp: Failed to populate saved tasks list: {e}")

    def _on_task_selected(self, selected_task: str):
        """Loads and prepares files of a saved library task for immediate playback."""
        if selected_task in ["Select Task...", "No saved tasks"]:
            return
            
        task_dir = os.path.join(self.library_dir, selected_task)
        summary_path = os.path.join(task_dir, "workflow_summary.json")
        model_path = os.path.join(task_dir, "model.pth")
        win_map_path = os.path.join(task_dir, "window_map.json")

        if not (os.path.exists(summary_path) and os.path.exists(model_path)):
            self.log_box.insert("insert", f"\n>>> ERROR: Task '{selected_task}' is missing model or summary files!\n")
            return
            
        # Re-register this task under active trained_models & observations directory
        # so ExecutionEngine can read the session data transparently
        trained_dir = os.path.join(self.project_root, "data", "trained_models", selected_task)
        obs_dir = os.path.join(self.project_root, "data", "observations", selected_task)
        
        os.makedirs(trained_dir, exist_ok=True)
        os.makedirs(obs_dir, exist_ok=True)
        
        try:
            shutil.copy2(model_path, os.path.join(trained_dir, "model.pth"))
            if os.path.exists(win_map_path):
                shutil.copy2(win_map_path, os.path.join(trained_dir, "window_map.json"))
            shutil.copy2(summary_path, os.path.join(obs_dir, "workflow_summary.json"))
            
            # Set active session_id to load task
            self.session_id = selected_task
            
            # Load step sequence details
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary = json.load(f)
                
            self._on_workflow_understood(summary)
            self.log_box.insert("1.0", f">>> Loaded Task '{selected_task}' from Library! Ready to run.\n\n")
            self.btn_play.configure(state="normal")
            self.status_label.configure(text=f"Status: Loaded Task '{selected_task}'")
        except Exception as e:
            self.log_box.insert("insert", f"\n>>> Failed to copy task files to active runtime: {e}\n")

    def _save_task_action(self):
        """Saves current trained model files to the task library folder."""
        task_name = self.entry_task_name.get().strip()
        if not task_name:
            self.log_box.insert("insert", "\n>>> WARNING: Please type a name in the text field to save the task!\n")
            return
            
        if not self.session_id:
            self.log_box.insert("insert", "\n>>> WARNING: No active trained task session available to save!\n")
            return
            
        # Clean task name for filesystems
        clean_name = "".join(c for c in task_name if c.isalnum() or c in [' ', '_', '-']).strip().replace(' ', '_')
        
        target_dir = os.path.join(self.library_dir, clean_name)
        os.makedirs(target_dir, exist_ok=True)
        
        trained_dir = os.path.join(self.project_root, "data", "trained_models", self.session_id)
        model_path = os.path.join(trained_dir, "model.pth")
        win_map_path = os.path.join(trained_dir, "window_map.json")
        
        obs_dir = os.path.join(self.project_root, "data", "observations", self.session_id)
        summary_path = os.path.join(obs_dir, "workflow_summary.json")
        
        try:
            if not os.path.exists(model_path) or not os.path.exists(summary_path):
                self.log_box.insert("insert", "\n>>> ERROR: Current active task has not been trained yet. Click 'Teach Assistant' first!\n")
                return
                
            # Copy files
            shutil.copy2(model_path, os.path.join(target_dir, "model.pth"))
            if os.path.exists(win_map_path):
                shutil.copy2(win_map_path, os.path.join(target_dir, "window_map.json"))
            shutil.copy2(summary_path, os.path.join(target_dir, "workflow_summary.json"))
            
            self.log_box.insert("insert", f"\n>>> SUCCESS: Task saved inside Library as '{clean_name}'!\n")
            self.entry_task_name.delete(0, "end")
            
            # Refresh list
            self._populate_saved_tasks()
        except Exception as e:
            self.log_box.insert("insert", f"\n>>> Error saving task to Library: {e}\n")

    # --- Button Callbacks ---

    def _start_observe_action(self):
        """Starts observation recording."""
        self.btn_observe.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_teach.configure(state="disabled")
        self.btn_play.configure(state="disabled")
        
        self.log_box.delete("1.0", "end")
        self.log_box.insert("insert", ">>> Starting recording listeners... Get ready to demonstrate!\n")
        
        # Run start in Orchestrator
        self.orchestrator.start_recording()

    def _stop_observe_action(self):
        """Stops observation recording."""
        self.btn_stop.configure(state="disabled")
        self.session_id = self.orchestrator.observation_engine.session_id
        
        self.log_box.insert("insert", ">>> Stopping recording and writing events list...\n")
        
        # Run stop in Orchestrator
        self.orchestrator.stop_recording()

    def _teach_action(self):
        """Launches PyTorch training in a background thread to prevent UI freezing."""
        self.btn_teach.configure(state="disabled")
        self.status_label.configure(text="Status: Training PyTorch Brain...")
        self.log_box.insert("insert", "\n>>> Initiating model training in background thread...\n")

        def train_thread():
            # Run the training
            success = self.orchestrator.teach_workflow(self.session_id)
            if success:
                # Use after() to safely update GUI elements from a background thread
                self.after(0, lambda: self.status_label.configure(text="Status: Training Successful! Model Ready."))
                self.after(0, lambda: self.btn_play.configure(state="normal"))
                self.after(0, lambda: self.log_box.insert("insert", ">>> SUCCESS: Neural network trained. Saved 'model.pth'.\n"))
            else:
                self.after(0, lambda: self.status_label.configure(text="Status: Training Failed! Check logs."))
                self.after(0, lambda: self.btn_teach.configure(state="normal"))

        threading.Thread(target=train_thread, daemon=True).start()

    def _play_action(self):
        """Launches playback automation in a background thread."""
        self.btn_play.configure(state="disabled")
        self.status_label.configure(text="Status: Replaying Task Autonomously...")
        self.log_box.insert("insert", "\n>>> Starting autonomous playback. Hands off keyboard/mouse!\n")
        self.log_box.insert("insert", ">>> Press 'ESC' key to force stop.\n\n")

        def play_thread():
            success = self.orchestrator.execute_workflow(self.session_id)
            if success:
                self.after(0, lambda: self.status_label.configure(text="Status: Task Completed!"))
            else:
                self.after(0, lambda: self.status_label.configure(text="Status: Playback Aborted!"))
            self.after(0, lambda: self.btn_play.configure(state="normal"))

        threading.Thread(target=play_thread, daemon=True).start()

    # --- Event Bus Handlers (UI updates) ---

    def _on_observe_started(self, data):
        self.status_label.configure(text="Status: OBSERVING DESKTOP ACTIONS...")
        self.log_box.insert("insert", f"Session Started: {data.get('session_id')}\n")
        self.log_box.insert("insert", "OBSERVATION ACTIVE! Perform your clicks and keystrokes now...\n")

    def _on_observe_stopped(self, data):
        self.status_label.configure(text="Status: Observation stopped. Analyzing...")
        self.log_box.insert("insert", "Observation Stopped. Segmenting raw events...\n")

    def _on_workflow_understood(self, summary):
        """Updates the log box text with the clean segmented steps."""
        self.status_label.configure(text="Status: Workflow Analysis Ready.")
        self.btn_observe.configure(state="normal")
        self.btn_teach.configure(state="normal")
        
        self.log_box.insert("insert", "\n========================================\n")
        self.log_box.insert("insert", "       📋 AI WORKFLOW STEPS LIST        \n")
        self.log_box.insert("insert", "========================================\n")
        self.log_box.insert("insert", f"Workflow Name: {summary.get('workflow_name')}\n")
        self.log_box.insert("insert", f"Apps Used:     {', '.join(summary.get('apps_used', []))}\n")
        self.log_box.insert("insert", f"Duration:      {summary.get('total_duration_sec', 0.0)} seconds\n")
        self.log_box.insert("insert", "----------------------------------------\n")
        
        steps = summary.get("steps", [])
        if not steps:
            self.log_box.insert("insert", "  (No semantic steps detected)\n")
        else:
            for idx, step in enumerate(steps, 1):
                action = step.get("action")
                window = step.get("window", "Desktop")
                short_win = (window[:25] + '...') if len(window) > 28 else window
                self.log_box.insert("insert", f"  {idx:02d}. {action:<30} (in '{short_win}')\n")
                
        self.log_box.insert("insert", "========================================\n")
        self.log_box.see("end")
