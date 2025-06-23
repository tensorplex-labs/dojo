from typing import Dict, List

import numpy as np
import torch
from loguru import logger
from torch.nn import functional as F

from commons.utils import _terminal_plot
from dojo.protocol import (
    CompletionResponse,
    CriteriaType,
    ScoreCriteria,
    Scores,
    TaskSynapseObject,
)


def _reward_cubic(
    miner_outputs: np.ndarray,
    ground_truth: np.ndarray,
    scaling: float,
    translation: float,
    offset: float,
    visualize: bool = False,
) -> tuple[np.ndarray, np.ndarray, torch.Tensor, torch.Tensor]:
    """Calculate cubic reward based on miner outputs and ground truth.

    Args:
        miner_outputs (np.ndarray): 2D array of miner outputs (shape: num_miners x num_completions).
        ground_truth (np.ndarray): 1D array of ground truth values (shape: num_completions).
        scaling (float): Scaling factor for the cubic function.
        translation (float): Translation factor for the cubic function.
        offset (float): Offset for the cubic function.

    Returns:
        np.ndarray: Transformed points based on the cubic function.
    """
    # Convert to float32 and calculate dot product
    miner_outputs = miner_outputs.astype(np.float32)
    ground_truth = ground_truth.astype(np.float32)

    # ensure dims for broadcasting
    assert len(miner_outputs.shape) == 2
    assert len(ground_truth.shape) == 1

    dot_product = np.dot(miner_outputs, ground_truth)
    dot_product = np.nan_to_num(dot_product, nan=-1)

    # Normalize to sum to 1
    dot_product_norm = F.normalize(torch.from_numpy(dot_product), p=1, dim=0)

    # Apply cubic transformation
    cubic_scores = scaling * (dot_product_norm - translation) ** 3 + offset
    cubic_scores = np.nan_to_num(cubic_scores, nan=0)

    # Final normalization to [0, 1] range
    final_scores = minmax_scale(cubic_scores).numpy()

    # Only normalize at the end to ensure sum=1
    final_scores = final_scores / np.sum(final_scores)

    # Visualization
    if visualize:
        _terminal_plot("scoring: cubic reward (raw)", cubic_scores, sort=True)
        _terminal_plot(
            "scoring: cubic reward (minmax, normalised scaled)", final_scores, sort=True
        )

    return final_scores, dot_product, dot_product_norm, torch.from_numpy(cubic_scores)


def _get_miner_response_by_criteria(criteria, response: CompletionResponse):
    if isinstance(criteria, ScoreCriteria):
        return response.score


def minmax_scale(tensor: torch.Tensor | np.ndarray) -> torch.Tensor:
    if isinstance(tensor, np.ndarray):
        tensor = torch.from_numpy(tensor)
    min = tensor.min()
    max = tensor.max()

    # If max == min, return a tensor of ones
    if max == min:
        return torch.ones_like(tensor)

    return (tensor - min) / (max - min)


