import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import EndpointSelector from "./EndpointSelector";
import { ENDPOINT_OPTIONS } from "./chatConstants";
import { EndpointType, getEndpointType } from "@/components/chat_ui/mode_endpoint_mapping";

describe("model mode endpoint selection", () => {
  it.each([
    ["image_edit", EndpointType.IMAGE_EDITS],
    ["image_edits", EndpointType.IMAGE_EDITS],
    ["realtime", EndpointType.REALTIME],
  ])("maps %s to its supported endpoint", (mode, endpointType) => {
    expect(getEndpointType(mode)).toBe(endpointType);
    expect(ENDPOINT_OPTIONS.some((option) => option.value === endpointType)).toBe(true);
  });

  it("continues to default unknown modes to chat", () => {
    expect(getEndpointType("unknown_mode")).toBe(EndpointType.CHAT);
  });
});

describe("EndpointSelector", () => {
  Object.values(ENDPOINT_OPTIONS).forEach((endpointType) => {
    it(`should render the endpoint selector for ${endpointType.value}`, async () => {
      const { getByText } = render(<EndpointSelector endpointType={endpointType.value} onEndpointChange={() => {}} />);
      await waitFor(() => {
        expect(getByText(endpointType.label)).toBeInTheDocument();
      });
    });
  });

  it("should filter and show audio endpoints when user inputs 'audio'", async () => {
    const user = userEvent.setup();
    render(<EndpointSelector endpointType={ENDPOINT_OPTIONS[0].value} onEndpointChange={() => {}} />);

    const combobox = screen.getByRole("combobox");
    await user.click(combobox);

    const input = await screen.findByRole("combobox");
    await user.type(input, "audio");

    expect(await screen.findByText("/v1/audio/speech")).toBeInTheDocument();
    expect(await screen.findByText("/v1/audio/transcriptions")).toBeInTheDocument();
  });
});
