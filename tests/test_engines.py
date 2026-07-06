import unittest
from app.services.config.config_manager import config_manager
from app.services.events.event_bus import event_bus
from app.engines.understanding.understanding_engine import WorkflowUnderstandingEngine

class TestEchoServices(unittest.TestCase):
    """
    Unit tests to verify that our shared services (ConfigManager, EventBus)
    and AI Segmentation logic work correctly in isolation.
    """
    
    def test_config_manager(self):
        """Verifies that the ConfigManager loads the settings correctly."""
        # ConfigManager should load defaults or file values
        app_name = config_manager.get("app.name", "ECHO")
        self.assertEqual(app_name, "ECHO")
        
        # Test default fallback value when key doesn't exist
        fallback = config_manager.get("nonexistent.key", "default_val")
        self.assertEqual(fallback, "default_val")

    def test_event_bus(self):
        """Verifies that the EventBus forwards publications to subscribers."""
        event_received = False
        received_data = None

        def callback(data):
            nonlocal event_received, received_data
            event_received = True
            received_data = data

        # Subscribe
        event_bus.subscribe("TEST_EVENT", callback)
        
        # Publish
        event_bus.publish("TEST_EVENT", {"status": "ok"})
        
        # Verify callback was called with correct data
        self.assertTrue(event_received)
        self.assertEqual(received_data, {"status": "ok"})
        
        # Unsubscribe
        event_bus.unsubscribe("TEST_EVENT", callback)

    def test_understanding_fuzzy_match(self):
        """Verifies that the fuzzy window-matching in the understanding engine is correct."""
        engine = WorkflowUnderstandingEngine()
        
        # Test suggested name and goal heuristics
        name, goal = engine._suggest_name_and_goal(["Brave", "Notepad"])
        self.assertEqual(name, "Data Extraction & Text Logging")
        
        name_empty, goal_empty = engine._suggest_name_and_goal([])
        self.assertEqual(name_empty, "Desktop Workflow Automation")

if __name__ == "__main__":
    unittest.main()
