import React from "react";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/../tests/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PoliciesPanel from "./index";

/**
 * Ant Design's static Modal.confirm often does not run onOk in the real app (React 18+).
 * In jsdom it may still run; we mock confirm as a no-op so the test fails until the panel
 * uses a controlled DeleteResourceModal instead of Modal.confirm.
 */
vi.mock("antd", async (importOriginal) => {
  const mod = await importOriginal<typeof import("antd")>();
  return {
    ...mod,
    Modal: Object.assign(mod.Modal, {
      confirm: vi.fn(),
    }),
  };
});

const EXPECTED_ATTACHMENT_ID = "att-11111111-2222-3333-4444-555555555555" as const;

const componentMocks = vi.hoisted(() => ({
  policyTemplates: vi.fn(),
  flowBuilderPage: vi.fn(() => null),
  addPolicyForm: vi.fn(() => null),
  guardrailSelectionModal: vi.fn(() => null),
  templateParameterModal: vi.fn(() => null),
  aiSuggestionModal: vi.fn(() => null),
  policyTestPanel: vi.fn(() => null),
  addAttachmentForm: vi.fn(() => null),
}));

const networkingMocks = vi.hoisted(() => ({
  deletePolicyAttachmentCall: vi.fn().mockResolvedValue(undefined),
  getPoliciesList: vi.fn().mockResolvedValue({ policies: [] }),
  getPolicyAttachmentsList: vi.fn().mockResolvedValue({
    attachments: [
      {
        attachment_id: "att-11111111-2222-3333-4444-555555555555",
        policy_name: "test-policy",
        scope: null,
        teams: [],
        keys: [],
        models: [],
        tags: [],
      },
    ],
  }),
  getGuardrailsList: vi.fn().mockResolvedValue({ guardrails: [] }),
  getPolicyInfo: vi.fn().mockResolvedValue({}),
  deletePolicyCall: vi.fn().mockResolvedValue(undefined),
  createPolicyCall: vi.fn(),
  updatePolicyCall: vi.fn(),
  createPolicyAttachmentCall: vi.fn(),
  createGuardrailCall: vi.fn(),
  enrichPolicyTemplate: vi.fn(),
}));

vi.mock("@/components/networking", () => ({
  ...networkingMocks,
}));

vi.mock("./impact_popover", () => ({
  default: () => <button type="button" aria-label="View blast radius" />,
}));

vi.mock("@tremor/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tremor/react")>();
  return {
    ...actual,
    Button: React.forwardRef<HTMLButtonElement, any>(({ children, ...props }, ref) =>
      React.createElement("button", { ...props, ref }, children),
    ),
    Tooltip: ({ children }: { children?: React.ReactNode }) => React.createElement(React.Fragment, null, children),
    Switch: ({
      checked,
      onChange,
      className,
    }: {
      checked?: boolean;
      onChange?: (v: boolean) => void;
      className?: string;
    }) =>
      React.createElement("input", {
        type: "checkbox",
        role: "switch",
        checked,
        onChange: (e: React.ChangeEvent<HTMLInputElement>) => onChange?.(e.target.checked),
        className,
      }),
  };
});

vi.mock("./policy_templates", () => ({
  __esModule: true,
  default: (props: any) => {
    componentMocks.policyTemplates(props);
    return (
      <div data-testid="policy-templates-stub">
        {props.canManage && <button type="button">应用模板</button>}
        {props.canManage && <button type="button">AI 推荐模板</button>}
      </div>
    );
  },
}));

vi.mock("./pipeline_flow_builder", () => ({
  FlowBuilderPage: componentMocks.flowBuilderPage,
}));

