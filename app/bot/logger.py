import logging
import queue
from pathlib import Path
from datetime import date
from logging.handlers import QueueHandler, QueueListener

LOG_PATH = Path(__file__).resolve().parent / "log" / f"{date.today()}.txt"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

log_queue = queue.Queue()

stream_handler = logging.StreamHandler()

file_handler = logging.FileHandler(
    LOG_PATH,
    encoding="utf-8"
)

formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

stream_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

queue_handler = QueueHandler(log_queue)
queue_handler.setFormatter(logging.Formatter("%(message)s"))

listener = QueueListener(
    log_queue,
    stream_handler,
    file_handler
)

logging.basicConfig(
    level=logging.INFO,
    handlers=[queue_handler],
    force=True
)

listener.start()

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)