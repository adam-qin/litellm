"use client";

import { useHashicorpVaultConfig } from "@/app/(dashboard)/hooks/configOverrides/useHashicorpVaultConfig";
import { useUpdateHashicorpVaultConfig } from "@/app/(dashboard)/hooks/configOverrides/useUpdateHashicorpVaultConfig";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import NotificationManager from "@/components/molecules/notifications_manager";
import { Alert, Button, Divider, Form, Input, Modal, Space, Switch, Typography } from "antd";
import React, { useEffect } from "react";
import { SENSITIVE_FIELDS, FIELD_LABELS } from "./constants";

interface FieldGroup {
  title: string;
  subtitle?: string;
  fields: string[];
}

const FIELD_GROUPS: FieldGroup[] = [
  {
    title: "Connection",
    fields: ["vault_addr", "vault_namespace", "vault_mount_name", "vault_path_prefix"],
  },
  {
    title: "Token Authentication",
    subtitle: "Use a Vault token to authenticate. Only one auth method is required.",
    fields: ["vault_token"],
  },
  {
    title: "AppRole Authentication",
    subtitle: "Use AppRole credentials to authenticate. Only one auth method is required.",
    fields: ["approle_role_id", "approle_secret_id", "approle_mount_path"],
  },
  {
    title: "TLS",
    subtitle: "Optional client certificate for mTLS.",
    fields: ["client_cert", "client_key", "vault_cert_role"],
  },
  {
    title: "Virtual Key Storage",
    subtitle: "Store newly created XHub Virtual Keys in Vault KV v2 using a stable key alias or token ID.",
    fields: ["store_virtual_keys", "prefix_for_stored_virtual_keys"],
  },
];

interface EditHashicorpVaultModalProps {
  isVisible: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}

const EditHashicorpVaultModal: React.FC<EditHashicorpVaultModalProps> = ({ isVisible, onCancel, onSuccess }) => {
  const [form] = Form.useForm();
  const { accessToken } = useAuthorized();
  const { data } = useHashicorpVaultConfig();
  const { mutate, isPending } = useUpdateHashicorpVaultConfig(accessToken);

  const schema = data?.field_schema;
  const properties = schema?.properties ?? {};
  const rawValues = data?.values ?? {};
  const virtualKeyStorageFields = {
    store_virtual_keys: {
      description: "Automatically store newly created Virtual Keys in Vault",
      type: "boolean",
    },
    prefix_for_stored_virtual_keys: {
      description: "Prefix used for Virtual Key secret names",
      type: "string",
    },
  };
  const effectiveProperties = { ...virtualKeyStorageFields, ...properties };

  useEffect(() => {
    if (isVisible && data) {
      form.resetFields();
      // Only set non-sensitive fields — sensitive ones show as placeholders
      const formValues: Record<string, any> = {};
      for (const [key, value] of Object.entries(rawValues)) {
        if (!SENSITIVE_FIELDS.has(key)) {
          formValues[key] = value;
        }
      }
      form.setFieldsValue(formValues);
    }
  }, [isVisible, data, form]);

  const handleSubmit = (formValues: Record<string, any>) => {
    const config: Record<string, any> = {};
    for (const [key, value] of Object.entries(formValues)) {
      if (value !== undefined && value !== null && value !== "") {
        // Non-empty value → update
        config[key] = value;
      } else if (!SENSITIVE_FIELDS.has(key)) {
        // Non-sensitive field cleared → send "" to clear it on the backend
        config[key] = "";
      }
      // Sensitive field left blank → omit from payload (keep existing)
    }

    mutate(config, {
      onSuccess: () => {
        NotificationManager.success("Hashicorp Vault configuration updated successfully");
        onSuccess();
      },
      onError: (err) => {
        NotificationManager.fromBackend(err);
      },
    });
  };

  const handleCancel = () => {
    form.resetFields();
    onCancel();
  };

  const renderField = (fieldName: string) => {
    const fieldSchema = effectiveProperties[fieldName];
    if (!fieldSchema) return null;

    const rules =
      fieldName === "vault_addr"
        ? [{ pattern: /^https?:\/\/.+/, message: "Must start with http:// or https://" }]
        : undefined;

    const isSensitive = SENSITIVE_FIELDS.has(fieldName);
    const existingValue = rawValues[fieldName];
    const hasExistingValue = isSensitive && existingValue != null && existingValue !== "";
    const placeholder = hasExistingValue ? `Leave blank to keep existing (${existingValue})` : fieldSchema?.description;

    if (fieldName === "store_virtual_keys") {
      return (
        <Form.Item
          key={fieldName}
          name={fieldName}
          label={FIELD_LABELS[fieldName] ?? fieldName}
          valuePropName="checked"
          extra="Key creation returns immediately. Vault persistence runs asynchronously and does not roll back a successfully created Key."
        >
          <Switch checkedChildren="Enabled" unCheckedChildren="Disabled" />
        </Form.Item>
      );
    }

    return (
      <Form.Item key={fieldName} name={fieldName} label={FIELD_LABELS[fieldName] ?? fieldName} rules={rules}>
        {isSensitive ? <Input.Password placeholder={placeholder} /> : <Input placeholder={fieldSchema?.description} />}
      </Form.Item>
    );
  };

  return (
    <Modal
      title="Edit Hashicorp Vault Configuration"
      open={isVisible}
      width={700}
      footer={
        <Space>
          <Button onClick={handleCancel} disabled={isPending}>
            Cancel
          </Button>
          <Button type="primary" loading={isPending} onClick={() => form.submit()}>
            {isPending ? "Saving..." : "Save"}
          </Button>
        </Space>
      }
      onCancel={handleCancel}
    >
      <Alert
        type="info"
        showIcon
        className="mb-4"
        message="Virtual Key persistence is asynchronous and best-effort"
        description="XHub creates the Virtual Key first, then writes it to Vault in the background. A Vault failure is logged but does not invalidate the created Key."
      />
      <Form form={form} layout="vertical" onFinish={handleSubmit}>
        {FIELD_GROUPS.map((group, index) => (
          <div key={group.title}>
            {index > 0 && <Divider />}
            <Typography.Title level={5} style={{ marginBottom: 4 }}>
              {group.title}
            </Typography.Title>
            {group.subtitle && (
              <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
                {group.subtitle}
              </Typography.Paragraph>
            )}
            {group.fields.map(renderField)}
          </div>
        ))}
      </Form>
    </Modal>
  );
};

export default EditHashicorpVaultModal;
