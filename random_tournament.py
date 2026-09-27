#!/usr/bin/env python3
"""
Random Tournament Runner
Selects 4 random personas from prompts.yaml and runs a tournament.
Can run single games or multiple rounds.
"""

import subprocess
import random
import yaml
import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


class RandomTournament:
    def __init__(self, prompts_file: str = "prompts.yaml"):
        self.prompts_file = prompts_file
        self.personas = self._load_personas()
        self.tournament_history = []

    def _load_personas(self) -> List[str]:
        """Load all persona names from prompts.yaml"""
        try:
            with open(self.prompts_file) as f:
                data = yaml.safe_load(f) or {}
            personas = [name for name in data.keys() if isinstance(data[name], dict)]
            return sorted(personas)
        except FileNotFoundError:
            print(f"Error: {self.prompts_file} not found")
            sys.exit(1)

    def select_random_personas(self, count: int = 4) -> List[str]:
        """Randomly select N personas"""
        if count > len(self.personas):
            print(f"Error: Only {len(self.personas)} personas available, need {count}")
            sys.exit(1)
        return random.sample(self.personas, count)

    def run_tournament(self, personas: List[str], model: str = "mistral", base_url: str = "http://localhost:8000") -> bool:
        """Run a single tournament with the given personas"""
        prompt_names = ",".join(personas)

        print(f"\n{'='*80}")
        print(f"🏆 RANDOM TOURNAMENT: {', '.join(personas)}")
        print(f"{'='*80}")
        print(f"Model: {model}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        cmd = [
            "python3",
            "tournament_runner.py",
            "--num-bots", "4",
            "--model", model,
            "--prompt-names", prompt_names,
            "--base-url", base_url,
        ]

        try:
            result = subprocess.run(cmd, timeout=600)
            success = result.returncode == 0

            # Log the tournament
            self.tournament_history.append({
                "timestamp": datetime.now().isoformat(),
                "personas": personas,
                "model": model,
                "success": success,
            })

            return success
        except subprocess.TimeoutExpired:
            print("\n⚠️  Tournament timed out (10 minutes)")
            return False
        except Exception as e:
            print(f"\n❌ Error running tournament: {e}")
            return False

    def run_multiple(self, num_tournaments: int = 5, model: str = "mistral", base_url: str = "http://localhost:8000"):
        """Run multiple random tournaments"""
        print(f"\n{'='*80}")
        print(f"🏆 RUNNING {num_tournaments} RANDOM TOURNAMENTS")
        print(f"{'='*80}")
        print(f"Available personas ({len(self.personas)}): {', '.join(self.personas)}")
        print()

        for i in range(num_tournaments):
            print(f"\n[Tournament {i+1}/{num_tournaments}]")
            personas = self.select_random_personas(4)
            self.run_tournament(personas, model, base_url)

        self.print_summary()

    def print_summary(self):
        """Print tournament history summary"""
        if not self.tournament_history:
            return

        print(f"\n{'='*80}")
        print(f"📊 TOURNAMENT SUMMARY ({len(self.tournament_history)} games)")
        print(f"{'='*80}\n")

        persona_counts = {}
        for entry in self.tournament_history:
            for persona in entry["personas"]:
                persona_counts[persona] = persona_counts.get(persona, 0) + 1

        print("Persona Appearance Frequency:")
        for persona, count in sorted(persona_counts.items(), key=lambda x: x[1], reverse=True):
            pct = (count / len(self.tournament_history)) * 25  # 25% if appearing every game
            bar = "█" * int(pct / 5)
            print(f"  {persona:25} {count:2}x  {bar}")

        print(f"\nSuccessful tournaments: {sum(1 for e in self.tournament_history if e['success'])}/{len(self.tournament_history)}")

    def print_personas(self):
        """Print all available personas"""
        print(f"\n{'='*80}")
        print(f"📋 AVAILABLE PERSONAS ({len(self.personas)})")
        print(f"{'='*80}\n")
        for i, persona in enumerate(self.personas, 1):
            print(f"  {i:2}. {persona}")
        print()

    def show_next_tournament(self):
        """Show what the next random tournament will be without running it"""
        personas = self.select_random_personas(4)
        print(f"\n{'='*80}")
        print(f"🎲 NEXT RANDOM TOURNAMENT (not running)")
        print(f"{'='*80}")
        print(f"\nPersonas selected: {', '.join(personas)}\n")
        return personas


def main():
    parser = argparse.ArgumentParser(description="Random Diplomacy Tournament Runner")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available personas and exit"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview next random tournament without running"
    )
    parser.add_argument(
        "--num",
        type=int,
        default=1,
        help="Number of random tournaments to run (default: 1)"
    )
    parser.add_argument(
        "--model",
        default="mistral",
        help="Ollama model to use (default: mistral)"
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="API server URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--prompts-file",
        default="prompts.yaml",
        help="Path to prompts.yaml (default: prompts.yaml)"
    )

    args = parser.parse_args()

    rt = RandomTournament(args.prompts_file)

    if args.list:
        rt.print_personas()
        return

    if args.preview:
        rt.show_next_tournament()
        return

    # Run tournament(s)
    if args.num == 1:
        personas = rt.select_random_personas(4)
        rt.run_tournament(personas, args.model, args.base_url)
    else:
        rt.run_multiple(args.num, args.model, args.base_url)


if __name__ == "__main__":
    main()
