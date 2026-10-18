#!/usr/bin/env python
"""Run the 804 Hacks Carbon API server."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)