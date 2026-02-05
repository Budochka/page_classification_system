"""Main entry point for page classification system."""

import argparse
import logging
import sys
from pathlib import Path

from .config.loader import load_config
from .agent.mcp_agent import MCPAgent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Page Classification System for Exchange Websites"
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config/config.yaml",
        help="Path to config file (YAML or JSON)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    # Resolve paths relative to project root (page_classification_system/)
    project_root = Path(__file__).resolve().parent.parent.parent
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_root / config_path

    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config(config_path)
    # Resolve ruleset and term_dictionaries relative to project root
    if not Path(config.ruleset_path).is_absolute():
        config.ruleset_path = str(project_root / config.ruleset_path)
    if not Path(config.term_dictionaries_path).is_absolute():
        config.term_dictionaries_path = str(project_root / config.term_dictionaries_path)
    if not Path(config.output_config.storage_path).is_absolute():
        config.output_config.storage_path = str(
            project_root / config.output_config.storage_path
        )

    agent = MCPAgent(config)
    results = agent.run()
    print(f"Processed {len(results)} pages. Results saved to {config.output_config.storage_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
