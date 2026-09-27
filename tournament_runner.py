#!/usr/bin/env python3
"""
Continuous Tournament Runner
Spawns multiple bots that automatically re-queue for new games after each match.
"""

import subprocess
import time
import sys
import signal
from typing import List, Optional

class TournamentRunner:
    def __init__(
        self,
        num_bots: int = 4,
        ollama_model: str = "mistral",
        prompts_file: str = "prompts.yaml",
        prompt_names: Optional[List[str]] = None,
        base_url: str = "http://localhost:8000",
    ):
        self.num_bots = num_bots
        self.ollama_model = ollama_model
        self.prompts_file = prompts_file
        self.base_url = base_url
        # Cycle through the given prompt variants across bots (e.g. 4 bots,
        # 2 names -> bots 1&3 get name[0], bots 2&4 get name[1]), so you can
        # A/B test prompts.yaml variants against each other in one tournament.
        self.prompt_names = prompt_names or ["default"]
        self.processes: List[subprocess.Popen] = []
        self.running = True

    def spawn_bot(self, bot_num: int) -> subprocess.Popen:
        """Spawn a single bot process."""
        prompt_name = self.prompt_names[(bot_num - 1) % len(self.prompt_names)]
        cmd = [
            "python3",
            "ollama_bot.py",
            "--agent-name", f"Bot{bot_num}",
            "--developer-handle", "tournament",
            "--model", self.ollama_model,
            "--prompts-file", self.prompts_file,
            "--prompt-name", prompt_name,
            "--base-url", self.base_url,
        ]
        print(f"[TOURNAMENT] Spawning Bot {bot_num} (prompt: {prompt_name})...")
        process = subprocess.Popen(cmd)
        return process

    def run(self):
        """Main tournament loop."""
        print(f"\n{'='*70}")
        print(f"🏆 MICRO-DIPLOMACY CONTINUOUS TOURNAMENT 🏆")
        print(f"{'='*70}")
        print(f"Spawning {self.num_bots} bots (model: {self.ollama_model})")
        print(f"Bots will automatically re-queue after each game")
        print(f"Press Ctrl+C to stop all bots\n")

        # Clear any stale agents in the queue from previous runs
        try:
            resp = self.make_request("POST", "/queue/clear")
            print(f"[TOURNAMENT] Cleared stale agents from queue\n")
        except Exception as e:
            print(f"[TOURNAMENT] Note: queue clear not available ({e})\n")

        # Spawn initial bots
        for i in range(1, self.num_bots + 1):
            proc = self.spawn_bot(i)
            self.processes.append(proc)
            time.sleep(1)  # Stagger startup

        print(f"[TOURNAMENT] All {self.num_bots} bots spawned. Waiting for registration...\n")
        time.sleep(5)  # Give all bots time to register + queue before matchmaker fires

        # Monitor and respawn dead processes
        try:
            while self.running:
                for i, proc in enumerate(self.processes):
                    if proc.poll() is not None:  # Process has exited
                        print(f"\n[TOURNAMENT] Bot {i+1} finished a game, respawning...")
                        self.processes[i] = self.spawn_bot(i + 1)

                time.sleep(2)

        except KeyboardInterrupt:
            print("\n[TOURNAMENT] Stopping all bots...")
            self.stop()

    def stop(self):
        """Kill all bot processes."""
        self.running = False
        for proc in self.processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("[TOURNAMENT] All bots stopped.")
        sys.exit(0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Continuous Micro-Diplomacy Tournament")
    parser.add_argument("--num-bots", type=int, default=4, help="Number of bots to spawn")
    parser.add_argument("--model", default="mistral", help="Ollama model to use")
    parser.add_argument("--prompts-file", default="prompts.yaml", help="YAML file of named prompt variants")
    parser.add_argument(
        "--prompt-names",
        default="default",
        help="Comma-separated prompt variant names to cycle across bots, e.g. 'aggressive,cautious' for a 4-bot A/B test",
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="Referee server URL to play against")
    args = parser.parse_args()

    runner = TournamentRunner(
        num_bots=args.num_bots,
        ollama_model=args.model,
        prompts_file=args.prompts_file,
        prompt_names=[n.strip() for n in args.prompt_names.split(",") if n.strip()],
        base_url=args.base_url,
    )

    def signal_handler(sig, frame):
        runner.stop()

    signal.signal(signal.SIGINT, signal_handler)
    runner.run()
