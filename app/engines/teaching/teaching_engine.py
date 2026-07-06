import os
import json
import torch
import torch.nn as nn
import torch.optim as optim

from app.services.config.config_manager import config_manager
from app.services.logging.logger import logger
from app.models.workflow_model import WorkflowMLP

class TeachingEngine:
    """
    TeachingEngine takes observed user events, extracts numeric features,
    and trains our WorkflowMLP neural network (Behavioral Cloning).
    It saves the trained model weights so they can be loaded for execution.
    """
    def __init__(self):
        pass

    def train_workflow(self, session_id: str) -> bool:
        """
        Trains a model based on the recorded session events.
        """
        logger.info(f"TeachingEngine: Preparing training dataset for session: {session_id}")
        
        # 1. Paths setup
        output_dir = config_manager.get("observation.output_dir", "data/observations")
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        session_dir = os.path.join(project_root, output_dir, session_id)
        events_json_path = os.path.join(session_dir, "events.json")

        if not os.path.exists(events_json_path):
            logger.error(f"TeachingEngine: Cannot train. events.json not found at {events_json_path}")
            return False

        # 2. Read events data
        try:
            with open(events_json_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
        except Exception as e:
            logger.error(f"TeachingEngine: Failed to read events: {e}")
            return False

        events = session_data.get("events", [])
        if not events:
            logger.error("TeachingEngine: No events found. Cannot train model on empty session.")
            return False

        # 3. Feature Engineering & Target Mapping
        # We need to map active window titles (strings) to window IDs (numbers)
        window_map = {}
        window_counter = 0
        
        features = []
        targets = []
        
        last_action_id = 0.0 # 0.0 represents no action yet
        
        # Map event types to integer labels:
        # 0: Click, 1: Type, 2: Scroll, 3: Finish
        action_mapping = {
            "mouse_click": 0,
            "key_press": 1,
            "mouse_scroll": 2,
            "screenshot": 3 # We can treat screenshot or end of session as transition
        }

        logger.info("TeachingEngine: Engineering feature vectors...")
        for event in events:
            event_type = event.get("type")
            
            # Skip mouse move events to keep training simple
            if event_type == "mouse_move":
                continue
                
            active_window = event.get("active_window", "Desktop")
            timestamp = event.get("timestamp", 0.0)
            
            # Assign a unique number to this window title if we haven't seen it yet
            if active_window not in window_map:
                window_map[active_window] = window_counter
                window_counter += 1
                
            window_id = float(window_map[active_window])
            
            # Map the current action to a target class
            # If it's a key release, ignore it to prevent double-learning
            if event_type == "key_release":
                continue
                
            action_label = action_mapping.get(event_type, 3)
            
            # Create feature vector: [Window ID, Elapsed Time, Previous Action ID]
            feature_vector = [window_id, timestamp, last_action_id]
            
            features.append(feature_vector)
            targets.append(action_label)
            
            # Update last action ID for next step
            last_action_id = float(action_label)

        # Add a final "Finish" step to teach the model when to stop
        if features:
            final_win_id = features[-1][0]
            final_time = features[-1][1] + 1.0
            features.append([final_win_id, final_time, last_action_id])
            targets.append(3) # Action ID 3 = Finish

        # Convert to PyTorch Tensors
        X = torch.tensor(features, dtype=torch.float32)
        y = torch.tensor(targets, dtype=torch.long)
        
        logger.info(f"TeachingEngine: Created dataset of size: {len(X)} training samples")

        # 4. Neural Network Training Setup
        model = WorkflowMLP(input_dim=3, hidden_dim=16, num_classes=4)
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=0.01)

        # 5. Training Loop
        epochs = 100
        logger.info(f"TeachingEngine: Starting PyTorch training loop for {epochs} epochs...")
        model.train()
        
        for epoch in range(1, epochs + 1):
            optimizer.zero_grad() # Clear gradients from previous step
            
            outputs = model(X) # Forward pass
            loss = criterion(outputs, y) # Compute loss
            
            loss.backward() # Backward pass (compute gradients)
            optimizer.step() # Update weights
            
            if epoch == 1 or epoch % 10 == 0:
                logger.info(f"  Epoch {epoch:03d}/{epochs} - Training Loss: {loss.item():.4f}")

        # 6. Save the trained model and window mapping
        # Create output model directory
        model_save_dir = os.path.join(project_root, "data", "trained_models", session_id)
        os.makedirs(model_save_dir, exist_ok=True)
        
        model_path = os.path.join(model_save_dir, "model.pth")
        window_map_path = os.path.join(model_save_dir, "window_map.json")
        
        try:
            # Save neural network weights
            torch.save(model.state_dict(), model_path)
            # Save the window mapping so Execution Engine can index titles the same way
            with open(window_map_path, 'w', encoding='utf-8') as f:
                json.dump(window_map, f, indent=4)
                
            # Copy all crop_*.png files from session_dir to model_save_dir for visual template matching
            import shutil
            for filename in os.listdir(session_dir):
                if filename.startswith("crop_") and filename.endswith(".png"):
                    shutil.copy2(os.path.join(session_dir, filename), os.path.join(model_save_dir, filename))
                
            logger.info("TeachingEngine: Training completed successfully!")
            logger.info(f"TeachingEngine: Model saved to: {model_path}")
            logger.info(f"TeachingEngine: Window map saved to: {window_map_path}")
            return True
        except Exception as e:
            logger.error(f"TeachingEngine: Failed to save trained model: {e}")
            return False
