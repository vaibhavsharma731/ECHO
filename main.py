from app.services.logging.logger import logger
from app.services.config.config_manager import config_manager
from app.controller.orchestrator import Orchestrator
from app.ui.gui_app import EchoGuiApp

def main():
    """
    Main entry point for ECHO.
    Launches the modern CustomTkinter desktop GUI.
    """
    logger.info("========================================")
    logger.info(f"Starting {config_manager.get('app.name')} v{config_manager.get('app.version')}...")
    logger.info("========================================")
    
    # Initialize the Orchestrator (Head Chef)
    orchestrator = Orchestrator()
    
    # Initialize the visual UI window
    app = EchoGuiApp(orchestrator)
    
    # Start the Tkinter main loop (keeps window open)
    app.mainloop()
    
    logger.info("ECHO GUI shut down cleanly.")

if __name__ == "__main__":
    main()
