"""
Modern Gunicorn configuration for ASGI/Uvicorn workers
"""
import multiprocessing
import os

# Server socket
bind = "0.0.0.0:8080"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
# Restart workers after this many requests, with up to 50 random jitter
# This helps prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Restart workers after this many seconds
max_worker_age = 3600

# Timeout for requests
timeout = 30
keepalive = 2

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "giraffe"

# Server mechanics
preload_app = True
daemon = False
pidfile = "/tmp/gunicorn.pid"
user = os.getuid()
group = os.getgid()
tmp_upload_dir = None

# SSL (if needed)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Uvicorn specific settings (passed to uvicorn workers)
# These are set as environment variables or passed to uvicorn
uvicorn_settings = {
    "loop": "uvloop",  # Use uvloop for better performance
    "http": "httptools",  # Use httptools for better HTTP parsing
    "lifespan": "on",  # Enable lifespan events
    "interface": "asgi3",  # Use ASGI 3 interface
}

# Worker configuration
def worker_int(worker):
    """Called just after a worker has been forked."""
    worker.log.info("Worker spawned (pid: %s)", worker.pid)

def worker_abort(worker):
    """Called when a worker receives the SIGABRT signal."""
    worker.log.info("Worker received SIGABRT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_exec(server):
    """Called just before a new master process is forked."""
    server.log.info("Forked child, re-executing.")

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Server is ready. Spawning workers")

def worker_exit(server, worker):
    """Called just after a worker has been exited."""
    server.log.info("Worker exited (pid: %s)", worker.pid)

def pre_request(worker, req):
    """Called just before a worker processes the request."""
    worker.log.debug("%s %s", req.method, req.path)

def post_request(worker, req, environ, resp):
    """Called just after a worker processes the request."""
    worker.log.debug("%s %s - %s", req.method, req.path, resp.status_code) 