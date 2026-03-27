const js = require("@eslint/js");

module.exports = [
  js.configs.recommended,
  {
    // JSX files — need React plugin for JSX parsing
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: "module",
        ecmaFeatures: {
          jsx: true,
        },
      },
      globals: {
        // Browser globals (fixes 'window', 'fetch', 'URLSearchParams')
        window: "readonly",
        fetch: "readonly",
        URLSearchParams: "readonly",
        document: "readonly",
        console: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
      },
    },
    rules: {
      "no-unused-vars": "warn",
      "no-console": "off",
    },
  },
  {
    // Test files — need Node globals (fixes 'global')
    files: ["src/tests/**/*.{js,jsx}"],
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