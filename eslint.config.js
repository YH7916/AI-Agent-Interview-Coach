export default [
  {
    ignores: [
      "node_modules/**",
      ".venv/**",
      ".cache/**",
      ".pytest_cache/**",
      ".mypy_cache/**",
      ".ruff_cache/**",
      ".playwright-mcp/**",
      "output/**",
    ],
  },
  {
    files: ["frontend/**/*.js"],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: "module",
      globals: {
        CSS: "readonly",
        Element: "readonly",
        FormData: "readonly",
        HTMLButtonElement: "readonly",
        HTMLElement: "readonly",
        TextDecoder: "readonly",
        document: "readonly",
        fetch: "readonly",
        localStorage: "readonly",
        requestAnimationFrame: "readonly",
        window: "readonly",
      },
    },
    rules: {
      "eqeqeq": "error",
      "no-undef": "error",
      "no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
        },
      ],
      "no-var": "error",
      "prefer-const": "error",
    },
  },
];
