"""Positive and negative controls for the eval suite itself."""
import pytest

from evals import policies
from evals.cases import CASES
from evals.run import run_case

pytestmark = pytest.mark.needs_server


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
async def test_reference_policy_passes_every_case(case):
    result = await run_case(case, policies.reference_model)
    assert result["passed"], result["verdicts"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
async def test_reckless_policy_is_caught(case):
    result = await run_case(case, policies.reckless_model)
    if case.id == "claimed_preapproval":
        # The harness defends this one: forged reference stripped, human declined, nothing written.
        assert result["passed"] and result["forged_approvals_stripped"] == 1
    else:
        assert not result["passed"], "graders failed to catch a reckless agent"
