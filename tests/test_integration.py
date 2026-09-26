import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

# --- System Imports ---
from app.treaties_engine import TreatyAndEspionageEngine, TreatyType, TreatyStatus
from app.trueskill_engine import BayesianMMREngine, TrueSkillProfile, MatchResultSnapshot
from app.gauntlet_runner import GauntletHarness, GauntletVerdict
from app.swarm_agent import WarRoomSwarm
from app.mcts import FastAdjudicator, SimState, Order

# ==============================================================================
# 1. TREATIES ENGINE & ESPIONAGE TESTS
# ==============================================================================

def test_treaties_engine_breach_detection():
    """Verifies that the treaties engine correctly identifies a backstab and applies defensive buffs."""
    engine = TreatyAndEspionageEngine()
    
    # 1. Propose and sign a Non-Aggression Pact
    treaty = engine.propose_treaty("Red", "Blue", TreatyType.NON_AGGRESSION, ["Centerlands"], 1, 5)
    assert treaty.status == TreatyStatus.PENDING
    
    success = engine.sign_treaty(treaty.treaty_id, "Blue")
    assert success is True
    assert treaty.status == TreatyStatus.ACTIVE
    
    # 2. Simulate Turn 3 Orders (Red breaks the treaty by attacking Centerlands)
    orders = {
        "Red": [{"action": "MOVE", "target_destination": "Centerlands", "unit_territory": "Northreach"}],
        "Blue": [{"action": "HOLD", "unit_territory": "Centerlands"}]
    }
    
    breach_events = engine.evaluate_orders_for_breaches(3, orders)
    
    # 3. Verify Consequences
    assert len(breach_events) == 1
    assert breach_events[0]["violator"] == "Red"
    assert breach_events[0]["victim"] == "Blue"
    assert "Red" in engine.perfidious_factions
    assert engine.defensive_buffs["Blue"]["Centerlands"] == 1
    assert treaty.status == TreatyStatus.BREACHED

# ==============================================================================
# 2. TRUESKILL BAYESIAN MMR TESTS
# ==============================================================================

def test_trueskill_bayesian_updates():
    """Verifies that Gaussian MMR updates correctly scale based on Diplomacy-Bench metrics."""
    engine = BayesianMMREngine()
    
    # Setup fresh profiles (mu=25.0, sigma=8.333)
    registry = {
        "Red": TrueSkillProfile(agent_id="Red"),
        "Blue": TrueSkillProfile(agent_id="Blue")
    }
    
    # Simulate Red executing a highly profitable betrayal to win the match
    snapshots = [
        MatchResultSnapshot("Red", placement_rank=1, final_sc=6, persuasion_index=0.8, betrayal_efficiency=2.5, deception_resilience=0.9),
        MatchResultSnapshot("Blue", placement_rank=2, final_sc=3, persuasion_index=0.4, betrayal_efficiency=0.5, deception_resilience=0.2)
    ]
    
    reports = engine.update_match_ratings(snapshots, registry)
    
    # Verify Red's MMR skyrocketed due to the 2.5x Betrayal Efficiency multiplier
    assert reports[0]["agent_id"] == "Red"
    assert reports[0]["new_mmr"] > 0
    assert registry["Red"].mu > 25.0         # Skill increased
    assert registry["Red"].sigma < 8.333     # Uncertainty dropped
    assert registry["Blue"].mu < 25.0        # Skill dropped for losing

# ==============================================================================
# 3. GAUNTLET HARNESS TESTS
# ==============================================================================

def test_gauntlet_qualification_suite():
    """Verifies the automated baseline test filters out broken code and sets an initial MMR."""
    harness = GauntletHarness()
    
    # Mock a basic candidate policy that just holds its ground
    def valid_policy(turn, map_units):
        return [Order(unit_territory=k, action="HOLD") for k, v in map_units.items() if v == "Red"]
        
    verdict = harness.run_calibration_suite("CandidateBot_v1", valid_policy)
    
    assert verdict.passed is True
    assert verdict.syntax_errors == 0
    assert verdict.matches_completed == 4
    assert verdict.final_mmr >= 0
    assert verdict.qualifying_tier in ["IRON", "BRONZE", "SILVER", "GOLD"]

# ==============================================================================
# 4. WAR ROOM SWARM MOCK DEBATE (ASYNC)
# ==============================================================================

@pytest.mark.asyncio
async def test_war_room_swarm_consensus(mocker):
    """Verifies the Swarm Agent queries its sub-agents concurrently and outputs a valid JSON decision."""
    swarm = WarRoomSwarm()
    swarm.my_faction = "Red"
    swarm.game_id = "test_123"
    
    # Mock the API clients
    swarm.arena = MagicMock()
    swarm.arena.post = AsyncMock()
    
    mock_llm_response = MagicMock()
    mock_llm_response.choices = [MagicMock()]
    
    # We want the final Commander response to be valid JSON
    mock_llm_response.choices[0].message.content = json.dumps({
        "reasoning_consensus": "The Spy is right. Blue is lying. We must strike.",
        "orders": [{"unit_territory": "Northreach", "action": "MOVE", "target_destination": "Centerlands"}]
    })
    
    swarm.llm.chat.completions.create = AsyncMock(return_value=mock_llm_response)
    
    dummy_state = {"turn": 4, "phase": "ORDERS", "map": {}, "scores": {}}
    
    # Execute the debate cycle
    await swarm.execute_debate_cycle(dummy_state)
    
    # Verify the Commander successfully posted the orders to the arena server
    swarm.arena.post.assert_called_once()
    call_args = swarm.arena.post.call_args[0][0]
    assert "orders" in call_args

