"use client";

import { useEffect } from "react";

const TEXT_TRANSLATIONS: Record<string, string> = {
  "AI GATEWAY": "模型网关",
  "AI Gateway": "模型网关",
  OBSERVABILITY: "可观测性",
  Observability: "可观测性",
  "ACCESS CONTROL": "访问控制",
  "Access Control": "访问控制",
  SETTINGS: "系统设置",
  Settings: "系统设置",
  "Virtual Keys": "虚拟密钥",
  Playground: "模型调试",
  "Models + Endpoints": "模型与端点",
  Usage: "用量分析",
  Logs: "日志",
  Teams: "团队",
  "Internal Users": "内部用户",
  "Access Groups": "访问组",
  Budgets: "预算",
  "Router Settings": "路由设置",
  "Logging & Alerts": "日志与告警",
  "Admin Settings": "管理设置",
  "Cost Tracking": "成本追踪",
  "UI Theme": "界面主题",
  "Virtual Key": "虚拟密钥",
  "Create Key": "创建密钥",
  "Add Model": "添加模型",
  "Model Management": "模型管理",
  "All Models": "全部模型",
  "Your Models": "我的模型",
  "LLM Credentials": "模型凭据",
  "Pass-Through Endpoints": "透传端点",
  "Health Status": "健康状态",
  "Request Logs": "请求日志",
  "Audit Logs": "审计日志",
  "Deleted Keys": "已删除密钥",
  "Deleted Teams": "已删除团队",
  "Create Team": "创建团队",
  "Team Name": "团队名称",
  Members: "成员",
  Models: "模型",
  Keys: "密钥",
  "Create Access Group": "创建访问组",
  "Create Budget": "创建预算",
  Loadbalancing: "负载均衡",
  "Routing Groups": "路由组",
  Fallbacks: "故障转移",
  General: "常规设置",
  "Logging Callbacks": "日志回调",
  "Alerting Settings": "告警设置",
  "SSO Settings": "单点登录设置",
  "Security Settings": "安全设置",
  "UI Settings": "界面设置",
  "Cost Tracking Settings": "成本追踪设置",
  "UI Theme Customization": "界面主题定制",
  "Customize your XHub admin dashboard": "定制您的 XHub 管理控制台",
  "Custom Logo URL": "自定义 Logo 地址",
  "Custom Favicon URL": "自定义站点图标地址",
  "Reset to Default": "恢复默认设置",
  "User Information": "用户信息",
  "Team Information": "团队信息",
  "Access Group Information": "访问组信息",
  "Budget Information": "预算信息",
  "Key Information": "密钥信息",
  "Key Details": "密钥详情",
  "Optional Settings": "可选设置",
  "Key Lifecycle": "密钥生命周期",
  "Model Aliases": "模型别名",
  "Logging Settings": "日志设置",
  "Key Ownership": "密钥所有者",
  "Secret Key": "密钥值",
  "Key ID": "密钥 ID",
  "Key Alias": "密钥别名",
  "Team ID": "团队 ID",
  "User ID": "用户 ID",
  "Budget ID": "预算 ID",
  "Object ID": "对象 ID",
  "API Key (Hash)": "API 密钥（哈希）",
  "Changed By": "操作人",
  Timestamp: "时间戳",
  Table: "数据表",
  Before: "变更前",
  After: "变更后",
  Organization: "组织",
  "No teams yet": "暂无团队",
  "No keys found": "未找到密钥",
  "No callbacks configured": "暂未配置回调",
  "No provider discounts configured": "暂未配置供应商折扣",
  "No models assigned to this group": "该访问组尚未分配模型",
  "No keys attached": "尚未关联密钥",
  "No teams attached": "尚未关联团队",
  "Add Member": "添加成员",
  "Edit Member": "编辑成员",
  "Remove from Team": "从团队移除",
  "Team Settings": "团队设置",
  "Team Budget": "团队预算",
  "Team Member Settings": "团队成员设置",
  "Add Team": "添加团队",
  "Back to Users": "返回用户列表",
  "Back to Teams": "返回团队列表",
  "Delete User": "删除用户",
  "Global Proxy Role": "全局代理角色",
  "Total Spend": "总消费",
  "Personal Models": "个人模型",
  "User Settings": "用户设置",
  "Edit Settings": "编辑设置",
  "User Alias": "用户别名",
  "Default User Settings": "默认用户设置",
  "Bulk Edit All Users": "批量编辑所有用户",
  "Selected Users": "已选择用户",
  Instructions: "操作说明",
  "Team Management": "团队管理",
  "Manage resource permissions for your organization": "管理组织的资源访问权限",
  "Delete Access Group": "删除访问组",
  "Edit Access Group": "编辑访问组",
  "Attached Keys": "已关联密钥",
  "Attached Teams": "已关联团队",
  "MCP Servers": "MCP 服务器",
  Agents: "智能体",
  "Edit budget": "编辑预算",
  "Delete budget": "删除预算",
  "Delete Budget?": "确认删除预算？",
  "Assign Budget to Customer": "为客户分配预算",
  "Configure Model Fallbacks": "配置模型故障转移",
  "Primary Model": "主模型",
  "Fallback Chain": "故障转移链",
  "No fallback models selected": "尚未选择故障转移模型",
  "Save All Configurations": "保存全部配置",
  "Saving Configuration...": "正在保存配置...",
  Setting: "设置项",
  Value: "值",
  "In DB": "数据库配置",
  "In Config": "配置文件",
  "Not Set": "未设置",
  Callback: "回调",
  "Please select a callback": "请选择回调",
  "Alerting Types": "告警类型",
  "Email Alerts": "邮件告警",
  "Save Changes": "保存更改",
  "Test Alerts": "测试告警",
  "Add Logging Callback": "添加日志回调",
  "Edit Callback Settings": "编辑回调设置",
  "Delete Callback": "删除回调",
  "Callback Name": "回调名称",
  Mode: "模式",
  "Success & Failure": "成功与失败",
  "Allowed IPs": "允许的 IP",
  "UI Access Control": "界面访问控制",
  "Hashicorp Vault": "Hashicorp Vault",
  Plugins: "插件",
  "Admin Access": "管理员访问",
  "Add SSO": "添加单点登录",
  "Edit SSO Settings": "编辑单点登录设置",
  "Delete SSO Settings": "删除单点登录设置",
  "Role Mappings": "角色映射",
  "Group Claim": "用户组声明",
  "Default Role": "默认角色",
  "Login without SSO": "不使用单点登录",
  "Internal User Page Visibility": "内部用户页面可见性",
  "Provider Discounts": "供应商折扣",
  Discounts: "折扣",
  "Test It": "测试",
  "Add Provider Discount": "添加供应商折扣",
  "Fee/Price Margin": "费用/价格加成",
  "Add Provider Margin": "添加供应商加成",
  "Pricing Calculator": "价格计算器",
  "Remove Provider Discount": "移除供应商折扣",
  "Remove Provider Margin": "移除供应商加成",
  Save: "保存",
  Cancel: "取消",
  Close: "关闭",
  Delete: "删除",
  Edit: "编辑",
  Update: "更新",
  Reset: "重置",
  Confirm: "确认",
  Submit: "提交",
  Search: "搜索",
  Filter: "筛选",
  Filters: "筛选条件",
  "Reset Filters": "重置筛选",
  Previous: "上一页",
  Next: "下一页",
  Actions: "操作",
  Action: "操作",
  Status: "状态",
  Active: "启用",
  Blocked: "已禁用",
  Success: "成功",
  Failure: "失败",
  Details: "详情",
  Overview: "概览",
  Description: "描述",
  Name: "名称",
  Email: "邮箱",
  Role: "角色",
  Tier: "版本",
  Standard: "标准版",
  Premium: "高级版",
  Logout: "退出登录",
  Login: "登录",
  Username: "用户名",
  Password: "密码",
  "Logging in...": "正在登录...",
  "Login with SSO": "使用单点登录",
  "Back to Login": "返回登录",
  "Reset Password": "重置密码",
  "Sign Up": "注册",
  Loading: "加载中",
  "Loading...": "加载中...",
  "No data": "暂无数据",
  "No Data": "暂无数据",
  Unlimited: "无限制",
  "Created At": "创建时间",
  "Created By": "创建人",
  "Last Updated": "最后更新",
  "Last Active": "最后活跃",
  Expires: "到期时间",
  Spend: "消费",
  Budget: "预算",
  "Max Budget": "最大预算",
  "Budget Reset": "预算重置",
  "Rate Limits": "速率限制",
  "Total Requests": "请求总数",
  "Successful Requests": "成功请求",
  "Failed Requests": "失败请求",
  "Total Tokens": "Token 总量",
  "Input Tokens": "输入 Token",
  "Output Tokens": "输出 Token",
  "Daily Spend": "每日消费",
  "Export Data": "导出数据",
  Chat: "对话",
  Compare: "对比",
  Compliance: "合规检测",
  "Agent Builder (Experimental)": "智能体构建（实验性）",
  Configurations: "配置",
  "Model Settings": "模型设置",
  "Select a Model": "选择模型",
  "Type your message...": "请输入消息...",
  "Start a conversation": "开始对话",
  Assistant: "助手",
  Results: "结果",
  "Access Denied": "无权访问",
  "Copy JSON": "复制 JSON",
  Copied: "已复制",
  Enabled: "已启用",
  Disabled: "已禁用",
  Yes: "是",
  No: "否",
  Add: "添加",
  Remove: "移除",
  Back: "返回",
  Docs: "文档",
  // --- Guardrails & Policies (安全合规) ---
  Guardrails: "护栏",
  "Guardrail Garden": "护栏广场",
  "Add Provider Guardrail": "添加供应商护栏",
  "Create Custom Code Guardrail": "创建自定义代码护栏",
  "+ Add New Guardrail": "+ 新建护栏",
  "Test Playground": "测试演练场",
  "Submitted Guardrails": "已提交护栏",
  "Delete Guardrail": "删除护栏",
  "Guardrail Information": "护栏信息",
  "Guardrail Name": "护栏名称",
  "Create Guardrail": "创建护栏",
  "Edit Guardrail": "编辑护栏",
  "Are you sure you want to delete guardrail: ": "确定要删除护栏：",
  "? This action cannot be undone.": "？此操作无法撤销。",
  "Default On": "默认开启",
  "Failed to delete guardrail": "删除护栏失败",
  Policies: "策略",
  "About Policies": "关于策略",
  "Use policies to group guardrails and control which ones run for specific teams, keys, or models.":
    "使用策略将护栏分组，并控制哪些护栏对特定团队、密钥或模型生效。",
  "Why use policies?": "为什么要使用策略？",
  "Enable/disable specific guardrails for teams, keys, or models": "为团队、密钥或模型启用/禁用特定护栏",
  "Group guardrails into a single policy": "将多个护栏组合为单一策略",
  "Inherit from existing policies and override what you need": "继承现有策略并覆盖所需部分",
  "Learn more in the documentation →": "查看文档了解更多 →",
  Templates: "模板",
  "Policy Simulator": "策略模拟器",
  Attachments: "绑定",
  "+ Add New Policy": "+ 新建策略",
  "Delete Policy": "删除策略",
  "Policy Name": "策略名称",
  "Create Policy": "创建策略",
  "Edit Policy": "编辑策略",
  "Policy ID": "策略 ID",
  "Are you sure you want to delete policy: ": "确定要删除策略：",
  "Policy Information": "策略信息",
  "Inherits From": "继承来源",
  "About Policy Attachments": "关于策略绑定",
  "Policy attachments control where your policies apply. Policies don't do anything until you attach them to specific teams, keys, models, tags, or globally.":
    "策略绑定决定策略的生效范围。在将策略绑定到特定团队、密钥、模型、标签或全局之前，策略不会生效。",
  "Attachment Scopes:": "绑定范围：",
  "Global (*)": "全局 (*)",
  "Learn more about attachments →": "查看绑定文档了解更多 →",
  "Enterprise Feature Notice": "企业版功能提示",
  "Parts of policy attachments will be on LiteLLM Enterprise in subsequent releases.":
    "策略绑定的部分功能将在后续版本中归入 LiteLLM 企业版。",
  "+ Add New Attachment": "+ 新建绑定",
  "Delete Attachment": "删除绑定",
  "Are you sure you want to delete this attachment?": "确定要删除该绑定吗？",
  "Attachment Information": "绑定信息",
  "Attachment ID": "绑定 ID",
  Scope: "范围",
  Tags: "标签",
  Provider: "供应商",
  Mode: "模式",
  "Failed to delete policy": "删除策略失败",
  "Failed to fetch policies": "获取策略失败",
  "Failed to fetch attachments": "获取绑定失败",
  "Failed to load guardrails. Please try again.": "加载护栏失败，请重试。",
  "Failed to configure template. Please try again.": "配置模板失败，请重试。",
  "Failed to create guardrails. Please try again.": "创建护栏失败，请重试。",
};

