import argparse
import os
from datetime import datetime, timezone


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def append_behavior_log(wiki_root: str, prompt: str, user: str = "test-user"):
    bl_path = os.path.join(wiki_root, "Behavior-Log.md")
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    entry_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    entry = [
        f"### OBS-{entry_id}",
        "",
        f"- Timestamp (UTC): {ts}",
        f"- Request Type: interactive-prompt",
        f"- User: {user}",
        f"- Prompt: |\n  {prompt}",
        f"- Outcome: persisted-test",
        "",
    ]
    with open(bl_path, "a", encoding="utf-8") as f:
        f.write("\n".join(entry))


def write_transcript(wiki_root: str, prompt: str):
    artifacts_dir = os.path.join(wiki_root, "artifacts")
    ensure_dir(artifacts_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"transcript-{ts}.txt"
    path = os.path.join(artifacts_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}\n")
        f.write("Prompt:\n")
        f.write(prompt)
    return path


def main():
    parser = argparse.ArgumentParser(description="Trigger a test prompt and persist logs to .wiki/orchestrator")
    parser.add_argument("--prompt", "-p", required=True, help="Prompt text to persist")
    parser.add_argument("--wiki", "-w", default=".wiki/orchestrator", help="Wiki root folder")
    parser.add_argument("--user", "-u", default="test-user", help="User name to record")
    args = parser.parse_args()

    wiki_root = args.wiki
    ensure_dir(wiki_root)
    append_behavior_log(wiki_root, args.prompt, user=args.user)
    transcript = write_transcript(wiki_root, args.prompt)
    print(f"Persisted prompt to Behavior-Log.md and transcript: {transcript}")


if __name__ == "__main__":
    main()
