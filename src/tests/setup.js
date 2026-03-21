/**
 * tests/setup.js — Vitest global setup
 *
 * @testing-library/react registers an afterEach cleanup hook that unmounts
 * rendered components between tests, preventing state leakage.
 */
import "@testing-library/react/pure";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
