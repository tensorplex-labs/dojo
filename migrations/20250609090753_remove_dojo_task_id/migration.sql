/*
  Warnings:

  - You are about to drop the column `dojo_task_id` on the `miner_response` table. All the data in the column will be lost.
  - A unique constraint covering the columns `[validator_task_id,hotkey]` on the table `miner_response` will be added. If there are existing duplicate values, this will fail.

*/
-- DropIndex
DROP INDEX "miner_response_dojo_task_id_idx";

-- DropIndex
DROP INDEX "miner_response_validator_task_id_dojo_task_id_hotkey_key";

-- AlterTable
ALTER TABLE "miner_response" DROP COLUMN "dojo_task_id";

-- CreateIndex
CREATE UNIQUE INDEX "miner_response_validator_task_id_hotkey_key" ON "miner_response"("validator_task_id", "hotkey");
