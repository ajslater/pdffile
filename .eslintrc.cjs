module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  extends: [
    "eslint:recommended",
    // LANGS
    "plugin:json/recommended",
    "plugin:mdx/recommended",
    "plugin:yaml/recommended",
    // CODE QUALITY
    "plugin:sonarjs/recommended",
    "plugin:unicorn/all",
    // PRACTICES
    "plugin:array-func/recommended",
    "plugin:eslint-comments/recommended",
    "plugin:no-use-extend-native/recommended",
    "plugin:optimize-regex/all",
    "plugin:promise/recommended",
    "plugin:import/recommended",
    "plugin:switch-case/recommended",
    // PRETTIER
    "plugin:prettier/recommended",
    "prettier", // prettier-config
    // SECURITY
    "plugin:no-unsanitized/DOM",
    "plugin:security/recommended-legacy",
  ],
  overrides: [
    {
      files: ["*.md"],
      rules: {
        "prettier/prettier": ["warn", { parser: "markdown" }],
      },
    },
  ],
  parserOptions: {
    ecmaVersion: "latest",
    ecmaFeatures: {
      impliedStrict: true,
    },
  },
  plugins: [
    "array-func",
    "eslint-comments",
    "json",
    "import",
    "no-constructor-bind",
    "no-secrets",
    "no-unsanitized",
    "no-use-extend-native",
    "optimize-regex",
    "prettier",
    "promise",
    "simple-import-sort",
    "switch-case",
    "security",
    "sonarjs",
    "unicorn",
    "yaml",
  ],
  rules: {
    "array-func/prefer-array-from": "off", // for modern browsers the spread operator, as preferred by unicorn, works fine.
    "max-params": ["warn", 4],
    "no-console": process.env.NODE_ENV === "production" ? "warn" : "off",
    "no-debugger": process.env.NODE_ENV === "production" ? "warn" : "off",
    "no-constructor-bind/no-constructor-bind": "error",
    "no-constructor-bind/no-constructor-state": "error",
    "no-secrets/no-secrets": "error",
    "eslint-comments/no-unused-disable": 1,
    "prettier/prettier": "warn",
    "security/detect-object-injection": "off",
    "simple-import-sort/exports": "warn",
    "simple-import-sort/imports": "warn",
    "space-before-function-paren": "off",
    "switch-case/newline-between-switch-case": "off", // Malfunctioning
    "unicorn/switch-case-braces": ["warn", "avoid"],
    "unicorn/prefer-node-protocol": 0,
    "unicorn/prevent-abbreviations": "off",
    "unicorn/filename-case": [
      "error",
      { case: "kebabCase", ignore: [".*.md"] },
    ],
  },
  ignorePatterns: [
    "*~",
    "**/__pycache__",
    ".git",
    "!.circleci",
    ".mypy_cache",
    ".pytest_cache",
    ".venv*",
    "dist",
    "package-lock.json",
    "test-results",
    "typings",
  ],
};
