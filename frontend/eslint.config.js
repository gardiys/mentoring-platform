import js from "@eslint/js";
import prettier from "eslint-config-prettier/flat";
import globals from "globals";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist/**",
      "coverage/**",
      "**/node_modules/**",
      "**/.pnpm-store/**",
      "public/vendor/**",
      "src/api/generated/**",
    ],
  },
  { linterOptions: { reportUnusedDisableDirectives: "error" } },
  {
    ...js.configs.recommended,
    files: ["**/*.{js,mjs,cjs}"],
    languageOptions: { globals: globals.node },
  },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      react,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    settings: { react: { version: "detect" } },
    rules: {
      ...react.configs.flat.recommended.rules,
      ...react.configs.flat["jsx-runtime"].rules,
      ...reactHooks.configs.recommended.rules,
      "react/prop-types": "off",
      "react-hooks/exhaustive-deps": "error",
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "CallExpression[callee.name=/^set[A-Z]/] > ArrowFunctionExpression MemberExpression[property.name='currentTarget']",
          message:
            "Считайте event.currentTarget до вызова setState: внутри апдейтера он уже null.",
        },
      ],
      "react-refresh/only-export-components": [
        "error",
        { allowConstantExport: true },
      ],
    },
  },
  prettier,
);
