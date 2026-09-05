import time
import sys
import logging
from datetime import datetime, timezone, timedelta

from streak_db import init_db, get_settings, update_settings, get_queue, update_queue_item, record_history
from github_client import GitHubClient
from fallback_generator import generate_fallback_commit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

def execute_commit_item(gh, item):
    content = item.get("content", "")
    file_path = item.get("file_path", "")
    repo = item["repo"]
    branch = item.get("branch", "main")
    message = item["commit_message"]
    
    if file_path == "__bundle__" or '"__bundle__":' in content or '"files":' in content:
        try:
            bundle_data = json.loads(content)
            files = bundle_data.get("files", {})
            if files:
                return gh.push_files(
                    repo=repo,
                    files=files,
                    message=message,
                    branch=branch
                )
        except Exception as e:
            logging.warning(f"Failed to parse bundle json, falling back to push_file: {e}")

    return gh.push_file(
        repo=repo,
        file_path=file_path,
        content=content,
        message=message,
        branch=branch
    )

def run_scheduler_tick():
    settings = get_settings()
    gh = GitHubClient(
        user=settings.get("author_name", "comeraperuibe944"),
        email=settings.get("author_email", "juanperuibe6@gmail.com")
    )
    
    target_tz = timezone(timedelta(hours=-3))
    now = datetime.now(target_tz)
    today_date = now.strftime("%Y-%m-%d")
    current_time_str = now.strftime("%H:%M")
    fallback_time = settings.get("fallback_time", "20:45")
    last_fallback_date = settings.get("last_fallback_date", "")
    fallback_enabled = settings.get("fallback_enabled", "true").lower() == "true"
    check_first = settings.get("check_manual_commits_first", "true").lower() == "true"
    fallback_repo = settings.get("fallback_repo", "comeraperuibe944/streak-keeper")
    fallback_type = settings.get("fallback_type", "telemetry")

    # 1. Process specific scheduled items in the queue
    pending_items = get_queue(status="pending")
    for item in pending_items:
        sched = item.get("scheduled_at")
        if sched:
            try:
                sched_dt = datetime.fromisoformat(sched)
                if sched_dt.tzinfo is None:
                    sched_dt = sched_dt.replace(tzinfo=target_tz)
                if now >= sched_dt:
                    logging.info(f"Executing scheduled queue item #{item['id']} for repo {item['repo']}")
                    try:
                        res = execute_commit_item(gh, item)
                        update_queue_item(item["id"], status="completed", commit_sha=res["sha"])
                        record_history(
                            repo=item["repo"],
                            commit_sha=res["sha"],
                            commit_message=item["commit_message"],
                            commit_type="queued",
                            status="success",
                            details=f"URL: {res.get('url')}"
                        )
                        logging.info(f"Queue item #{item['id']} executed successfully. SHA: {res['sha']}")
                    except Exception as e:
                        logging.error(f"Error executing queue item #{item['id']}: {e}")
                        update_queue_item(item["id"], status="failed", error=str(e))
                        record_history(
                            repo=item["repo"],
                            commit_sha=None,
                            commit_message=item["commit_message"],
                            commit_type="queued",
                            status="failed",
                            details=str(e)
                        )
            except Exception as e:
                logging.error(f"Failed to parse scheduled time '{sched}': {e}")

    # 2. Check if end-of-day trigger has arrived
    if fallback_enabled and current_time_str == fallback_time and last_fallback_date != today_date:
        logging.info(f"End-of-day trigger reached at {current_time_str} (Target: {fallback_time})")

        # Check if user already committed today on GitHub
        if check_first:
            logging.info("Checking if user has already committed today on GitHub...")
            check_res = gh.check_committed_today()
            if check_res.get("has_committed_today"):
                logging.info(f"User already committed today ({check_res.get('commit_count')} commits). Streak preserved! Skipping fallback.")
                update_settings({"last_fallback_date": today_date})
                record_history(
                    repo="all",
                    commit_sha=None,
                    commit_message="Skip: User already made commits today",
                    commit_type="skipped",
                    status="success",
                    details=f"Found {check_res.get('commit_count')} commits today."
                )
                return

        # If we need a commit, check if there are pending items in queue (FIFO)
        remaining_pending = get_queue(status="pending")
        if remaining_pending:
            next_item = remaining_pending[0]
            logging.info(f"Consuming next queue item #{next_item['id']} for streak keeper")
            try:
                res = execute_commit_item(gh, next_item)
                update_queue_item(next_item["id"], status="completed", commit_sha=res["sha"])
                record_history(
                    repo=next_item["repo"],
                    commit_sha=res["sha"],
                    commit_message=next_item["commit_message"],
                    commit_type="queued",
                    status="success",
                    details=f"URL: {res.get('url')}"
                )
                update_settings({"last_fallback_date": today_date})
                logging.info(f"Queue item #{next_item['id']} committed for streak. SHA: {res['sha']}")
            except Exception as e:
                logging.error(f"Error executing queue item #{next_item['id']}: {e}")
                update_queue_item(next_item["id"], status="failed", error=str(e))
        else:
            # Queue is empty: Generate fallback commit
            logging.info(f"Queue is empty! Generating automated fallback commit to {fallback_repo}...")
            fallback_data = generate_fallback_commit(fallback_type)
            try:
                res = gh.push_file(
                    repo=fallback_repo,
                    file_path=fallback_data["file_path"],
                    content=fallback_data["content"],
                    message=fallback_data["commit_message"],
                    branch="main"
                )
                record_history(
                    repo=fallback_repo,
                    commit_sha=res["sha"],
                    commit_message=fallback_data["commit_message"],
                    commit_type="fallback",
                    status="success",
                    details=f"URL: {res.get('url')}"
                )
                update_settings({"last_fallback_date": today_date})
                logging.info(f"Fallback commit pushed successfully! SHA: {res['sha']}")
            except Exception as e:
                logging.error(f"Error pushing fallback commit: {e}")
                record_history(
                    repo=fallback_repo,
                    commit_sha=None,
                    commit_message=fallback_data["commit_message"],
                    commit_type="fallback",
                    status="failed",
                    details=str(e)
                )

def main():
    logging.info("Starting Streak Keeper Scheduler Daemon...")
    init_db()
    while True:
        try:
            run_scheduler_tick()
        except Exception as e:
            logging.error(f"Scheduler tick error: {e}")
        time.sleep(30)

if __name__ == "__main__":
    main()
