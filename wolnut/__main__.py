import argparse
import sys
import logging
from wolnut.config import load_config
from wolnut.monitors import WolNutMonitor

def main():
    parser = argparse.ArgumentParser(description="WolNut: UPS-triggered Wake-on-LAN client utility.")
    parser.add_argument(
        "--config", 
        default="/config/config.yaml", 
        help="Path to the application configuration file"
    )
    args = parser.parse_args()

    # Setup application logs
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger("wolnut")

    try:
        logger.info(f"Loading configuration from: {args.config}")
        config = load_config(args.config)
        
        monitor = WolNutMonitor(config)
        monitor.start(interval_sec=10)
        
    except Exception as e:
        logger.critical(f"Application failed to initialize: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
