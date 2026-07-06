from collections import defaultdict
from app.services.logging.logger import logger

class EventBus:
    """
    The EventBus is like the intercom/bell in our kitchen.
    It allows different parts of our app to send and receive messages 
    without having to know about each other's inner workings.
    """
    def __init__(self):
        # A dictionary mapping event names to lists of subscriber callback functions
        self._subscribers = defaultdict(list)

    def subscribe(self, event_type: str, callback):
        """
        Register a function to run whenever a specific event is published.
        Example: event_bus.subscribe("RECORDING_STOPPED", stop_screenshot_loop)
        """
        if callback not in self._subscribers[event_type]:
            self._subscribers[event_type].append(callback)
            logger.debug(f"EventBus: Subscribed callback {callback.__name__} to event '{event_type}'")

    def unsubscribe(self, event_type: str, callback):
        """Unsubscribe a function from a specific event."""
        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
            logger.debug(f"EventBus: Unsubscribed callback {callback.__name__} from event '{event_type}'")

    def publish(self, event_type: str, data=None):
        """
        Announce an event to all subscribers.
        Example: event_bus.publish("RECORDING_STARTED", {"session_id": "123"})
        """
        logger.debug(f"EventBus: Publishing event '{event_type}' with data: {data}")
        subscribers = self._subscribers.get(event_type, [])
        for callback in subscribers:
            try:
                # Call the subscriber's function, passing the event data
                callback(data)
            except Exception as e:
                logger.error(f"EventBus: Error calling subscriber callback for event '{event_type}': {e}")

# Create a singleton instance so everyone publishes/subscribes to the same bus
event_bus = EventBus()
