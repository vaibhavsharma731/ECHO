import torch
from app.services.logging.logger import logger

class ExplainabilityEngine:
    """
    ExplainabilityEngine translates the raw numbers in the AI's brain
    into friendly explanations so you know exactly why it is doing what it is doing.
    """
    def __init__(self):
        self.action_names = {
            0: "Click mouse button",
            1: "Type keyboard keys",
            2: "Scroll page",
            3: "Finish task"
        }

    def explain_action(self, logits: torch.Tensor, predicted_class: int, step_details: dict):
        """
        Takes the raw logits from the neural network and prints a friendly explanation.
        """
        # Softmax turns raw network output scores into percentage probabilities
        probabilities = torch.softmax(logits, dim=0)
        confidence = float(probabilities[predicted_class]) * 100
        
        action_name = self.action_names.get(predicted_class, "Unknown")
        target_win = step_details.get("window", "Desktop")
        action_desc = step_details.get("action", "No details")
        
        logger.info(f"💡 [AI EXPLANATION]:")
        logger.info(f"   * I decided to:    {action_name.upper()}")
        logger.info(f"   * Details:         {action_desc}")
        logger.info(f"   * Focused Window:  {target_win}")
        logger.info(f"   * My Confidence:   {confidence:.1f}%")
        logger.info(f"   * Why:             Current active window maps to this task sequence.")
        logger.info("")
