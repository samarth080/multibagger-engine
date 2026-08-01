module.exports = [
  {
    files: ["src/mbe/frontend/assets/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        globalThis: "readonly",
        module: "readonly",
        URL: "readonly",
        URLSearchParams: "readonly",
        AbortController: "readonly",
        FormData: "readonly",
        Blob: "readonly"
        ,Option: "readonly"
        ,TextEncoder: "readonly"
        ,TextDecoder: "readonly"
        ,Uint8Array: "readonly"
        ,document: "readonly"
        ,localStorage: "readonly"
      }
    },
    rules: {
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "no-unused-vars": ["error", { "argsIgnorePattern": "^_", "caughtErrorsIgnorePattern": "^_" }],
      "no-undef": "error",
      "eqeqeq": ["error", "always", { "null": "ignore" }]
    }
  },
  {
    files: ["tests/frontend/**/*.js", "tests/browser/**/*.js", "playwright.config.js", "eslint.config.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs",
      globals: { require: "readonly", module: "readonly", __dirname: "readonly", URL: "readonly", URLSearchParams: "readonly", setTimeout: "readonly", clearTimeout: "readonly", console: "readonly", Buffer: "readonly", process: "readonly", document: "readonly", localStorage: "readonly", PerformanceObserver: "readonly", performance: "readonly", matchMedia: "readonly", getComputedStyle: "readonly", NodeFilter: "readonly" }
    },
    rules: { "no-unused-vars": "error", "no-undef": "error" }
  }
];
