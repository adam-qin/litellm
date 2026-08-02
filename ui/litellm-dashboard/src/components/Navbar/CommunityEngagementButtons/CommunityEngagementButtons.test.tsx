import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen } from "../../../../tests/test-utils";
import { CommunityEngagementButtons } from "./CommunityEngagementButtons";

const mockUseDisableShowPrompts = vi.fn(() => false);

vi.mock("@/app/(dashboard)/hooks/useDisableShowPrompts", () => ({
  useDisableShowPrompts: () => mockUseDisableShowPrompts(),
}));

describe("CommunityEngagementButtons", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDisableShowPrompts.mockReturnValue(false);
  });

  it("should render the XHub GitHub link", () => {
    renderWithProviders(<CommunityEngagementButtons />);

    const githubLink = screen.getByRole("link", { name: /xhub source on github/i });
    expect(githubLink).toBeInTheDocument();
    expect(githubLink).toHaveAttribute("href", "https://github.com/adam-qin/litellm");
    expect(githubLink).toHaveAttribute("target", "_blank");
    expect(githubLink).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("should render GitHub link with correct href", () => {
    renderWithProviders(<CommunityEngagementButtons />);

    const githubLink = screen.getByRole("link", { name: /xhub source on github/i });
    expect(githubLink).toBeInTheDocument();
    expect(githubLink).toHaveAttribute("href", "https://github.com/adam-qin/litellm");
    expect(githubLink).toHaveAttribute("target", "_blank");
    expect(githubLink).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("should not render buttons when prompts are disabled", () => {
    mockUseDisableShowPrompts.mockReturnValue(true);

    renderWithProviders(<CommunityEngagementButtons />);

    expect(screen.queryByRole("link", { name: /xhub source on github/i })).not.toBeInTheDocument();
  });
});
