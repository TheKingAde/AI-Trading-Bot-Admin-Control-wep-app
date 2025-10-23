import os
import asyncio
from datetime import datetime
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_PATH = os.path.dirname(SCRIPT_DIR)
print("Repo Path:", REPO_PATH)
BRANCH = "main"
commit_message = f"fix drawdown calculation"

async def run_cmd(*args):
    proc = await asyncio.create_subprocess_exec(*args)
    await proc.wait()
    return proc.returncode

async def git_auto_push():
    os.chdir(REPO_PATH)
    await run_cmd("git", "add", ".")
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
