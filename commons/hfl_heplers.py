from datetime import datetime, timezone

from commons.utils import datetime_as_utc
from database.client import prisma
from database.prisma import Json
from database.prisma.enums import HFLStatusEnum
from database.prisma.models import HFLState
from database.prisma.types import HFLStateCreateInput, HFLStateUpdateInput
from dojo.protocol import HFLEvent, ScoreFeedbackEvent, TextFeedbackEvent


class HFLManager:
    @staticmethod
    async def create_state(
        previous_task_id: str,
        current_task_id: str,
        status: HFLStatusEnum = HFLStatusEnum.TF_PENDING,
        selected_completion_id: str | None = None,
        tx=None,
    ) -> HFLState:
        """
        Create or continue an HFL state.

        Args:
            previous_task_id: ID of the previous task
            current_task_id: ID of the current task
            original_task_id: ID of the original task (only needed for first cycle)
            status: Initial status of the HFL state
            selected_completion_id: ID of the selected completion (if any)
            tx: Optional transaction object

        Returns:
            The created HFL state

        Raises:
            ValueError: If original_task_id is not provided for a new HFL process
        """

        prisma_client = tx if tx else prisma

        # First try to find existing HFL state regardless of original_task_id
        existing_hfl = await prisma_client.hflstate.find_first(
            where={"current_task_id": previous_task_id}
        )

        if existing_hfl:
            # Use the existing original_task_id and increment iteration
            original_task_id = existing_hfl.original_task_id
            current_iteration = existing_hfl.current_iteration + 1
        else:
            # No existing cycle found, then this is the first cycle
            original_task_id = previous_task_id
            current_iteration = 1

        # Create the initial event with the correct iteration
        initial_event = TextFeedbackEvent(
            task_id=current_task_id,
            iteration=current_iteration,  # Use the determined iteration
            timestamp=datetime_as_utc(datetime.now(timezone.utc)),
        )

        # Prepare data for creating the HFL state
        create_data = HFLStateCreateInput(
            original_task_id=original_task_id,
            current_task_id=current_task_id,
            current_iteration=current_iteration,
            status=status,
            events=[Json(initial_event.model_dump())],
        )

        # Add selected_completion_id if provided
        if status == HFLStatusEnum.TF_PENDING and not selected_completion_id:
            raise ValueError(
                f"For a Text Feedback task, selected_completion_id must be provided: {selected_completion_id}"
            )
        else:
            create_data["selected_completion_id"] = selected_completion_id

        # Create and return the HFL state
        return await prisma_client.hflstate.create(data=create_data)

    @staticmethod
    async def update_state(
        hfl_state_id: str,
        updates: HFLStateUpdateInput,
        event_data: HFLEvent | None = None,
        tx=None,
    ) -> HFLState:
        """Update HFL state and handle status transitions."""
        prisma_client = tx if tx else prisma
        current_state = await prisma_client.hflstate.find_unique(
            where={"id": hfl_state_id}
        )
        if not current_state:
            raise ValueError(f"No HFL state found with ID {hfl_state_id}")

        new_status = updates.get("status")
        if new_status:
            match new_status:
                case HFLStatusEnum.TF_COMPLETED:
                    return await HFLManager._handle_tf_completed(
                        current_state, updates, event_data, tx
                    )
                case HFLStatusEnum.TF_PENDING:
                    return await HFLManager._handle_tf_pending(
                        current_state, updates, event_data, tx
                    )
                case HFLStatusEnum.TF_FAILED:
                    return await HFLManager._handle_tf_failed(
                        current_state, updates, event_data, tx
                    )
                case HFLStatusEnum.SF_PENDING:
                    return await HFLManager._handle_sf_pending(
                        current_state, updates, event_data, tx
                    )
                case HFLStatusEnum.SF_COMPLETED:
                    return await HFLManager._handle_sf_completed(
                        current_state, updates, event_data, tx
                    )
                case HFLStatusEnum.TF_NEXT_TASK_CREATED:
                    return await HFLManager._handle_tf_next_task_created(
                        current_state, updates, event_data, tx
                    )
                case HFLStatusEnum.HFL_COMPLETED:
                    return await HFLManager._handle_hfl_completed(
                        current_state, updates, event_data, tx
                    )

        return await HFLManager._update_state(current_state, updates, event_data, tx)

    @staticmethod
    async def _handle_tf_pending(
        state: HFLState,
        updates: HFLStateUpdateInput,
        event_data: HFLEvent | None = None,
        tx=None,
    ) -> HFLState:
        """Handle transition to TF_PENDING."""
        # NOTE: Add TF pending specific logic as needed
        return await HFLManager._update_state(state, updates, event_data, tx)

    @staticmethod
    async def _handle_tf_completed(
        state: HFLState,
        updates: HFLStateUpdateInput,
        event_data: HFLEvent | None = None,
        tx=None,
    ) -> HFLState:
        """Handle transition to TF_COMPLETED."""
        # NOTE: Add TF completion specific logic as needed
        return await HFLManager._update_state(state, updates, event_data, tx)

    @staticmethod
    async def _handle_tf_failed(
        state: HFLState,
        updates: HFLStateUpdateInput,
        event_data: HFLEvent | None = None,
        tx=None,
    ) -> HFLState:
        """Handle transition to TF_FAILED."""
        # NOTE: Add TF failed specific logic as needed
        return await HFLManager._update_state(state, updates, event_data, tx)

    @staticmethod
    async def _handle_sf_pending(
        state: HFLState,
        updates: HFLStateUpdateInput,
        event_data: HFLEvent | None = None,
        tx=None,
    ) -> HFLState:
        """Handle transition to SF_PENDING."""
        # NOTE: Add SF pending specific logic as needed

        if event_data:
            updates["current_synthetic_req_id"] = (
                event_data.syn_req_id
            )  # Clear the current synthetic request ID

        return await HFLManager._update_state(state, updates, event_data, tx)

    @staticmethod
    async def _handle_sf_completed(
        state: HFLState,
        updates: HFLStateUpdateInput,
        event_data: HFLEvent | None = None,
        tx=None,
    ) -> HFLState:
        """Handle transition to SF_COMPLETED."""
        # NOTE: Add SF completion specific logic as needed
        return await HFLManager._update_state(state, updates, event_data, tx)

    @staticmethod
    async def _handle_tf_next_task_created(
        state: HFLState,
        updates: HFLStateUpdateInput,
        event_data: HFLEvent | None = None,
        tx=None,
    ) -> HFLState:
        """Handle transition to TF_NEXT_TASK_CREATED."""
        # NOTE: Add TF next task creation specific logic as needed
        new_event = TextFeedbackEvent(
            task_id=state.current_task_id,
            iteration=state.current_iteration,
            timestamp=datetime_as_utc(datetime.now(timezone.utc)),
            type=HFLStatusEnum.TF_SCHEDULED,
        )
        if event_data:
            new_event.message = event_data.message
        return await HFLManager._update_state(state, updates, new_event, tx)

    @staticmethod
    async def _handle_hfl_completed(
        state: HFLState,
        updates: HFLStateUpdateInput,
        event_data: HFLEvent | None = None,
        tx=None,
    ) -> HFLState:
        """Handle transition to HFL_COMPLETED."""
        # NOTE: Add HFL completion specific logic as needed
        return await HFLManager._update_state(state, updates, event_data, tx)

    @staticmethod
    async def _update_state(
        state: HFLState,
        updates: HFLStateUpdateInput,
        event_data: HFLEvent | None = None,
        tx=None,
    ) -> HFLState:
        """Core update logic used by all handlers."""
        prisma_client = tx if tx else prisma
        if event_data:
            updates["events"] = {"push": [Json(event_data.model_dump())]}

        updates["updated_at"] = datetime_as_utc(datetime.now(timezone.utc))
        update_state = await prisma_client.hflstate.update(
            where={"id": state.id}, data=updates
        )

        if not update_state:
            raise ValueError(f"Failed to update HFL state with ID {state.id}")

        return update_state

    @staticmethod
    async def get_state(hfl_state_id: str) -> HFLState:
        """Get HFL state by ID."""
        state = await prisma.hflstate.find_unique(where={"id": hfl_state_id})
        if not state:
            raise ValueError(f"No HFL state found with ID {hfl_state_id}")
        return state

    @staticmethod
    async def get_update_state_operation(
        state_id: str, status_updates: HFLStateUpdateInput, event: ScoreFeedbackEvent
    ):
        return {
            "where": {"id": state_id},
            "data": HFLStateUpdateInput(
                status_updates,
                events={"push": [Json(event.model_dump())]},
                updated_at=datetime_as_utc(datetime.now(timezone.utc)),
            ),
        }

    @staticmethod
    async def get_state_by_current_task_id(current_task_id: str) -> HFLState | None:
        return await prisma.hflstate.find_first(
            where={"current_task_id": current_task_id}
        )

    @staticmethod
    async def get_state_by_original_task_id(original_task_id: str) -> HFLState | None:
        return await prisma.hflstate.find_first(
            where={"original_task_id": original_task_id}
        )