vi.mock("./policy_info", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("./add_policy_form", () => ({
  __esModule: true,
  default: componentMocks.addPolicyForm,
}));

vi.mock("./guardrail_selection_modal", () => ({
  __esModule: true,
  default: componentMocks.guardrailSelectionModal,
}));

vi.mock("./template_parameter_modal", () => ({
  __esModule: true,
  default: componentMocks.templateParameterModal,
}));

vi.mock("./ai_suggestion_modal", () => ({
  __esModule: true,
  default: componentMocks.aiSuggestionModal,
}));

vi.mock("./policy_test_panel", () => ({
  __esModule: true,
  default: componentMocks.policyTestPanel,
}));

vi.mock("./add_attachment_form", () => ({
  __esModule: true,
  default: componentMocks.addAttachmentForm,
}));

describe("PoliciesPanel attachment delete", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps Admin Viewer read-only across policy management features", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PoliciesPanel accessToken="test-token" userRole="Admin Viewer" />);

    await waitFor(() => {
      expect(networkingMocks.getPoliciesList).toHaveBeenCalled();
    });

    expect(screen.queryByRole("tab", { name: "策略模拟器" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ 新建策略" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "应用模板" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "AI 推荐模板" })).not.toBeInTheDocument();
    expect(componentMocks.policyTemplates).toHaveBeenCalledWith(expect.objectContaining({ canManage: false }));

    await user.click(screen.getByRole("tab", { name: "策略绑定" }));
    expect(screen.queryByRole("button", { name: "+ 新建绑定" })).not.toBeInTheDocument();

    expect(componentMocks.addPolicyForm).not.toHaveBeenCalled();
    expect(componentMocks.addAttachmentForm).not.toHaveBeenCalled();
    expect(componentMocks.policyTestPanel).not.toHaveBeenCalled();
    expect(componentMocks.guardrailSelectionModal).not.toHaveBeenCalled();
    expect(componentMocks.templateParameterModal).not.toHaveBeenCalled();
    expect(componentMocks.aiSuggestionModal).not.toHaveBeenCalled();
    expect(componentMocks.flowBuilderPage).not.toHaveBeenCalled();
  });

  it("should call deletePolicyAttachmentCall after the user confirms delete in the attachment modal", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PoliciesPanel accessToken="test-token" userRole="Admin" />);

    await waitFor(() => {
      expect(networkingMocks.getPolicyAttachmentsList).toHaveBeenCalled();
    });

    await user.click(screen.getByRole("tab", { name: "策略绑定" }));

    await waitFor(() => {
      expect(screen.getByText("test-policy")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId(`attachment-actions-${EXPECTED_ATTACHMENT_ID}`));
    await user.click(await screen.findByTestId("attachment-action-delete"));

    const dialog = await screen.findByRole("dialog", {}, { timeout: 5000 });
    expect(within(dialog).getByText(/Are you sure you want to delete this attachment/i)).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => {
      expect(networkingMocks.deletePolicyAttachmentCall).toHaveBeenCalledTimes(1);
      expect(networkingMocks.deletePolicyAttachmentCall).toHaveBeenCalledWith("test-token", EXPECTED_ATTACHMENT_ID);
    });
  });

  it("should show mutation pending state while attachment delete is in flight", async () => {
    let resolveDelete: (() => void) | undefined;
    const deletePromise = new Promise<void>((resolve) => {
      resolveDelete = resolve;
    });
    networkingMocks.deletePolicyAttachmentCall.mockImplementationOnce(() => deletePromise);

    const user = userEvent.setup();
    renderWithProviders(<PoliciesPanel accessToken="test-token" userRole="Admin" />);

    await waitFor(() => {
      expect(networkingMocks.getPolicyAttachmentsList).toHaveBeenCalled();
    });

    await user.click(screen.getByRole("tab", { name: "策略绑定" }));
    await waitFor(() => {
      expect(screen.getByText("test-policy")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId(`attachment-actions-${EXPECTED_ATTACHMENT_ID}`));
    await user.click(await screen.findByTestId("attachment-action-delete"));
    const dialog = await screen.findByRole("dialog", {}, { timeout: 5000 });

    const deleteButton = within(dialog).getByRole("button", { name: /^delete$/i });
    await user.click(deleteButton);

    await waitFor(() => {
      expect(within(dialog).getByRole("button", { name: /deleting/i })).toBeDisabled();
    });

    resolveDelete?.();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
