import json
import base64
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
DEFAULT_USER = "comeraperuibe944"
DEFAULT_EMAIL = "juanperuibe6@gmail.com"

class GitHubClient:
    def __init__(self, token=GITHUB_TOKEN, user=DEFAULT_USER, email=DEFAULT_EMAIL):
        self.token = token
        self.user = user
        self.email = email
        self.headers = {
            "Authorization": f"token {self.token}",
            "User-Agent": "StreakKeeper-Bot/1.0",
            "Accept": "application/vnd.github.v3+json"
        }

    def _request(self, url, method="GET", data=None):
        payload = None
        if data is not None:
            payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
                return status, json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(error_body)
            except Exception:
                err_json = {"message": error_body}
            return e.code, err_json
        except Exception as e:
            return 500, {"message": str(e)}

    def normalize_repo(self, repo: str) -> str:
        repo = repo.strip()
        if "/" not in repo:
            return f"{self.user}/{repo}"
        return repo

    def get_file(self, repo: str, file_path: str, branch: str = "main"):
        repo = self.normalize_repo(repo)
        url = f"https://api.github.com/repos/{repo}/contents/{file_path}?ref={branch}"
        status, data = self._request(url)
        if status == 200:
            return data
        return None

    def push_file(self, repo: str, file_path: str, content: str, message: str, branch: str = "main", author_name: str = None, author_email: str = None):
        repo = self.normalize_repo(repo)
        author_name = author_name or self.user
        author_email = author_email or self.email

        # Check if file exists to acquire sha
        existing = self.get_file(repo, file_path, branch)
        sha = existing.get("sha") if existing else None

        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        now_iso = datetime.now(timezone(timedelta(hours=-3))).isoformat()
        payload = {
            "message": message,
            "content": encoded_content,
            "branch": branch,
            "author": {
                "name": author_name,
                "email": author_email,
                "date": now_iso
            },
            "committer": {
                "name": author_name,
                "email": author_email,
                "date": now_iso
            }
        }
        if sha:
            payload["sha"] = sha

        url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
        status, data = self._request(url, method="PUT", data=payload)
        
        if status in (200, 201):
            commit_sha = data.get("commit", {}).get("sha", "")
            commit_url = data.get("commit", {}).get("html_url", "")
            return {
                "success": True,
                "sha": commit_sha,
                "url": commit_url,
                "message": message,
                "repo": repo,
                "file_path": file_path
            }
        else:
            err_msg = data.get("message", f"HTTP {status}")
            raise RuntimeError(f"GitHub API Error: {err_msg}")

    def push_files(self, repo: str, files: dict, message: str, branch: str = "main", author_name: str = None, author_email: str = None, date_str: str = None):
        repo = self.normalize_repo(repo)
        author_name = author_name or self.user
        author_email = author_email or self.email
        if not date_str:
            date_str = datetime.now(timezone(timedelta(hours=-3))).isoformat()

        # 1. Get branch ref
        status, ref_data = self._request(f"https://api.github.com/repos/{repo}/git/ref/heads/{branch}")
        if status != 200 or "object" not in ref_data:
            raise RuntimeError(f"Failed to get branch ref: {ref_data.get('message', status)}")
        latest_commit_sha = ref_data["object"]["sha"]

        # 2. Get commit base tree
        status, commit_data = self._request(f"https://api.github.com/repos/{repo}/git/commits/{latest_commit_sha}")
        if status != 200 or "tree" not in commit_data:
            raise RuntimeError(f"Failed to get commit tree: {commit_data.get('message', status)}")
        base_tree_sha = commit_data["tree"]["sha"]

        # 3. Create blobs for each file
        tree_items = []
        for file_path, content in files.items():
            status, blob_data = self._request(
                f"https://api.github.com/repos/{repo}/git/blobs",
                method="POST",
                data={"content": content, "encoding": "utf-8"}
            )
            if status not in (200, 201) or "sha" not in blob_data:
                raise RuntimeError(f"Failed to create blob for {file_path}: {blob_data.get('message', status)}")
            tree_items.append({
                "path": file_path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_data["sha"]
            })

        # 4. Create new tree
        status, new_tree = self._request(
            f"https://api.github.com/repos/{repo}/git/trees",
            method="POST",
            data={"base_tree": base_tree_sha, "tree": tree_items}
        )
        if status not in (200, 201) or "sha" not in new_tree:
            raise RuntimeError(f"Failed to create tree: {new_tree.get('message', status)}")
        new_tree_sha = new_tree["sha"]

        # 5. Create new commit
        commit_payload = {
            "message": message,
            "tree": new_tree_sha,
            "parents": [latest_commit_sha],
            "author": {
                "name": author_name,
                "email": author_email,
                "date": date_str
            },
            "committer": {
                "name": author_name,
                "email": author_email,
                "date": date_str
            }
        }
        status, new_commit = self._request(
            f"https://api.github.com/repos/{repo}/git/commits",
            method="POST",
            data=commit_payload
        )
        if status not in (200, 201) or "sha" not in new_commit:
            raise RuntimeError(f"Failed to create commit: {new_commit.get('message', status)}")
        new_commit_sha = new_commit["sha"]

        # 6. Update branch ref
        status, updated_ref = self._request(
            f"https://api.github.com/repos/{repo}/git/refs/heads/{branch}",
            method="PATCH",
            data={"sha": new_commit_sha}
        )
        if status not in (200, 201):
            raise RuntimeError(f"Failed to update ref: {updated_ref.get('message', status)}")

        return {
            "success": True,
            "sha": new_commit_sha,
            "url": f"https://github.com/{repo}/commit/{new_commit_sha}",
            "message": message,
            "repo": repo,
            "files_count": len(files)
        }

    def check_committed_today(self, tz_offset_hours: int = -3):
        target_tz = timezone(timedelta(hours=tz_offset_hours))
        now_local = datetime.now(target_tz)
        today_date_str = now_local.strftime("%Y-%m-%d")

        # Use search commits API for instant detection
        search_url = f"https://api.github.com/search/commits?q=author:{self.user}+author-date:>={today_date_str}&sort=author-date&order=desc"
        status, data = self._request(search_url)

        if status == 200 and "total_count" in data:
            total = data.get("total_count", 0)
            items = data.get("items", [])
            last_commit_time = None
            last_commit_msg = None
            last_repo = None
            if items:
                first = items[0]
                last_commit_time = first.get("commit", {}).get("author", {}).get("date")
                last_commit_msg = first.get("commit", {}).get("message")
                last_repo = first.get("repository", {}).get("full_name")
            return {
                "has_committed_today": total > 0,
                "commit_count": total,
                "last_commit_time": last_commit_time,
                "last_commit_msg": last_commit_msg,
                "last_repo": last_repo,
                "today_date": today_date_str
            }

        # Fallback to events API if search fails or rate limits
        events_url = f"https://api.github.com/users/{self.user}/events/public?per_page=100"
        status, events = self._request(events_url)

        if status != 200 or not isinstance(events, list):
            return {
                "has_committed_today": False,
                "commit_count": 0,
                "last_commit_time": None,
                "today_date": today_date_str,
                "error": events.get("message", "Failed to fetch events") if isinstance(events, dict) else "Unknown"
            }

        commits_today = 0
        last_commit_iso = None
        for event in events:
            if event.get("type") == "PushEvent":
                created_at_str = event.get("created_at")
                if created_at_str:
                    utc_dt = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    local_dt = utc_dt.astimezone(target_tz)
                    if local_dt.strftime("%Y-%m-%d") == today_date_str:
                        payload = event.get("payload", {})
                        num_commits = len(payload.get("commits", [])) or 1
                        commits_today += num_commits
                        if not last_commit_iso:
                            last_commit_iso = local_dt.strftime("%Y-%m-%d %H:%M:%S")

        return {
            "has_committed_today": commits_today > 0,
            "commit_count": commits_today,
            "last_commit_time": last_commit_iso,
            "today_date": today_date_str
        }

    def list_repos(self):
        url = "https://api.github.com/user/repos?per_page=100&sort=updated"
        status, repos = self._request(url)
        if status == 200 and isinstance(repos, list):
            return [
                {
                    "name": r["name"],
                    "full_name": r["full_name"],
                    "private": r["private"],
                    "default_branch": r.get("default_branch", "main")
                }
                for r in repos
            ]
        return []
