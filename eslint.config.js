const js = require("@eslint/js");

module.exports = [
  js.configs.recommended,
  {
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
      },
    },
    rules: {
      "no-unused-vars": ["warn", { "varsIgnorePattern": "^[A-Z]" }],
      "no-console": "off",
    },
  },
  {
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