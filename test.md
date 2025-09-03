# �� Subnet Schema

Participants (miners and validators) interact through tasks, completions, and votes.

---

## **Participants**

Represents both miners and validators.

- `hotkey` (PK): unique identifier (public key).
- `reputation_score`: current standing or performance score.
- `registered_at`: when the participant joined.

**Relationships**

- One participant can create many tasks (as validator).
- One participant can be assigned many tasks (as miner).
- One participant can submit many completions.
- One participant can cast many votes.
- One participant can have many score history entries.
- One miner can have many contributors; one contributor can be linked to exactly one miner (see Miner Contributors).

**Notes**

- Roles are inferred from activity (no `role` column stored):
  - Appears in `tasks.validator_hotkey` → acted as validator
  - Appears in `tasks.assigned_miner_hotkey` or submits a completion for a task → acted as miner (generator)
  - Appears in `votes.voter_hotkey` → acted as discriminator

---

## **Tasks**

Represents a validation request created by a validator.

- `id` (PK): unique task identifier.
- `task_type`: category of task.
- `task_metadata`: prompt details or other task parameters.
- `validator_hotkey` (FK → participants.hotkey): validator who created the task.
- `validator_completion_id` (FK → completions.id): validator’s reference completion.
- `assigned_miner_hotkey` (FK → participants.hotkey): the miner this task is assigned to (exactly one).
- `status`: assignment state (e.g. `"assigned"`, `"submitted"`, `"expired"`).
- `expire_at`: deadline for the task.
- `created_at`, `updated_at`: timestamps.

**Relationships**

- One task is assigned to exactly one miner.
- One task can have many completions (at most one from the assigned miner, and one from the validator).
- One task can receive many votes.
- Each task references one validator completion.

---

## **Completions**

Stores answers submitted by miners or validators.

- `id` (PK): unique completion identifier.
- `hotkey` (FK → participants.hotkey): who submitted the completion (validator, miner, or contributor).
- `task_id` (FK → tasks.id): related task.
- `completion`: JSON content of the submission.
- `created_at`, `updated_at`: timestamps.

**Relationships**

- One task can have many completions.
- One participant can submit many completions.
- Many votes can reference a completion as chosen/rejected.
- A validator completion is referenced by its task.

**Notes/Constraints**

- At most one completion per submitter per task: unique on `(task_id, hotkey)`.
- At most one miner completion per task: enforce via application or trigger using `miner_contributors` mapping; the miner completion must be submitted by the assigned miner or a contributor linked to that miner.
- A contributor may submit on behalf of the assigned miner only if they are linked in `miner_contributors` and not revoked.
- Validator completion: the row referenced by `tasks.validator_completion_id` must also have `task_id = tasks.id` and `hotkey = tasks.validator_hotkey`.

---

## **Miner Contributors**

Maps contributors who are allowed to act on behalf of a miner. Each contributor can help exactly one miner.

- `contributor_hotkey` (PK): the contributor.
- `miner_hotkey` (FK → participants.hotkey): the miner they can help.
- `created_at`: when the relationship was created.
- `revoked_at` (nullable): when the permission was revoked; null means active.

**Relationships**

- One miner can have many contributors.
- One contributor links to exactly one miner.

**Constraints**

- Unique on `contributor_hotkey` (one contributor → one miner).
- A contributor may only submit a miner completion for tasks where `tasks.assigned_miner_hotkey = miner_hotkey` and the link is active (`revoked_at IS NULL`).

**Usage**

- Determines which tasks a contributor can see and answer (tasks assigned to their linked miner).

---

## **Votes**

Records miner judgments on completions.

- `id` (PK): unique vote identifier.
- `voter_hotkey` (FK → participants.hotkey): voter.
- `task_id` (FK → tasks.id): task being judged.
- `chosen_completion_id` (FK → completions.id): preferred completion.
- `against_completion_id` (FK → completions.id, nullable): rejected completion.
- `weight`: vote weight (e.g. reputation/stake-based).
- `created_at`, `updated_at`: timestamps.

**Relationships**

- One participant can cast many votes.
- One task can receive many votes.
- One completion can be chosen in many votes.
- One completion can also be rejected in many votes.

---

## **Score History**

Tracks participant score changes over time.

- `id` (PK): unique record identifier.
- `hotkey` (FK → participants.hotkey): participant affected.
- `score_change`: numeric adjustment (+/-).
- `reason`: reason for the score update.
- `created_at`: when the change occurred.

**Relationships**

- One participant can have many score history records.
