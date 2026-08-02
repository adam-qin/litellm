"use client";

import { useAuthorized } from "@/app/(dashboard)/hooks/useAuthorized";
import { getLDAPSettings, updateLDAPSettings } from "@/components/networking";
import NotificationsManager from "@/components/molecules/notifications_manager";
import { Button, Card, Form, Input, Switch, Typography } from "antd";
import { useEffect, useState } from "react";

const LDAP_SECRET_MASK = "********";
const DEFAULT_VALUES: Record<string, any> = {
  enabled: false,
  server_url: "",
  bind_dn: "",
  bind_password: "",
  user_search_base: "",
  user_search_filter: "(uid={username})",
  user_email_attribute: "mail",
  use_ssl: true,
  start_tls: false,
  ca_cert_file: "",
  connect_timeout: 5,
  receive_timeout: 10,
};

export default function LDAPSettings() {
  const { accessToken } = useAuthorized();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    getLDAPSettings(accessToken)
      .then((res: any) => {
        const values = res?.values ?? {};
        form.setFieldsValue({
          ...DEFAULT_VALUES,
          ...values,
          bind_password: values.bind_password === LDAP_SECRET_MASK ? "" : values.bind_password ?? "",
        });
      })
      .catch(() => {
        NotificationsManager.error("加载 LDAP 设置失败，请重试");
        form.setFieldsValue(DEFAULT_VALUES);
      })
      .finally(() => setLoading(false));
  }, [accessToken, form]);

  const onSave = async () => {
    try {
      const values = await form.validateFields();
      const payload = { ...values };
      if (!payload.bind_password) {
        delete payload.bind_password;
      }
      setSaving(true);
      await updateLDAPSettings(accessToken as string, payload);
      NotificationsManager.success("LDAP 设置已保存");
    } catch (error: any) {
      const message = error?.message ?? "保存 LDAP 设置失败";
      NotificationsManager.error(message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <Typography.Title level={4}>LDAP 登录设置</Typography.Title>
      <Typography.Paragraph type="secondary">
        启用后，用户可使用 LDAP / Active Directory 账号密码登录 XHub。通过 LDAP
        登录的用户默认被授予“内部用户”角色（可创建、删除、查看自己的密钥）。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULT_VALUES} disabled={loading || saving}>
        <Form.Item name="enabled" label="启用 LDAP 登录" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item
          noStyle
          shouldUpdate={(prev, current) => prev.enabled !== current.enabled}
        >
          {({ getFieldValue }) => (
            <Form.Item
              name="server_url"
              label="LDAP 服务器地址"
              rules={[
                { required: getFieldValue("enabled"), message: "请输入 LDAP 服务器地址" },
                { type: "url", message: "请输入有效的 LDAP URL" },
              ]}
            >
              <Input placeholder="ldaps://ldap.example.com:636" />
            </Form.Item>
          )}
        </Form.Item>
        <Form.Item
          noStyle
          shouldUpdate={(prev, current) => prev.bind_password !== current.bind_password || prev.enabled !== current.enabled}
        >
          {({ getFieldValue }) => (
            <Form.Item
              name="bind_dn"
              label="绑定 DN（服务账号，可选）"
              tooltip="用于搜索用户条目的服务账号；留空则使用匿名绑定。"
              rules={[
                {
                  required: getFieldValue("enabled") && Boolean(getFieldValue("bind_password")),
                  message: "请输入绑定 DN",
                },
              ]}
            >
              <Input placeholder="cn=readonly,dc=example,dc=com" />
            </Form.Item>
          )}
        </Form.Item>
        <Form.Item
          name="bind_password"
          label="绑定密码"
          tooltip="服务账号密码，以密文存储；留空表示保留已保存的密码。"
          dependencies={["bind_dn"]}
          rules={[
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (getFieldValue("enabled") && value && !getFieldValue("bind_dn")) {
                  return Promise.reject(new Error("请输入绑定 DN"));
                }
                return Promise.resolve();
              },
            }),
          ]}
        >
          <Input.Password placeholder="请输入绑定账号密码" />
        </Form.Item>
        <Form.Item
          name="user_search_base"
          label="用户搜索基准 DN"
          rules={[{ required: true, message: "请输入用户搜索基准 DN" }]}
        >
          <Input placeholder="dc=example,dc=com" />
        </Form.Item>
        <Form.Item name="use_ssl" label="启用 LDAPS" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="start_tls" label="启用 StartTLS" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="ca_cert_file" label="CA 证书文件路径（可选）">
          <Input placeholder="/etc/ssl/certs/ldap-ca.pem" />
        </Form.Item>
        <Form.Item name="user_search_filter" label="用户搜索过滤语句" tooltip="使用 {username} 作为登录名占位符。">
          <Input placeholder="(uid={username})" />
        </Form.Item>
        <Form.Item
          name="user_email_attribute"
          label="用户邮件属性"
          tooltip="LDAP 条目中存放邮箱的属性名，作为 XHub 用户标识。"
        >
          <Input placeholder="mail" />
        </Form.Item>
        <Form.Item label="默认用户角色">
          <Typography.Text>内部用户（创建 / 删除 / 查看）</Typography.Text>
        </Form.Item>
        <Button type="primary" loading={saving || loading} onClick={onSave}>
          保存设置
        </Button>
      </Form>
    </Card>
  );
}
