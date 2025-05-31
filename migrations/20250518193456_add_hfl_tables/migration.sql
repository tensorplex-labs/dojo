/*
  Warnings:

  - A unique constraint covering the columns `[next_task_id]` on the table `validator_task` will be added. If there are existing duplicate values, this will fail.

*/
-- CreateEnum
CREATE TYPE "HFLStatusEnum" AS ENUM ('TF_PENDING', 'TF_COMPLETED', 'TF_FAILED', 'TF_SCHEDULED', 'TF_NEXT_TASK_CREATED', 'SF_PENDING', 'SF_COMPLETED', 'SF_FAILED', 'HFL_COMPLETED');

-- AlterEnum
ALTER TYPE "CriteriaTypeEnum" ADD VALUE 'TEXT';

-- AlterEnum
-- This migration adds more than one value to an enum.
-- With PostgreSQL versions 11 and earlier, this is not possible
-- in a single migration. This can be worked around by creating
-- multiple migrations, each migration adding only one value to
-- the enum.


ALTER TYPE "TaskTypeEnum" ADD VALUE 'TEXT_FEEDBACK';
ALTER TYPE "TaskTypeEnum" ADD VALUE 'SCORE_FEEDBACK';

-- AlterTable
ALTER TABLE "validator_task" ADD COLUMN     "hfl_state_id" TEXT,
ADD COLUMN     "next_task_id" TEXT;

-- CreateTable
CREATE TABLE "hfl_state" (
    "id" TEXT NOT NULL,
    "original_task_id" TEXT NOT NULL,
    "current_task_id" TEXT NOT NULL,
    "current_iteration" INTEGER NOT NULL DEFAULT 1,
    "tf_retry_count" INTEGER NOT NULL DEFAULT 0,
    "syn_retry_count" INTEGER NOT NULL DEFAULT 0,
    "current_synthetic_req_id" TEXT,
    "selected_completion_id" TEXT,
    "status" "HFLStatusEnum" NOT NULL,
    "events" JSONB[],
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "hfl_state_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "hfl_completion_relation" (
    "id" TEXT NOT NULL,
    "miner_response_id" TEXT NOT NULL,
    "sf_completion_id" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "hfl_completion_relation_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "hfl_state_original_task_id_current_task_id_key" ON "hfl_state"("original_task_id", "current_task_id");

-- CreateIndex
CREATE UNIQUE INDEX "validator_task_next_task_id_key" ON "validator_task"("next_task_id");

-- AddForeignKey
ALTER TABLE "validator_task" ADD CONSTRAINT "validator_task_next_task_id_fkey" FOREIGN KEY ("next_task_id") REFERENCES "validator_task"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "validator_task" ADD CONSTRAINT "validator_task_hfl_state_id_fkey" FOREIGN KEY ("hfl_state_id") REFERENCES "hfl_state"("id") ON DELETE SET NULL ON UPDATE CASCADE;
