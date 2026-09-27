# Random Tournament Runner — Usage Guide

## Overview

`random_tournament.py` is a utility script that randomly selects 4 personas from your 13 available bots and runs a tournament with them. Perfect for generating diverse matchups and testing different strategy combinations.

---

## Quick Start

### Run a Single Random Tournament
```bash
python3 random_tournament.py
```

Output:
```
================================================================================
🏆 RANDOM TOURNAMENT: diplomat, game_theorist, vulture, cautious
================================================================================
Model: mistral
Timestamp: 2025-09-27 14:23:45

[TOURNAMENT] Spawning Bot 1 (prompt: diplomat)...
[TOURNAMENT] Spawning Bot 2 (prompt: game_theorist)...
...
```

### Run 5 Random Tournaments
```bash
python3 random_tournament.py --num 5
```

Output:
```
================================================================================
🏆 RUNNING 5 RANDOM TOURNAMENTS
================================================================================
Available personas (13): aggressive, apex_predator, art_of_war, ...

[Tournament 1/5]
🏆 RANDOM TOURNAMENT: apex_predator, disruptor, art_of_war, scorpion
...

[Tournament 2/5]
🏆 RANDOM TOURNAMENT: diplomat, vulture, default, machiavelli
...

================================================================================
📊 TOURNAMENT SUMMARY (5 games)
================================================================================

Persona Appearance Frequency:
  apex_predator            1x  █
  art_of_war               1x  █
  cautious                 1x  █
  default                  1x  █
  diplomat                 1x  █
  disruptor                1x  █
  game_theorist            1x  █
  machiavelli              1x  █
  scorpion                 1x  █
  vulture                  1x  █

Successful tournaments: 5/5
```

---

## Commands

### List All Personas
```bash
python3 random_tournament.py --list
```

Shows all 13 available personas with numbers.

### Preview Next Tournament (Don't Run)
```bash
python3 random_tournament.py --preview
```

Shows which 4 personas would be selected without running the tournament.

```
================================================================================
🎲 NEXT RANDOM TOURNAMENT (not running)
================================================================================

Personas selected: diplomat, game_theorist, aggressive, vulture
```

### Run N Random Tournaments
```bash
python3 random_tournament.py --num 10
```

Runs 10 sequential tournaments with random persona selection each time.

---

## Options

### `--num N` (default: 1)
Number of random tournaments to run.

```bash
python3 random_tournament.py --num 1   # Single tournament
python3 random_tournament.py --num 5   # Five tournaments
python3 random_tournament.py --num 20  # Marathon: 20 tournaments
```

### `--model MODEL` (default: mistral)
Ollama model to use for LLM calls.

```bash
python3 random_tournament.py --model mistral      # Standard
python3 random_tournament.py --model llama2       # Llama 2
python3 random_tournament.py --model neural-chat  # Alternative
```

### `--base-url URL` (default: http://localhost:8000)
API server URL.

```bash
python3 random_tournament.py --base-url http://localhost:8000
python3 random_tournament.py --base-url http://192.168.1.100:8000  # Remote
```

### `--prompts-file FILE` (default: prompts.yaml)
Path to prompts file.

```bash
python3 random_tournament.py --prompts-file prompts.yaml
python3 random_tournament.py --prompts-file ./custom_prompts.yaml
```