const ATTRIBUTE_TRANSLATIONS: Record<string, string> = {
  "Enter your username": "请输入用户名",
  "Enter your password": "请输入密码",
  "Please enter your username": "请输入用户名",
  "Please enter your password": "请输入密码",
  "Search...": "搜索...",
  "Search teams by name or ID...": "按团队名称或 ID 搜索...",
  "Search groups by name, ID, or description...": "按名称、ID 或描述搜索访问组...",
  "Type your message...": "请输入消息...",
  "Expand sidebar": "展开侧边栏",
  "Collapse sidebar": "收起侧边栏",
};

const TEXT_ATTRIBUTES = ["placeholder", "title", "aria-label"] as const;
const OBSERVER_OPTIONS: MutationObserverInit = {
  childList: true,
  subtree: true,
  characterData: true,
  attributes: true,
  attributeFilter: [...TEXT_ATTRIBUTES],
};

function translateText(value: string): string {
  const trimmed = value.trim();
  const translated = TEXT_TRANSLATIONS[trimmed];
  if (translated) return value.replace(trimmed, translated);

  let result = value;
  for (const [source, target] of Object.entries(TEXT_TRANSLATIONS)) {
    if (source.length < 8 || !result.includes(source)) continue;
    result = result.replaceAll(source, target);
  }
  return result;
}

