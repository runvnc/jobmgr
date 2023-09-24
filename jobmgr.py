#!/usr/bin/env python3

import os
import sys
import subprocess
import logging
import signal
import time
from concurrent.futures import ThreadPoolExecutor
import threading

# File paths for storing job information
JOBS_FILE = "jobs.txt"
STATUS_FILE = "status.txt"
OUTPUT_DIR = "output"
PIDS_FILE = "pids.txt"
DAEMON_LOCK_FILE = 'jobmgr.lock'

logging.basicConfig(filename='jobmgr.log', level=logging.INFO, 
                    format='[%(asctime)s] %(levelname)s: %(message)s')

file_lock = threading.Lock()

def initialize():
    if not os.path.exists(JOBS_FILE):
        open(JOBS_FILE, 'w').close()
    if not os.path.exists(STATUS_FILE):
        open(STATUS_FILE, 'w').close()
    if not os.path.exists(OUTPUT_DIR):
        os.mkdir(OUTPUT_DIR)
    if not os.path.exists(PIDS_FILE):
        open(PIDS_FILE, 'w').close()

def add_job(command):
    with open(JOBS_FILE, 'a') as f:
        f.write(command + '\n')
    with open(STATUS_FILE, 'a') as f:
        f.write("PENDING\n")
    logging.info(f"Added job: {command}")

def list_jobs():
    with open(JOBS_FILE, 'r') as jf, open(STATUS_FILE, 'r') as sf:
        jobs = jf.readlines()
        statuses = sf.readlines()
    for idx, (job, status) in enumerate(zip(jobs, statuses)):
        print(f"{idx + 1}. [{status.strip()}] {job.strip()}")

def run_job(idx, job):
    try:
        current_shell = os.environ.get("SHELL", "/bin/sh")
        logging.info(f"Starting job {idx + 1} in shell {current_shell}: {job.strip()}")
        proc = subprocess.Popen([current_shell, "-c", job.strip()], env=os.environ, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)

        stdout, stderr = proc.communicate()  # This will wait for the process to complete and retrieve its outputs

        with file_lock, open(os.path.join(OUTPUT_DIR, f"job_{idx + 1}.txt"), 'w') as f:
            f.write(stdout)
            if stderr:
                f.write("\n--- Errors ---\n")
                f.write(stderr)

        if proc.returncode == 0:
            update_status(idx, "COMPLETED")
            logging.info(f"Completed job {idx + 1}: {job.strip()}")
        else:
            update_status(idx, "ERROR")
            logging.error(f"Error in job {idx + 1} with code {proc.returncode}: {job.strip()}")
    except Exception as e:
        logging.error(f"Error running job {idx + 1}: {e}")
        update_status(idx, "ERROR")


def run_jobs_parallel():
    executor = ThreadPoolExecutor(max_workers=10)  # Start tasks and return immediately
    with open(JOBS_FILE, 'r') as jf, open(STATUS_FILE, 'r') as sf:
        jobs = jf.readlines()
        statuses = sf.readlines()
    for idx, (job, status) in enumerate(zip(jobs, statuses)):
        if status.strip() == "PENDING":
            executor.submit(run_job, idx, job)

def update_status(job_idx, status):
    with file_lock:
        with open(STATUS_FILE, 'r') as f:
            statuses = f.readlines()
        statuses[job_idx] = f"{status}\n"
        with open(STATUS_FILE, 'w') as f:
            f.writelines(statuses)

def pause_job(job_id):
    with open(PIDS_FILE, 'r') as f:
        lines = f.readlines()
    for line in lines:
        idx, pid = map(int, line.strip().split(":"))
        if idx == job_id:
            os.kill(pid, signal.SIGSTOP)
            update_status(job_id - 1, "PAUSED")
            logging.info(f"Paused job {job_id}")

def resume_job(job_id):
    with open(PIDS_FILE, 'r') as f:
        lines = f.readlines()
    for line in lines:
        idx, pid = map(int, line.strip().split(":"))
        if idx == job_id:
            os.kill(pid, signal.SIGCONT)
            update_status(job_id - 1, "RUNNING")
            logging.info(f"Resumed job {job_id}")

def view_output(job_id):
    output_file = os.path.join(OUTPUT_DIR, f"job_{job_id}.txt")
    if os.path.exists(output_file):
        with open(output_file, 'r') as f:
            print(f.read())
    else:
        print(f"No output yet for job {job_id}.")


def is_daemon_running():
    return os.path.exists(DAEMON_LOCK_FILE)

def start_daemon():
    if is_daemon_running():
        print("Daemon is already running!")
        return

    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    else:
        with open(DAEMON_LOCK_FILE, 'w') as lock_file:
            lock_file.write(str(os.getpid()))
        main_loop()

def stop_daemon():
    if not is_daemon_running():
        print("Daemon is not running!")
        return

    with open(DAEMON_LOCK_FILE, 'r') as lock_file:
        pid = int(lock_file.readline().strip())

    os.kill(pid, signal.SIGTERM)
    os.remove(DAEMON_LOCK_FILE)
    print("Daemon stopped.")

def main_loop():
    while True:
        run_jobs_parallel()
        time.sleep(10)

def delete_job(job_id):
    with file_lock:
        with open(JOBS_FILE, 'r') as jf, open(STATUS_FILE, 'r') as sf:
            jobs = jf.readlines()
            statuses = sf.readlines()
        if 0 < job_id <= len(jobs):
            del jobs[job_id - 1]
            del statuses[job_id - 1]
        with open(JOBS_FILE, 'w') as jf, open(STATUS_FILE, 'w') as sf:
            jf.writelines(jobs)
            sf.writelines(statuses)

def clean_jobs():
    with file_lock:
        with open(JOBS_FILE, 'r') as jf, open(STATUS_FILE, 'r') as sf:
            jobs = jf.readlines()
            statuses = sf.readlines()
        clean_jobs = [job for job, status in zip(jobs, statuses) if status.strip() not in ["COMPLETED", "ERROR"]]
        clean_statuses = [status for status in statuses if status.strip() not in ["COMPLETED", "ERROR"]]
        with open(JOBS_FILE, 'w') as jf, open(STATUS_FILE, 'w') as sf:
            jf.writelines(clean_jobs)
            sf.writelines(clean_statuses)

def main():
    if len(sys.argv) < 2:
        print("Usage: ./jobmgr.py {add|list|run|pause|resume|view|start|stop|delete|clean} [command_or_job_id]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "start":
        start_daemon()
    elif action == "stop":
        stop_daemon()
    elif action == "add" and len(sys.argv) > 2:
        add_job(sys.argv[2])
    elif action == "delete" and len(sys.argv) > 2:
        delete_job(int(sys.argv[2]))
    elif action == "clean":
        clean_jobs()
    elif action == "list":
        list_jobs()
    elif action == "run":
        run_jobs_parallel()
    elif action == "pause" and len(sys.argv) > 2:
        pause_job(int(sys.argv[2]))
    elif action == "resume" and len(sys.argv) > 2:
        resume_job(int(sys.argv[2]))
    elif action == "view" and len(sys.argv) > 2:
        view_output(int(sys.argv[2]))
    else:
        print("Invalid command. Use: ./jobmgr.py {add|list|run|pause|resume|view} [command_or_job_id]")

    if not is_daemon_running():
        print("Daemon is not running. Start it with './jobmgr.py start'")

if __name__ == "__main__":
    initialize()
    main()

