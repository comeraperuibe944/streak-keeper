import time
import sys
import json
import logging
from datetime import datetime, timezone, timedelta

from streak_db import (
    init_db, get_settings, update_settings, get_queue, 
    update_queue_item, record_history, check_action_done_today
)
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
    
    # 1. Repository creation item
    if file_path == "__create_repo__" or '"__create_repo__":' in content:
        try:
            data = json.loads(content)
        except Exception:
            data = {}
        repo_name = data.get("repo_name") or repo
        raw_name = repo_name.split("/")[-1] if "/" in repo_name else repo_name
        description = data.get("description", "")
        private = data.get("private", False)
        files = data.get("files", {})
        
        full_repo_name = f"{gh.user}/{raw_name}"
        if not gh.repo_exists(full_repo_name):
            gh.create_repo(raw_name, description=description, private=private, auto_init=True)
            time.sleep(2)
            
        if files:
            res = gh.push_files(
                repo=full_repo_name,
                files=files,
                message=message or "Initial commit",
                branch=branch
            )
            return res
        return {
            "success": True,
            "sha": "init",
            "url": f"https://github.com/{full_repo_name}",
            "repo": full_repo_name
        }

    # 2. Multi-file bundle commit
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

    # 3. Single file push
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
    repo_post_time = settings.get("repo_post_time", "06:00")
    last_fallback_date = settings.get("last_fallback_date", "")
    last_repo_post_date = settings.get("last_repo_post_date", "")
    
    fallback_enabled = settings.get("fallback_enabled", "true").lower() == "true"
    check_first = settings.get("check_manual_commits_first", "true").lower() == "true"
    fallback_repo = settings.get("fallback_repo", "comeraperuibe944/streak-keeper")
    fallback_type = settings.get("fallback_type", "telemetry")

    # 1. Process specific scheduled items in the queue (ONLY items where scheduled_at <= now)
    pending_items = get_queue(status="pending")
    
    due_items = []
    for item in pending_items:
        sched = item.get("scheduled_at")
        if sched:
            try:
                sched_dt = datetime.fromisoformat(sched)
                if sched_dt.tzinfo is None:
                    sched_dt = sched_dt.replace(tzinfo=target_tz)
                if now >= sched_dt:
                    due_items.append((sched_dt, item))
            except Exception as e:
                logging.error(f"Failed to parse scheduled time '{sched}' for item #{item['id']}: {e}")

    # Sort due items so oldest scheduled runs first
    due_items.sort(key=lambda x: x[0])

    if due_items:
        # Check if an action was already performed today
        if check_action_done_today(tz_offset_hours=-3):
            logging.info(f"An action was already executed today ({today_date}). Waiting for scheduled items of future days.")
        else:
            _, target_item = due_items[0]
            logging.info(f"Executing scheduled queue item #{target_item['id']} for repo {target_item['repo']} (Scheduled: {target_item.get('scheduled_at')})")
            try:
                res = execute_commit_item(gh, target_item)
                update_queue_item(target_item["id"], status="completed", commit_sha=res.get("sha"))
                record_history(
                    repo=target_item["repo"],
                    commit_sha=res.get("sha"),
                    commit_message=target_item["commit_message"],
                    commit_type="queued",
                    status="success",
                    details=f"URL: {res.get('url')}"
                )
                update_settings({
                    "last_action_date": today_date,
                    "last_fallback_date": today_date,
                    "last_repo_post_date": today_date
                })
                logging.info(f"Queue item #{target_item['id']} executed successfully. SHA: {res.get('sha')}")
                return
            except Exception as e:
                logging.error(f"Error executing queue item #{target_item['id']}: {e}")
                update_queue_item(target_item["id"], status="failed", error=str(e))
                record_history(
                    repo=target_item["repo"],
                    commit_sha=None,
                    commit_message=target_item["commit_message"],
                    commit_type="queued",
                    status="failed",
                    details=str(e)
                )
                return

    # 2. Morning trigger for UNSCHEDULED items (06:00 BRT)
    # STRICT RULE: NEVER touch items with a future scheduled_at! Only unscheduled items.
    if current_time_str == repo_post_time and last_repo_post_date != today_date:
        if not check_action_done_today(tz_offset_hours=-3):
            remaining_pending = get_queue(status="pending")
            unscheduled_items = [it for it in remaining_pending if not it.get("scheduled_at")]
            if unscheduled_items:
                target_item = unscheduled_items[0]
                logging.info(f"Morning trigger (06:00 BRT): Executing unscheduled queue item #{target_item['id']} for {target_item['repo']}")
                try:
                    res = execute_commit_item(gh, target_item)
                    update_queue_item(target_item["id"], status="completed", commit_sha=res.get("sha"))
                    record_history(
                        repo=target_item["repo"],
                        commit_sha=res.get("sha"),
                        commit_message=target_item["commit_message"],
                        commit_type="queued",
                        status="success",
                        details=f"URL: {res.get('url')}"
                    )
                    update_settings({
                        "last_action_date": today_date,
                        "last_repo_post_date": today_date,
                        "last_fallback_date": today_date
                    })
                    logging.info(f"Morning queue item #{target_item['id']} executed. SHA: {res.get('sha')}")
                    return
                except Exception as e:
                    logging.error(f"Error executing morning queue item #{target_item['id']}: {e}")
                    update_queue_item(target_item["id"], status="failed", error=str(e))
                    return

    # 3. Night Fallback Trigger (20:45 BRT)
    if fallback_enabled and current_time_str == fallback_time and last_fallback_date != today_date:
        logging.info(f"End-of-day trigger reached at {current_time_str} (Target: {fallback_time})")

        # 3.1 Check local history first (100% reliable, zero API latency/indexing lag)
        if check_action_done_today(tz_offset_hours=-3):
            logging.info(f"Local streak keeper action already recorded for today ({today_date}). Skipping fallback.")
            update_settings({"last_fallback_date": today_date})
            record_history(
                repo="all",
                commit_sha=None,
                commit_message="Skip: Action already executed today",
                commit_type="skipped",
                status="success",
                details=f"Local streak action already completed today."
            )
            return

        # 3.2 Check if user made manual commits directly to GitHub today
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

        # 3.3 If still no commit today, check if there are UNSCHEDULED pending items
        # STRICT RULE: Under NO circumstances consume future scheduled items!
        remaining_pending = get_queue(status="pending")
        unscheduled_pending = [it for it in remaining_pending if not it.get("scheduled_at")]
        if unscheduled_pending:
            next_item = unscheduled_pending[0]
            logging.info(f"Consuming unscheduled queue item #{next_item['id']} for streak keeper")
            try:
                res = execute_commit_item(gh, next_item)
                update_queue_item(next_item["id"], status="completed", commit_sha=res.get("sha"))
                record_history(
                    repo=next_item["repo"],
                    commit_sha=res.get("sha"),
                    commit_message=next_item["commit_message"],
                    commit_type="queued",
                    status="success",
                    details=f"URL: {res.get('url')}"
                )
                update_settings({
                    "last_action_date": today_date,
                    "last_fallback_date": today_date
                })
                logging.info(f"Queue item #{next_item['id']} committed for streak. SHA: {res.get('sha')}")
                return
            except Exception as e:
                logging.error(f"Error executing queue item #{next_item['id']}: {e}")
                update_queue_item(next_item["id"], status="failed", error=str(e))
                return

        # 3.4 Queue has no unscheduled items: Generate automated fallback commit
        logging.info(f"Queue has no unscheduled items. Generating automated fallback commit to {fallback_repo}...")
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
            update_settings({
                "last_action_date": today_date,
                "last_fallback_date": today_date
            })
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
