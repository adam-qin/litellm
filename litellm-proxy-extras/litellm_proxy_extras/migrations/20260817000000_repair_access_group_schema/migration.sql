-- Repair partially-applied unified access-group migrations.
--
-- v1.93.10 introduced the table with access_model_ids and renamed that column to
-- access_model_names in the immediately-following migration. Deployments that
-- applied only the first migration cannot use /v1/access_group because the
-- generated Prisma client selects access_model_names on every query.

CREATE TABLE IF NOT EXISTS "LiteLLM_AccessGroupTable" (
    "access_group_id" TEXT NOT NULL,
    "access_group_name" TEXT NOT NULL,
    "description" TEXT,
    "access_model_names" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "access_mcp_server_ids" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "access_agent_ids" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "assigned_team_ids" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "assigned_key_ids" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT,

    CONSTRAINT "LiteLLM_AccessGroupTable_pkey" PRIMARY KEY ("access_group_id")
);

ALTER TABLE "LiteLLM_AccessGroupTable"
    ADD COLUMN IF NOT EXISTS "description" TEXT,
    ADD COLUMN IF NOT EXISTS "access_model_names" TEXT[] DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN IF NOT EXISTS "access_mcp_server_ids" TEXT[] DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN IF NOT EXISTS "access_agent_ids" TEXT[] DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN IF NOT EXISTS "assigned_team_ids" TEXT[] DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN IF NOT EXISTS "assigned_key_ids" TEXT[] DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN IF NOT EXISTS "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS "created_by" TEXT,
    ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS "updated_by" TEXT;

-- Preserve values from the short-lived access_model_ids schema before dropping it.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'LiteLLM_AccessGroupTable'
          AND column_name = 'access_model_ids'
    ) THEN
        EXECUTE '
            UPDATE "LiteLLM_AccessGroupTable"
            SET "access_model_names" = COALESCE("access_model_names", ARRAY[]::TEXT[])
                                       || COALESCE("access_model_ids", ARRAY[]::TEXT[])
            WHERE COALESCE(array_length("access_model_ids", 1), 0) > 0
              AND COALESCE(array_length("access_model_names", 1), 0) = 0';
        ALTER TABLE "LiteLLM_AccessGroupTable" DROP COLUMN "access_model_ids";
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS "LiteLLM_AccessGroupTable_access_group_name_key"
    ON "LiteLLM_AccessGroupTable"("access_group_name");

ALTER TABLE "LiteLLM_TeamTable"
    ADD COLUMN IF NOT EXISTS "access_group_ids" TEXT[] DEFAULT ARRAY[]::TEXT[];
ALTER TABLE "LiteLLM_VerificationToken"
    ADD COLUMN IF NOT EXISTS "access_group_ids" TEXT[] DEFAULT ARRAY[]::TEXT[];
ALTER TABLE "LiteLLM_DeletedTeamTable"
    ADD COLUMN IF NOT EXISTS "access_group_ids" TEXT[] DEFAULT ARRAY[]::TEXT[];
ALTER TABLE "LiteLLM_DeletedVerificationToken"
    ADD COLUMN IF NOT EXISTS "access_group_ids" TEXT[] DEFAULT ARRAY[]::TEXT[];