function translateTextNode(node: Text): void {
  if (!node.parentElement || node.parentElement.closest("script, style, pre, code, textarea")) return;
  const current = node.nodeValue ?? "";
  const translated = translateText(current);
  if (translated !== current) node.nodeValue = translated;
}

function translateAttributes(element: Element): void {
  for (const attribute of TEXT_ATTRIBUTES) {
    const current = element.getAttribute(attribute);
    if (!current) continue;
    const translated = ATTRIBUTE_TRANSLATIONS[current] ?? TEXT_TRANSLATIONS[current];
    if (!translated || translated === current) continue;
    element.setAttribute(attribute, translated);
  }
}

function translateNode(node: Node): void {
  if (node.nodeType === Node.TEXT_NODE) {
    translateTextNode(node as Text);
    return;
  }
  if (!(node instanceof Element)) return;
  translateAttributes(node);
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
  let textNode = walker.nextNode();
  while (textNode) {
    translateTextNode(textNode as Text);
    textNode = walker.nextNode();
  }
  node.querySelectorAll("[placeholder], [title], [aria-label]").forEach(translateAttributes);
}

export default function ChineseLocaleProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    document.documentElement.lang = "zh-CN";
    translateNode(document.body);

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === "characterData") translateNode(mutation.target);
        if (mutation.type === "attributes" && mutation.target instanceof Element) {
          translateAttributes(mutation.target);
        }
        mutation.addedNodes.forEach(translateNode);
      }
    });

    observer.observe(document.body, OBSERVER_OPTIONS);

    return () => observer.disconnect();
  }, []);

  return children;
}
