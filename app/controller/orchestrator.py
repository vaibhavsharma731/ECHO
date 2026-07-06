from app.services.logging.logger import logger
from app.services.events.event_bus import event_bus
from app.engines.observation.observation_engine import ObservationEngine
from app.engines.understanding.understanding_engine import WorkflowUnderstandingEngine
from app.engines.teaching.teaching_engine import TeachingEngine
from app.engines.execution.execution_engine import ExecutionEngine
from app.engines.safety.safety_engine import SafetyEngine
from app.engines.explainability.explainability_engine import ExplainabilityEngine

class Orchestrator:
    """
    The Orchestrator is the Head Chef. 
    It stands in the center and directs all other engines.
    """
    def __init__(self):
        logger.info("Orchestrator: Initializing engines...")
        self.observation_engine = ObservationEngine()
        self.understanding_engine = WorkflowUnderstandingEngine()
        self.teaching_engine = TeachingEngine()
        self.execution_engine = ExecutionEngine()
        self.safety_engine = SafetyEngine()
        self.explainability_engine = ExplainabilityEngine()
        
        # Subscribe to EventBus announcements
        self._register_event_listeners()

    def _register_event_listeners(self):
        """Subscribe to events we care about."""
        event_bus.subscribe("OBSERVATION_STARTED", self._on_observation_started)
        event_bus.subscribe("OBSERVATION_STOPPED", self._on_observation_stopped)

    def start_recording(self):
        """Instruct the observation engine to start observing."""
        logger.info("Orchestrator: Requesting start of recording...")
        self.observation_engine.start_observation()

    def stop_recording(self):
        """Instruct the observation engine to stop observing."""
        logger.info("Orchestrator: Requesting stop of recording...")
        self.observation_engine.stop_observation()

    def _on_observation_started(self, data):
        logger.info(f"Orchestrator Received Event: Observation Started. Data: {data}")

    def _on_observation_stopped(self, data):
        logger.info(f"Orchestrator Received Event: Observation Stopped. Data: {data}")
        session_id = data.get("session_id")
        if session_id:
            summary = self.understanding_engine.analyze_session(session_id)
            event_bus.publish("WORKFLOW_UNDERSTOOD", summary)
        else:
            logger.error("Orchestrator: No session_id received in stop event!")

    def teach_workflow(self, session_id: str) -> bool:
        """Trains the ML model for the approved session."""
        logger.info(f"Orchestrator: Initiating model training for session: {session_id}")
        success = self.teaching_engine.train_workflow(session_id)
        if success:
            logger.info("Orchestrator: Teaching phase complete.")
        else:
            logger.error("Orchestrator: Teaching phase failed!")
        return success

    def execute_workflow(self, session_id: str) -> bool:
        """Loads and plays back the ML model actions autonomously."""
        logger.info(f"Orchestrator: Initiating model execution for session: {session_id}")
        success = self.execution_engine.run_workflow(session_id, self.safety_engine, self.explainability_engine)
        if success:
            logger.info("Orchestrator: Execution phase complete.")
        else:
            logger.error("Orchestrator: Execution phase aborted or failed!")
        return success
