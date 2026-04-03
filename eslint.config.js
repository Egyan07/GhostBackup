const js = require("@eslint/js");
const tseslint = require("typescript-eslint");

module.exports = [
  { ignores: ["src/coverage/**", "dist/**"] },
  js.configs.recommended,
  // JS/JSX files (tests remain JS)
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: {
        window: "readonly",
        fetch: "readonly",
        URLSearchParams: "readonly",
        document: "readonly",
        console: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        Event: "readonly",
        Blob: "readonly",
        URL: "readonly",
        navigator: "readonly",
        confirm: "readonly",
        localStorage: "readonly",
      },
    },
    rules: {
      "no-unused-vars": ["warn", { "varsIgnorePattern": "^[A-Z]" }],
      "no-console": "off",
    },
  },
  // TypeScript files
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
      globals: {
        window: "readonly",
        fetch: "readonly",
        URLSearchParams: "readonly",
        document: "readonly",
        console: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        Event: "readonly",
        Blob: "readonly",
        URL: "readonly",
        navigator: "readonly",
        confirm: "readonly",
        localStorage: "readonly",
      },
    },
    rules: {
      "@typescript-eslint/no-unused-vars": ["warn", { "varsIgnorePattern": "^[A-Z]" }],
      "no-console": "off",
    },
  },
  // Test-specific globals
  {
    files: ["src/tests/**/*.{js,jsx,ts,tsx}"],
    languageOptions: {
      globals: {
        global: "readonly",
        process: "readonly",
        describe: "readonly",
        it: "readonly",
        expect: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
        vi: "readonly",
      },
    },
  },
];
