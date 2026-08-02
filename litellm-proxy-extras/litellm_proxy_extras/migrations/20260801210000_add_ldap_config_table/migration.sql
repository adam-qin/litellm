-- CreateTable
CREATE TABLE "LiteLLM_LDAPConfig" (
    "id" TEXT NOT NULL DEFAULT 'ldap_config',
    "ldap_settings" JSONB NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "LiteLLM_LDAPConfig_pkey" PRIMARY KEY ("id")
);
