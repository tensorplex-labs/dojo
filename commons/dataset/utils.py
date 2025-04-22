from commons.dataset.types import HumanFeedbackResponse
from commons.utils import get_new_uuid, set_expire_time
from dojo import TASK_DEADLINE
from dojo.protocol import (
    CompletionResponse,
    ScoreCriteria,
    TaskSynapseObject,
    TaskTypeEnum,
)


def map_human_feedback_to_task_synapse(
    human_feedback_response: HumanFeedbackResponse,
) -> TaskSynapseObject:
    """Convert to TaskSynapseObject format"""
    completion_responses: list[CompletionResponse] = []

    # First add the base code as a completion
    completion_responses.append(
        CompletionResponse(
            model="base_model",  # TODO: use the actual model name
            completion=human_feedback_response.base_code,
            completion_id=get_new_uuid(),
            criteria_types=[
                ScoreCriteria(
                    min=1.0,
                    max=100.0,
                )
            ],
        )
    )

    # Add each feedback task as a completion
    for task in human_feedback_response.human_feedback_tasks:
        completion_responses.append(
            CompletionResponse(
                model=task.miner_hotkey,  # Use miner_hotkey as model identifier
                completion=task.generated_code,
                completion_id=task.miner_response_id,
                criteria_types=[
                    ScoreCriteria(
                        min=1.0,
                        max=100.0,
                    ),
                ],
            )
        )

    return TaskSynapseObject(
        task_id=get_new_uuid(),
        prompt=human_feedback_response.base_prompt,
        task_type=TaskTypeEnum.CODE_GENERATION,
        expire_at=set_expire_time(TASK_DEADLINE),
        completion_responses=completion_responses,
    )
