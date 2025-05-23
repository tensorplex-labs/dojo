from commons.dataset.types import HumanFeedbackResponse, HumanFeedbackTask
from commons.utils import get_new_uuid
from dojo.protocol import CodeAnswer, SyntheticQA


def map_synthetic_response(response: dict) -> SyntheticQA:
    # Create a new dictionary to store the mapped fields
    mapped_data = {
        "prompt": response["prompt"],
        "ground_truth": response["ground_truth"],
    }

    responses = list(
        map(
            lambda resp: {
                "model": resp["model"],
                "completion": resp["completion"],
                "completion_id": resp["cid"],
            },
            response["responses"],
        )
    )

    mapped_data["responses"] = responses

    return SyntheticQA.model_validate(mapped_data)


def map_human_feedback_response(raw_response: dict) -> HumanFeedbackResponse:
    """
    Map and decode a raw human feedback response from Redis to a HumanFeedbackResponse object.
    Handles JSON-encoded strings properly.
    """
    # Decode base prompt and code which might be double-encoded JSON strings
    base_prompt = raw_response.get("base_prompt", "")
    base_code = CodeAnswer.model_validate_json(raw_response.get("base_code", None))

    # Create the human feedback tasks
    human_feedback_tasks = []
    for task_data in raw_response.get("human_feedback_tasks", []):
        # Decode any JSON-encoded fields
        generated_code = (
            CodeAnswer.model_validate(task_data.get("generated_code", None))
            if task_data.get("generated_code", None)
            else None
        )
        if generated_code is None:
            raise ValueError("Generated code should not be None")

        task = HumanFeedbackTask(
            miner_hotkey=task_data.get("miner_hotkey", ""),
            miner_response_id=task_data.get("miner_response_id", ""),
            feedback=task_data.get("feedback", ""),
            model=task_data.get("model", "unknown"),
            completion_id=get_new_uuid(),
            generated_code=generated_code,
        )
        human_feedback_tasks.append(task)

    # Return the complete response object
    return HumanFeedbackResponse(
        base_prompt=base_prompt,
        base_code=base_code,
        human_feedback_tasks=human_feedback_tasks,
    )
