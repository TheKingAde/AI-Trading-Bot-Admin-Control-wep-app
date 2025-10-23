import os
import asyncio
from datetime import datetime

# Determine repo root automatically
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_PATH = os.path.dirname(SCRIPT_DIR)

async def run_cmd(*args):
    proc = await asyncio.create_subprocess_exec(*args)
    await proc.wait()
    return proc.returncode

async def git_auto_push(branch: str, commit_message: str):
    os.chdir(REPO_PATH)

    # Add and commit
    await run_cmd("git", "add", ".")
    await run_cmd("git", "commit", "-m", commit_message)

    print(f"⬆️ Pushing changes to branch '{branch}'...")
    await run_cmd("git", "push", "origin", branch)

async def main():
    print("📁 Repo Path:", REPO_PATH)

    # Ask for branch name (default = main)
    branch = input("Enter branch name [default: main]: ").strip() or "main"

    # Ask for commit message
    commit_message = input("Enter commit message: ").strip()
    if not commit_message:
        commit_message = f"update file"

    try:
        await git_auto_push(branch, commit_message)
        print("✅ Push complete.")
    except KeyboardInterrupt:
        print("\nProgram stopped by user ✅")

if __name__ == "__main__":
    asyncio.run(main())