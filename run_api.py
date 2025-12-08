#!/usr/bin/env python3
"""
Algamol API Server
Convenience script to run the FastAPI server.
"""

import uvicorn
from src.config import load_config, get_config

if __name__ == "__main__":
    load_config()
    config = get_config()

    print(f"Starting Algamol API server on {config.api.host}:{config.api.port}")
    print(f"API documentation: http://{config.api.host}:{config.api.port}/docs")

    uvicorn.run(
        "src.api:app",
        host=config.api.host,
        port=config.api.port,
        reload=False
    )
