import os
import asyncio
from datetime import datetime

REPO_PATH = r"C:\Users\User\OneDrive\Documents\dailycb_model_training_data\bot-dashboad-and-control-station"
BRANCH = "main"

async def run_cmd(*args):
    proc = await asyncio.create_subprocess_exec(*args)
    await proc.wait()
    return proc.returncode

async def git_auto_push():
    os.chdir(REPO_PATH)
    print("🔄 Pulling latest changes...")
    ret = await run_cmd("git", "pull", "origin", BRANCH, "--no-edit")
    if ret != 0:
        print("⚠️ Git pull failed. Resolve conflicts manually.")
        return

    await run_cmd("git", "add", ".")
    commit_message = f"fix export issue"
    await run_cmd("git", "commit", "-m", commit_message)
    print("⬆️ Pushing changes...")
    await run_cmd("git", "push", "origin", BRANCH)

async def main():
    try:
        await git_auto_push()
    except KeyboardInterrupt:
        print("\nProgram stopped by user ✅")

if __name__ == "__main__":
    asyncio.run(main())
