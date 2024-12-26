import bittensor as bt
import pytest

from commons.utils import set_expire_time
from dojo.protocol import FeedbackRequest, RankingCriteria, TaskTypeEnum

# # Remove the default loguru handler
# logger.remove()

# # Add a new handler to log to stdout
# logger.add(sys.stdout, level="DEBUG")

default_ground_truth = {
    "cid_1": 0,  # 1st place
    "cid_2": 1,  # 2nd place
    "cid_3": 2,  # 3rd place
    "cid_4": 3,  # 4th place
}


@pytest.fixture
def scoring_module():
    # ensure we import them depending on mock_env_var so the ValueError doesn't
    # get raised
    from commons.scoring import Scoring
    from dojo.protocol import (
        CodeAnswer,
        CompletionResponse,
        FeedbackRequest,
        MultiScoreCriteria,
        TaskTypeEnum,
    )

    return (
        Scoring,
        FeedbackRequest,
        CodeAnswer,
        MultiScoreCriteria,
        CompletionResponse,
        TaskTypeEnum,
    )


def mock_response(
    model: str,
    filename: str,
    content: str,
    language: str,
    score: float | None = 0.0,
    cid: str = "",
    rank_id: int = 0,
):
    from dojo.protocol import CodeAnswer, CompletionResponse, FileObject

    return CompletionResponse(
        model=model,
        completion=CodeAnswer(
            files=[FileObject(filename=filename, content=content, language=language)]
        ),
        score=score,
        rank_id=rank_id,
        completion_id=cid,
    )


def mock_request(hotkey: str | None = None, scores: list[float] | None = None):
    from dojo.protocol import MultiScoreCriteria

    axon = bt.TerminalInfo(hotkey=hotkey)
    prompt = "Write a hello world program in python"
    task_type = TaskTypeEnum.CODE_GENERATION
    models = [
        "anthropic/claude-3-haiku-20240307",
        "anthropic/claude-3-opus-20240229",
        "anthropic/claude-3-sonnet-20240229",
        "meta-llama/llama-3-8b-instruct",
    ]

    responses = [
        mock_response(
            model=model,
            score=score,
            filename="hello_world.py",
            content="print('hello, world!')",
            language="python",
        )
        for model, score in zip(
            models, scores if scores is not None else [None] * len(models)
        )
    ]

    # Include the ground truth in the request object if provided
    return FeedbackRequest(
        axon=axon,
        prompt=prompt,
        task_type=task_type,
        criteria_types=[
            MultiScoreCriteria(type="multi-score", options=[], min=0.0, max=100.0)
        ],
        completion_responses=responses,
        expire_at=set_expire_time(8 * 3600),
    )


def mock_scoring_data_normal() -> tuple:
    request = mock_request()
    miner_a = mock_request(hotkey="hotkeyA", scores=[75, 100, 50, 69])
    miner_b = mock_request(hotkey="hotkeyB", scores=[51, 49, 52, 53])
    return request, [miner_a, miner_b]


def mock_scoring_data_all_same_scores() -> tuple:
    request = mock_request()
    miner_a = mock_request(hotkey="hotkeyA", scores=[50, 50, 50, 50])
    miner_b = mock_request(hotkey="hotkeyB", scores=[50, 50, 50, 50])
    return request, [miner_a, miner_b]


@pytest.mark.skip(reason="Placeholder test, not implemented yet")
def test_ground_truth_state_missing():
    pass


"""
TESTS FOR SPEARMAN CORRELATION
"""


def mock_request_spm(
    hotkey: str | None = None,
    rank_ids: list[int] = [],
    cids: list[str] = [],
    ground_truth: dict[str, int] = default_ground_truth,
):
    """
    Dynamically generates miner responses using separate rank_ids and cids.
    """
    from dojo.protocol import FeedbackRequest, TaskTypeEnum

    axon = bt.TerminalInfo(hotkey=hotkey)
    prompt = "Write a hello world program in python"
    task_type = TaskTypeEnum.CODE_GENERATION

    # List of models for testing purposes (you can adjust this as necessary)
    models = [
        "anthropic/claude-3-haiku-20240307",
        "anthropic/claude-3-opus-20240229",
        "anthropic/claude-3-sonnet-20240229",
        "meta-llama/llama-3-8b-instruct",
    ]

    # Ensure both rank_ids and cids have the same length
    assert len(rank_ids) == len(cids), "rank_ids and cids must have the same length."

    # Create responses dynamically using rank_ids and cids
    responses = [
        mock_response(
            model=models[i],
            score=None,
            cid=cid,
            filename=f"{models[i]}_output.py",
            content="print('hello')",
            language="python",
            rank_id=rank_id,
        )
        for i, (cid, rank_id) in enumerate(zip(cids, rank_ids))
    ]

    # Create and return FeedbackRequest with the dynamically generated responses
    return FeedbackRequest(
        axon=axon,
        prompt=prompt,
        task_type=task_type,
        criteria_types=[RankingCriteria(type="rank", options=[])],
        completion_responses=responses,
        ground_truth=ground_truth,
        expire_at=set_expire_time(8 * 3600),
    )


# TODO: repurpose these mock data functions for something else
def mock_scoring_data_for_spm() -> tuple:
    ground_truth = {
        "cid_1": 0,  # 1st place
        "cid_2": 1,  # 2nd place
        "cid_3": 2,  # 3rd place
        "cid_4": 3,  # 4th place
    }

    # Pass separate rank_ids and cids for miner A and miner B
    request = mock_request_spm(
        ground_truth=ground_truth,
        rank_ids=[2, 1, 0, 3],
        cids=["cid_1", "cid_2", "cid_3", "cid_4"],
    )
    miner_a = mock_request_spm(
        hotkey="hotkeyA",
        rank_ids=[2, 1, 0, 3],
        cids=["cid_1", "cid_2", "cid_3", "cid_4"],
    )
    miner_b = mock_request_spm(
        hotkey="hotkeyB",
        rank_ids=[0, 1, 2, 3],
        cids=["cid_1", "cid_2", "cid_3", "cid_4"],
    )

    return request, [miner_a, miner_b]


# TODO: repurpose these mock data functions for something else
def mock_scoring_data_with_known_values() -> tuple:
    """
    This mock data has specific values where we can predict the Spearman correlation.
    """

    ground_truth = {
        "cid1": 0,  # Best-ranked item
        "cid2": 1,
        "cid3": 2,
        "cid4": 3,  # Worst-ranked item
    }

    # Miner A ranks the items perfectly in reverse order of ground truth
    miner_a = mock_request_spm(
        hotkey="hotkeyA",
        rank_ids=[3, 2, 1, 0],  # Reverse of ground truth
        cids=["cid1", "cid2", "cid3", "cid4"],
        ground_truth=ground_truth,
    )

    # Miner B ranks the items in the exact order of the ground truth
    miner_b = mock_request_spm(
        hotkey="hotkeyB",
        rank_ids=[0, 1, 2, 3],  # Perfect match with ground truth
        cids=["cid1", "cid2", "cid3", "cid4"],
        ground_truth=ground_truth,
    )

    request = mock_request_spm(ground_truth=ground_truth)
    return request, [miner_a, miner_b]
