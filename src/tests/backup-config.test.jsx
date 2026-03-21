import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

const apiMocks = vi.hoisted(() => ({
  updateSite: vi.fn(),
  getConfig: vi.fn(),
  addSite: vi.fn(),
  removeSite: vi.fn(),
}));

vi.mock("../api-client.js", () => ({
  default: {
    getConfig: apiMocks.getConfig,
    updateSite: apiMocks.updateSite,
    updateConfig: vi.fn(),
    addSite: apiMocks.addSite,
    removeSite: apiMocks.removeSite,
    startRun: vi.fn(),
    ssdStatus: vi.fn().mockResolvedValue(null),
  },
}));

import BackupConfig from "../pages/BackupConfig.jsx";

describe("BackupConfig", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getConfig.mockResolvedValue({
      ssd_path: "",
      schedule: { time: "08:00", timezone: "Europe/London" },
      performance: { concurrency: 4, max_file_size_gb: 5 },
      backup: { verify_checksums: true, exclude_patterns: [] },
      sources: [{ label: "Accounts", path: "/data/accounts", enabled: true }],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses backend config after adding a source", async () => {
    apiMocks.addSite.mockResolvedValue({
      config: {
        ssd_path: "",
        schedule: { time: "08:00", timezone: "Europe/London" },
        performance: { concurrency: 4, max_file_size_gb: 5 },
        backup: { verify_checksums: true, exclude_patterns: [] },
        sources: [
          { label: "Accounts", path: "/data/accounts", enabled: true },
          { label: "Clients", path: "/data/clients", enabled: true },
        ],
      },
    });

    render(<BackupConfig />);

    fireEvent.click(await screen.findByText("+ Add Folder"));
    fireEvent.change(screen.getByPlaceholderText("e.g. Client Documents"), { target: { value: "Clients" } });
    fireEvent.change(screen.getByPlaceholderText("C:\\Users\\Shared\\Documents"), { target: { value: "/data/clients" } });
    fireEvent.click(screen.getByText("Add Folder"));

    await waitFor(() => {
      expect(apiMocks.addSite).toHaveBeenCalledWith({ label: "Clients", path: "/data/clients", enabled: true });
    });

    await waitFor(() => {
      expect(screen.getByText("Clients")).toBeTruthy();
    });
  });

  it("uses backend config after removing a source", async () => {
    apiMocks.removeSite.mockResolvedValue({
      config: {
        ssd_path: "",
        schedule: { time: "08:00", timezone: "Europe/London" },
        performance: { concurrency: 4, max_file_size_gb: 5 },
        backup: { verify_checksums: true, exclude_patterns: [] },
        sources: [],
      },
    });

    render(<BackupConfig />);

    fireEvent.click(await screen.findByText("Remove"));

    await waitFor(() => {
      expect(apiMocks.removeSite).toHaveBeenCalledWith("Accounts");
    });

    await waitFor(() => {
      expect(screen.getByText(/No source folders added yet/)).toBeTruthy();
    });
  });

  it("persists source toggle changes through the API", async () => {
    apiMocks.updateSite.mockResolvedValue({
      source: { label: "Accounts", path: "/data/accounts", enabled: false },
    });

    render(<BackupConfig />);

    const checkboxes = await screen.findAllByRole("checkbox");
    const sourceCheckbox = checkboxes.at(-1);
    fireEvent.click(sourceCheckbox);

    await waitFor(() => {
      expect(apiMocks.updateSite).toHaveBeenCalledWith("Accounts", { enabled: false });
    });

    await waitFor(() => {
      expect(sourceCheckbox.checked).toBe(false);
    });
  });
});
