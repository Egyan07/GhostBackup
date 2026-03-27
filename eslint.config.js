const js = require("@eslint/js");

module.exports = [
  js.configs.recommended,
  {
    files: ["src/**/*.{js,jsx}"],
    rules: {
      "no-unused-vars": "warn",
      "no-console": "off",
    },
  },
];