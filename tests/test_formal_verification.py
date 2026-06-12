"""
Tests for security/formal_verification.py — DFA model of TRIsecure V2 auth pipeline.
Verifies all 6 formal security properties hold.
"""

import json
import pytest

from security.formal_verification import (
    AUTH_DFA,
    AuthDFA,
    AuthInput,
    AuthState,
    PropertyResult,
    _SUCCESS_PATH,
    _SUCCESS_INPUTS,
    _TRANSITIONS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dfa() -> AuthDFA:
    return AuthDFA()


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------

class TestDFAStructure:
    def test_all_states_present(self, dfa):
        assert dfa.states == frozenset(AuthState)

    def test_all_inputs_present(self, dfa):
        assert dfa.alphabet == frozenset(AuthInput)

    def test_initial_state_is_idle(self, dfa):
        assert dfa.initial == AuthState.IDLE

    def test_accepting_state_is_session_issued(self, dfa):
        assert AuthState.SESSION_ISSUED in dfa.accepting
        assert len(dfa.accepting) == 1

    def test_transition_count(self, dfa):
        # 16 defined transitions (see _TRANSITIONS)
        assert len(dfa.transitions) == len(_TRANSITIONS)

    def test_step_returns_none_for_undefined(self, dfa):
        assert dfa.step(AuthState.IDLE, AuthInput.FACE_MATCH) is None


# ---------------------------------------------------------------------------
# Property 1: Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_determinism_holds(self, dfa):
        result = dfa.verify_determinism()
        assert result.holds, result.proof

    def test_no_duplicate_keys_in_transition_table(self):
        keys = list(_TRANSITIONS.keys())
        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Property 2: Completeness
# ---------------------------------------------------------------------------

class TestCompleteness:
    def test_completeness_holds(self, dfa):
        result = dfa.verify_completeness()
        assert result.holds, result.proof

    def test_all_expected_inputs_have_transitions(self, dfa):
        from security.formal_verification import _STATE_ALPHABET
        for state, expected_inputs in _STATE_ALPHABET.items():
            for inp in expected_inputs:
                assert dfa.step(state, inp) is not None, (
                    f"Missing δ({state.name}, {inp.name})"
                )


# ---------------------------------------------------------------------------
# Property 3: Safety
# ---------------------------------------------------------------------------

class TestSafety:
    def test_safety_holds(self, dfa):
        result = dfa.verify_safety()
        assert result.holds, result.proof

    def test_exactly_one_accepting_path(self, dfa):
        paths = dfa._all_paths_to(AuthState.SESSION_ISSUED)
        assert len(paths) == 1

    def test_accepting_path_matches_success_path(self, dfa):
        paths = dfa._all_paths_to(AuthState.SESSION_ISSUED)
        assert paths[0] == list(_SUCCESS_PATH)

    def test_success_path_has_eight_stages(self):
        # IDLE + 7 intermediate stages + SESSION_ISSUED = 9 states, 8 inputs
        assert len(_SUCCESS_PATH) == 9
        assert len(_SUCCESS_INPUTS) == 8

    def test_success_trace_reaches_session_issued(self, dfa):
        final, visited = dfa.run(list(_SUCCESS_INPUTS))
        assert final == AuthState.SESSION_ISSUED
        assert visited == list(_SUCCESS_PATH)

    @pytest.mark.parametrize("fail_input,fail_at", [
        (AuthInput.RATE_BLOCKED,    AuthState.RATE_CHECK),
        (AuthInput.NFC_INVALID,     AuthState.NFC_VERIFY),
        (AuthInput.VOTER_NOT_FOUND, AuthState.VOTER_LOOKUP),
        (AuthInput.NOT_ELIGIBLE,    AuthState.ELIGIBILITY_CHECK),
        (AuthInput.FACE_MISMATCH,   AuthState.FACE_VERIFY),
        (AuthInput.FUSION_REJECT,   AuthState.FUSION_CHECK),
        (AuthInput.PAD_ATTACK,      AuthState.PAD_CHECK),
    ])
    def test_failure_at_each_stage_leads_to_rejected(self, dfa, fail_input, fail_at):
        # To reach state at index i, feed _SUCCESS_INPUTS[:i] first, then the fail input.
        # e.g. RATE_CHECK is index 1 → feed ATTEMPT (inputs[:1]) then RATE_BLOCKED.
        stage_index = list(_SUCCESS_PATH).index(fail_at)
        partial_inputs = list(_SUCCESS_INPUTS[:stage_index]) + [fail_input]
        final, _ = dfa.run(partial_inputs)
        assert final == AuthState.REJECTED, (
            f"Expected REJECTED when failing at {fail_at.name} with {fail_input.name}"
        )


# ---------------------------------------------------------------------------
# Property 4: Liveness
# ---------------------------------------------------------------------------

class TestLiveness:
    def test_liveness_holds(self, dfa):
        result = dfa.verify_liveness()
        assert result.holds, result.proof

    def test_no_non_resetting_cycles(self, dfa):
        from collections import defaultdict
        adj = defaultdict(set)
        for (s, inp), t in dfa.transitions.items():
            if inp != AuthInput.RESET:
                adj[s].add(t)
        cycles = dfa._find_cycles(adj)
        non_trivial = [c for c in cycles if len(c) > 1 or (len(c) == 1 and c[0] != AuthState.REJECTED)]
        assert non_trivial == []

    def test_reset_returns_to_idle_from_session_issued(self, dfa):
        assert dfa.step(AuthState.SESSION_ISSUED, AuthInput.RESET) == AuthState.IDLE

    def test_reset_returns_to_idle_from_rejected(self, dfa):
        assert dfa.step(AuthState.REJECTED, AuthInput.RESET) == AuthState.IDLE

    def test_full_round_trip(self, dfa):
        inputs = list(_SUCCESS_INPUTS) + [AuthInput.RESET]
        final, _ = dfa.run(inputs)
        assert final == AuthState.IDLE


# ---------------------------------------------------------------------------
# Property 5: Double-vote prevention
# ---------------------------------------------------------------------------

class TestDoubleVotePrevention:
    def test_property_holds(self, dfa):
        result = dfa.verify_double_vote_prevention()
        assert result.holds, result.proof

    def test_not_eligible_leads_to_rejected(self, dfa):
        assert dfa.step(AuthState.ELIGIBILITY_CHECK, AuthInput.NOT_ELIGIBLE) == AuthState.REJECTED

    def test_eligible_leads_to_face_verify(self, dfa):
        assert dfa.step(AuthState.ELIGIBILITY_CHECK, AuthInput.ELIGIBLE) == AuthState.FACE_VERIFY

    def test_already_voted_voter_cannot_reach_session(self, dfa):
        inputs = [
            AuthInput.ATTEMPT,
            AuthInput.RATE_OK,
            AuthInput.NFC_VALID,
            AuthInput.VOTER_FOUND,
            AuthInput.NOT_ELIGIBLE,   # already voted
        ]
        final, _ = dfa.run(inputs)
        assert final == AuthState.REJECTED

    def test_rejected_voter_cannot_get_session_by_skipping(self, dfa):
        # Even if attacker somehow jumps to PAD_CHECK directly,
        # they must have passed ELIGIBILITY_CHECK → this tests the DFA
        # doesn't allow PAD_CHECK to be reached without ELIGIBLE input.
        paths = dfa._all_paths_to(AuthState.PAD_CHECK)
        for path in paths:
            assert AuthState.ELIGIBILITY_CHECK in path


# ---------------------------------------------------------------------------
# Property 6: Rate-limit enforcement
# ---------------------------------------------------------------------------

class TestRateLimit:
    def test_property_holds(self, dfa):
        result = dfa.verify_rate_limit()
        assert result.holds, result.proof

    def test_attempt_leads_to_rate_check(self, dfa):
        assert dfa.step(AuthState.IDLE, AuthInput.ATTEMPT) == AuthState.RATE_CHECK

    def test_rate_blocked_leads_to_rejected(self, dfa):
        assert dfa.step(AuthState.RATE_CHECK, AuthInput.RATE_BLOCKED) == AuthState.REJECTED

    def test_blocked_attacker_never_reaches_nfc_stage(self, dfa):
        inputs = [AuthInput.ATTEMPT, AuthInput.RATE_BLOCKED]
        final, visited = dfa.run(inputs)
        assert final == AuthState.REJECTED
        assert AuthState.NFC_VERIFY not in visited
        assert AuthState.VOTER_LOOKUP not in visited


# ---------------------------------------------------------------------------
# Full verification run
# ---------------------------------------------------------------------------

class TestVerifyAll:
    def test_all_six_properties_hold(self, dfa):
        results = dfa.verify_all()
        assert len(results) == 6
        failures = [r for r in results if not r.holds]
        assert failures == [], "\n".join(f"{r.name}: {r.proof}" for r in failures)

    def test_proof_report_is_valid_json(self, dfa):
        report_str = dfa.proof_report()
        report = json.loads(report_str)
        assert report["all_properties_hold"] is True
        assert len(report["properties"]) == 6

    def test_module_singleton_passes_verification(self):
        results = AUTH_DFA.verify_all()
        assert all(r.holds for r in results)


# ---------------------------------------------------------------------------
# Trace / simulation tests
# ---------------------------------------------------------------------------

class TestTraceSimulation:
    def test_empty_trace_stays_idle(self, dfa):
        final, visited = dfa.run([])
        assert final == AuthState.IDLE
        assert visited == [AuthState.IDLE]

    def test_partial_trace_stops_at_last_valid_state(self, dfa):
        final, _ = dfa.run([AuthInput.ATTEMPT, AuthInput.RATE_OK])
        assert final == AuthState.NFC_VERIFY

    def test_undefined_transition_halts_trace(self, dfa):
        # FACE_MATCH from IDLE is undefined — trace should stop at IDLE
        final, visited = dfa.run([AuthInput.FACE_MATCH])
        assert final == AuthState.IDLE
        assert len(visited) == 1
