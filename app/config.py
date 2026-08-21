import os

from dotenv import load_dotenv


load_dotenv()

WORKSPACE = os.getenv(
    "WORKSPACE",
    "/home/eodadmin/development-mcp/workspace",
)

GITHUB_TOKEN = os.getenv(
    "GITHUB_TOKEN",
    "",
)

LOG_DIR = os.getenv(
    "LOG_DIR",
    "/home/eodadmin/development-mcp/logs",
)