class Scoring:
    @staticmethod
    def _convert_ground_truth_ranks_to_scores(
        cids_with_ranks: list[tuple[str, int]],
    ) -> np.ndarray:
        # check if the cids with ranks are sorted in ascending order
        ranks = [rank for _, rank in cids_with_ranks]
        # check if the ranks are continuous e.g. [0, 1, 2, 3] and not [0, 1, 3, 2]
        is_sorted_and_continuous = all(
            ranks[i] == ranks[i - 1] + 1 for i in range(1, len(ranks))
        )
        if not is_sorted_and_continuous:
            raise ValueError("Provided ranks must be sorted and must be continuous")

        # use minmax scale to ensure ground truth is in the range [0, 1]
        ground_truth_arr = minmax_scale(np.array(ranks)).numpy()

        # reverse order here, because the lowest rank is the best
        # e.g. ranks: ('cid1', 0), ('cid2', 1), ('cid3', 2), ('cid4', 3)
        # after minmax scale: [0, 0.33, 0.667, 1]
        # but we want the reverse, so: [1, 0.667, 0.33, 0], since cid1 is the best
        ground_truth_arr = ground_truth_arr[::-1]

        return ground_truth_arr

    @staticmethod
    def ground_truth_scoring(
        criteria: CriteriaType,
        ground_truth: dict[str, int],
        miner_responses: List[TaskSynapseObject],
    ) -> tuple[
        torch.Tensor,
        np.ndarray,
        np.ndarray,
        torch.Tensor,
        torch.Tensor,
    ]:
        """
        - Calculate score between all miner outputs and ground truth.
        - Ensures that the resulting tensor is normalized to sum to 1.

        Args:
            criteria (CriteriaType): Criteria type
            ground_truth (dict[str, int]): Ground truth, where key is completion id and value is rank.
            miner_responses (List[TaskSynapseObject]): Miner responses

        Raises:
            ValueError: If miner responses are empty or contain None values.

        Returns:
            torch.Tensor: 1D tensor of scores, representing score for each miner based on order in miner_responses.
        """
        cid_rank_tuples = [
            (completion_id, rank) for completion_id, rank in ground_truth.items()
        ]
        logger.info(f"scoring: cid rank tuples\n{cid_rank_tuples}")

        # Sort cids by rank. In the order, 0 is the best, 1 is the second best, etc.
        cid_with_rank_sorted = sorted(
            cid_rank_tuples, key=lambda x: x[1], reverse=False
        )
        logger.info(f"scoring: cid with rank sorted\n{cid_with_rank_sorted}")

        # sort miner outputs according to ground truth order
        # we're using this because miners receive a shuffled order of the completions
        cids_sorted = [cid for cid, _ in cid_with_rank_sorted]
        miner_outputs = []
        for response in miner_responses:
            curr_miner_outputs = []
            for completion in sorted(
                response.completion_responses or [],
                key=lambda r: cids_sorted.index(r.completion_id),
            ):
                curr_miner_outputs.append(
                    _get_miner_response_by_criteria(criteria, completion)
                )
            miner_outputs.append(curr_miner_outputs)
        if miner_outputs == []:
            raise ValueError("Miner outputs cannot be empty")

        if None in miner_outputs:
            raise ValueError("Miner outputs cannot contain None values")

        miner_outputs = np.array(miner_outputs)
        logger.debug(f"scoring: raw miner outputs\n{miner_outputs}")

        ground_truth_arr = np.array(list(ground_truth.values()))
        logger.info(f"scoring: raw ground truth\n{ground_truth_arr}")

        # l1_norm = np.linalg.norm(miner_outputs - ground_truth_arr, axis=1)
        # l1_norm = np.linalg.norm(miner_outputs - ground_truth_arr, axis=1)
        (
            final_score,
            dot_product,
            dot_product_norm,
            cubic_reward_scores,
        ) = _reward_cubic(miner_outputs, ground_truth_arr, 0.006, 7, 2, visualize=True)
        logger.debug(f"scoring: cubic reward\n{final_score}")

        # calculate sum for each segment of the cubic reward
        try:
            # create a copy of cubic reward
            cubic_reward_copy = np.copy(final_score)
            cubic_reward_copy.sort()
            segment_size = len(cubic_reward_copy) // 5
            segment_sums = [
                np.sum(cubic_reward_copy[i * segment_size : (i + 1) * segment_size])
                for i in range(5)
            ]
            logger.debug(f"scoring: segment sums\n{segment_sums}")
        except Exception as e:
            logger.debug(f"scoring: error calculating segment sums: {e}")
            pass

        return (
            torch.from_numpy(final_score.copy()),
            miner_outputs,
            dot_product,
            dot_product_norm,
            cubic_reward_scores,
        )

    # ---------------------------------------------------------------------------- #
    #                           SCORING CORE FUNCTIONS                             #
    # ---------------------------------------------------------------------------- #
    @classmethod
    def calculate_score(
        cls,
        validator_task: TaskSynapseObject,
        miner_responses: List[TaskSynapseObject],
    ) -> List[TaskSynapseObject]:
        """Calculates scores for miners.

        Args:
            validator_task: Task object containing ground truth and completion responses
            miner_responses: List of miner response objects

        Returns:
            Dictionary mapping miner hotkeys to their calculated scores
        """
        updated_miner_responses = []

        # Early validation
        if not validator_task.completion_responses:
            logger.error("No completion responses in validator task")
            return updated_miner_responses

        if not validator_task.ground_truth:
            logger.error("No ground truth found in validator task")
            return updated_miner_responses

        # Use criteria types from the first completion response. This assumes that all completions have the same criteria types
        criteria_types = validator_task.completion_responses[0].criteria_types
        logger.trace(
            f"Calculating scores for miner responses ... {len(miner_responses)}"
        )

        for criteria in criteria_types:
            # valid responses
            valid_miner_responses = [
                response
                for response in miner_responses
                if response.completion_responses
                and all(
                    _get_miner_response_by_criteria(criteria, completion) is not None
                    for completion in response.completion_responses
                )
            ]

            if not valid_miner_responses:
                logger.info(f"📝 No valid responses for {validator_task.task_id}")
                return updated_miner_responses

            logger.info(
                f"📝 Filtered {len(valid_miner_responses)} valid responses for task id {validator_task.task_id}"
            )

            # Check if ground truth is None
            if validator_task.ground_truth is None:
                logger.error("No ground truth found in validator task")
                return updated_miner_responses

            try:
                updated_miner_responses = cls.score_by_criteria(
                    criteria,
                    valid_miner_responses,
                    validator_task.ground_truth,
                )
            except NotImplementedError:
                logger.warning(
                    f"Scoring not implemented for criteria type: {type(criteria)}"
                )
                continue

        return updated_miner_responses

    # ---------------------------------------------------------------------------- #
    #                           SCORING HELPER FUNCTIONS                           #
    # ---------------------------------------------------------------------------- #
    @classmethod
    def score_by_criteria(
        cls,
        criteria: CriteriaType,
        valid_responses: List[TaskSynapseObject],
        ground_truth: Dict[str, int],
    ) -> List[TaskSynapseObject]:
        """Calculates and assigns scores based on criteria type."""
        if not isinstance(criteria, ScoreCriteria):
            raise NotImplementedError("Only score criteria is supported")

        (
            gt_score,
            miner_outputs,
            dot_product,
            dot_product_norm,
            cubic_reward_scores,
        ) = cls.ground_truth_scoring(criteria, ground_truth, valid_responses)

        for i, response in enumerate(valid_responses):
            if not response.axon or not response.axon.hotkey:
                continue

            for j, completion_response in enumerate(
                response.completion_responses or []
            ):
                scores = Scores(
                    raw_score=float(miner_outputs[i, j]),
                    ground_truth_score=float(gt_score[i]),
                    dot_product=float(dot_product[i]),
                    dot_product_norm=float(dot_product_norm[i]),
                    cubic_reward_score=float(cubic_reward_scores[i]),
                )

                for criteria in completion_response.criteria_types:
                    if isinstance(criteria, ScoreCriteria):
                        criteria.scores = scores

        return valid_responses


if __name__ == "__main__":
    miner_outputs = np.array(
        [
            [70, 67, 50, 30],
            [80, 75, 60, 40],
            [90, 85, 70, 50],
            [100, 95, 80, 60],
            [70, 67, 50, 30],
            [80, 75, 60, 40],
            [90, 85, 70, 50],
            [100, 95, 80, 60],
            [80, 75, 60, 40],
            [90, 85, 70, 50],
            [-1, -2, -3, -4],
        ]
    )
    ground_truth = np.array([82, 70, 55, 15])
    (
        final_score,
        dot_product,
        dot_product_norm,
        cubic_reward_scores,
    ) = _reward_cubic(miner_outputs, ground_truth, 0.006, 7.0, 2.0, visualize=True)

    logger.info(f"scoring: final score\n{final_score}")
    logger.info(f"scoring: dot product\n{dot_product}")
    logger.info(f"scoring: dot product norm\n{dot_product_norm}")
    logger.info(f"scoring: cubic reward scores\n{cubic_reward_scores}")