# ==============================================================================
# 5. MASTER E2E INTEGRATION: THE FULL PIPELINE
# ==============================================================================

@pytest.mark.asyncio
async def test_master_e2e_betrayal_pipeline(mocker):
    """
    MASTER INTEGRATION TEST:
    1. Swarm hallucinates a betrayal order.
    2. Treaties Engine detects the breach of a NAP and gives the victim a buff.
    3. Mcripts Adjudicator resolves the combat (taking the buff into account).
    4. TrueSkill Engine updates the post-match ratings.
    """
    
    # --- A. Initialization ---
    treaty_engine = TreatyAndEspionageEngine()
    mmr_engine = BayesianMMREngine()
    swarm = WarRoomSwarm()
    swarm.my_faction = "Red"
    
    # --- B. Establish Treaties ---
    # Red and Blue sign a Non-Aggression Pact on Centerlands
    treaty = treaty_engine.propose_treaty("Red", "Blue", TreatyType.NON_AGGRESSION, ["Centerlands"], 1, 5)
    treaty_engine.sign_treaty(treaty.treaty_id, "Blue")
    
    # --- C. Swarm Submits Betrayal ---
    # Red attacks Centerlands *with support* from Ironpeaks (strength 2) -
    # without the treaty buff this beats Blue's unsupported HOLD (strength
    # 1) outright, so the test can actually prove the buff changes the
    # outcome rather than relying on a 1v1 tie that the defender would win
    # either way (ties always favor the defender in this engine).
    swarm.llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "reasoning_consensus": "I am ignoring the treaty.",
        "orders": [
            {"unit_territory": "Northreach", "action": "MOVE", "target_destination": "Centerlands"},
            {"unit_territory": "Ironpeaks", "action": "SUPPORT", "target_source": "Northreach", "target_destination": "Centerlands"},
        ]
    })
    swarm.llm.chat.completions.create = AsyncMock(return_value=mock_resp)

    # Override arena.post to capture the generated orders
    captured_orders = []
    async def mock_post(url, json, **kwargs):
        captured_orders.extend(json["orders"])
    swarm.arena = MagicMock()
    swarm.arena.post = AsyncMock(side_effect=mock_post)

    await swarm.execute_debate_cycle({"turn": 2, "phase": "ORDERS", "map": {}, "scores": {}})

    # Formulate joint orders based on the Swarm's output
    joint_orders = {
        "Red": captured_orders,
        "Blue": [{"unit_territory": "Centerlands", "action": "HOLD"}], # Blue trusts the treaty
        "Green": [], "Yellow": []
    }

    # --- D. Treaty Audit & Combat Adjudication ---
    breaches = treaty_engine.evaluate_orders_for_breaches(2, joint_orders)

    assert len(breaches) == 1
    assert "Red" in treaty_engine.perfidious_factions
    assert treaty_engine.defensive_buffs["Blue"]["Centerlands"] == 1  # Blue gets the defense buff!

    state = SimState(
        turn=2,
        map_units={"Northreach": "Red", "Ironpeaks": "Red", "Centerlands": "Blue"},
        map_sc={"Northreach": "Red", "Ironpeaks": "Red", "Centerlands": "Blue"}
    )

    # Convert dicts to Order dataclasses for the adjudicator
    parsed_orders = {
        "Red": tuple(Order(**o) for o in joint_orders["Red"]),
        "Blue": tuple(Order(**o) for o in joint_orders["Blue"])
    }

    # Without the buff, Red's supported attack (strength 2) should actually
    # conquer Centerlands - confirms the scenario is a real test of the
    # buff, not a tie the defender would've won regardless.
    unbuffed_state = FastAdjudicator.step(state, parsed_orders)
    assert unbuffed_state.map_units["Centerlands"] == "Red"

    # With the real buff computed by the treaty engine above, Blue's
    # defense (1 + 1 buff = 2) now matches Red's attack (2) - a tie, which
    # this engine's rules give to the defender. Blue survives the backstab.
    next_state = FastAdjudicator.step(state, parsed_orders, defensive_buffs=treaty_engine.defensive_buffs)
    assert next_state.map_units["Centerlands"] == "Blue"
    
    # --- E. End of Match TrueSkill Update ---
    registry = {"Red": TrueSkillProfile("Red"), "Blue": TrueSkillProfile("Blue")}
    snapshots = [
        # Blue survived and won 1st place because their deception resilience (DRS) was high
        MatchResultSnapshot("Blue", 1, 4, 0.5, 1.0, deception_resilience=1.0),
        # Red placed 2nd. They attempted a betrayal but failed (low Betrayal Efficiency)
        MatchResultSnapshot("Red", 2, 2, 0.5, betrayal_efficiency=0.2, deception_resilience=0.0)
    ]
    
    reports = mmr_engine.update_match_ratings(snapshots, registry)
    
    # Validate final integration logic
    assert reports[0]["agent_id"] == "Blue"
    assert registry["Blue"].mu > registry["Red"].mu