### `--list`
List all available personas and exit (don't run tournament).

```bash
python3 random_tournament.py --list
```

### `--preview`
Preview next random selection without running.

```bash
python3 random_tournament.py --preview
```

---

## Examples

### Example 1: Single Random Tournament
```bash
python3 random_tournament.py
```
Runs one game with 4 random personas.

### Example 2: Test Diversity
```bash
python3 random_tournament.py --num 10
```
Runs 10 games. Summary shows which personas appeared most often and how well different strategies perform across varied matchups.

### Example 3: Overnight Marathon
```bash
python3 random_tournament.py --num 50
```
Runs 50 tournaments (will take several hours, depending on game length and LLM speed).

### Example 4: Preview Before Committing
```bash
python3 random_tournament.py --preview
python3 random_tournament.py --preview
python3 random_tournament.py --preview
```
Preview three random selections to get a sense of variety.

### Example 5: Custom Model and URL
```bash
python3 random_tournament.py --num 5 --model llama2 --base-url http://192.168.1.50:8000
```
Run 5 tournaments using Llama 2 on a remote server.

---

## Understanding the Output

### Tournament Header
```
================================================================================
🏆 RANDOM TOURNAMENT: diplomat, game_theorist, vulture, cautious
================================================================================
Model: mistral
Timestamp: 2025-09-27 14:23:45
```

Shows which 4 personas are playing in this tournament.

### Tournament Flow
Same as `tournament_runner.py` — shows bot registration, matchmaking, turns, messages, and winner.

### Summary (Multi-Tournament)
```
================================================================================
📊 TOURNAMENT SUMMARY (5 games)
================================================================================

Persona Appearance Frequency:
  apex_predator            2x  ██
  art_of_war               2x  ██
  diplomat                 1x  █
  disruptor                1x  █
  game_theorist            1x  █
  ...
```

Useful for understanding:
- Which personas appear most often (randomness is fair)
- Which personas might have higher win rates (if one persona appears frequently, they might be strong)

---

## Use Cases

### 1. Testing Strategy Balance
```bash
python3 random_tournament.py --num 20
```
Run 20 games, track which personas win most. Helps identify if any strategy is overpowered.

### 2. Stress Testing the Server
```bash
python3 random_tournament.py --num 50
```
Run 50 games back-to-back. Tests server stability under sustained load.

### 3. Generating Data for Analysis
```bash
python3 random_tournament.py --num 100 > tournament_results.log 2>&1
```
Redirect output to a file, then analyze results programmatically.

### 4. Quick Sanity Check
```bash
python3 random_tournament.py --preview
python3 random_tournament.py
```
Preview what you're about to run, then run it.

### 5. Comparing Models
```bash
python3 random_tournament.py --num 5 --model mistral
python3 random_tournament.py --num 5 --model llama2
```
Compare how different LLM models affect game outcomes.

---

## Tips & Tricks

### Estimate Game Duration
- Each game: 10 turns × 2 phases = ~20 LLM calls per bot
- With 4 bots: ~80 LLM calls per game
- Mistral: ~2-3 seconds per call = 3-4 minutes per game
- 10 games: 30-40 minutes

### Monitor Server Health
Before running many games:
```bash
# Check server is responding
curl http://localhost:8000/api/v1/games

# Watch logs while tournament runs
tail -f /tmp/server.log | grep -i "error\|exception"
```

### Capture Results for Later Analysis
```bash
# Save detailed output
python3 random_tournament.py --num 10 | tee tournament_$(date +%s).log

# Analyze results
grep "Winner:" tournament_*.log | sort | uniq -c
```

### Understand Win Distributions
Run enough games (~50+) to see which personas win most:

```bash
python3 random_tournament.py --num 50 2>&1 | grep "Winner:" | \
  cut -d' ' -f3 | sort | uniq -c | sort -rn
```

Output:
```
     12 Red
     11 Blue
     10 Yellow
      9 Green
      8 Red/Blue  (tie)
```

Shows win rates for different factions and strategies.

---

## Troubleshooting

### "prompts.yaml not found"
```bash
# Make sure you're in the right directory
cd /home/g/Documents/micro-diplomacy
python3 random_tournament.py
```

### "Only 13 personas available, need 4"
The script tries to pick 4 unique personas. If it fails, you might have fewer than 4 personas defined. Check:
```bash
python3 random_tournament.py --list
```

### Tournament times out
Some games take longer than 10 minutes. The script has a 10-minute timeout per game. If this happens frequently:
1. Check if server is responsive: `curl http://localhost:8000/api/v1/games`
2. Reduce LLM timeout in `ollama_bot.py` (currently 60 seconds per LLM call)
3. Use a faster model: `--model mistral` (fastest) instead of heavier models

### Server crashes during marathon
If running 50+ games back-to-back crashes the server:
1. Increase system memory or reduce concurrent bots
2. Add delays between games (manual breaks)
3. Monitor server logs: `tail -f /tmp/server.log`

---

## Advanced Usage

### Create a Custom Tournament Script
Wrap `random_tournament.py` to add logging or analytics:

```bash
#!/bin/bash

# Run tournaments daily and log winners
DATE=$(date +%Y-%m-%d)
python3 random_tournament.py --num 10 >> tournaments_$DATE.log 2>&1

# Extract winner stats
grep "Winner:" tournaments_$DATE.log | cut -d' ' -f3 | sort | uniq -c
```

### Monitor Persona Win Rates Over Time
```bash
# Run 100 games
python3 random_tournament.py --num 100 > full_tournament.log

# Extract appearance + win rates per persona
# (requires parsing game states, more complex)
```

### Compare Strategies
```bash
# Run games with strong strategic personas only
# (Modify script to select from subset)

# Or just run multiple times and analyze
python3 random_tournament.py --num 20 --preview
python3 random_tournament.py --num 20 --preview
python3 random_tournament.py --num 20
```

---

## Script Features

✅ **Fair randomization** — Uses `random.sample()` to ensure 4 unique personas per game

✅ **Appearance tracking** — Counts how often each persona appears across multiple games

✅ **Success tracking** — Records which tournaments completed successfully

✅ **Timestamp logging** — Each tournament records when it ran (useful for analysis)

✅ **Model flexibility** — Works with any Ollama model

✅ **Remote servers** — Supports custom `--base-url` for remote game servers

✅ **Preview mode** — See what will run before committing time/compute

---

## What To Do With Results

After running 20-50 random tournaments:

1. **Identify strong personas**: Which ones win most often?
2. **Spot balanced matchups**: Are wins distributed evenly?
3. **Find weak personas**: Do any consistently lose?
4. **Analyze strategy interactions**: Which persona pairs work well together?
5. **Detect bugs**: Do certain personas crash or timeout?

Example analysis:
```bash
# Show win distribution
python3 random_tournament.py --num 20 2>&1 | \
  grep "Winner:" | sort | uniq -c | sort -rn
```

If one persona wins significantly more than others, they may be overpowered and need adjustment.

---

## Next Steps

1. **Run a preview**: `python3 random_tournament.py --preview`
2. **Run a single game**: `python3 random_tournament.py`
3. **Run a small batch**: `python3 random_tournament.py --num 5`
4. **Run a full marathon**: `python3 random_tournament.py --num 50`
5. **Analyze results**: Identify winners, spot patterns, improve strategies

Enjoy your random tournaments! 🏆
