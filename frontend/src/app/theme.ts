import {
  Accordion,
  Badge,
  Button,
  Card,
  NumberInput,
  Paper,
  Textarea,
  TextInput,
  createTheme,
  defaultVariantColorsResolver,
  type CSSVariablesResolver,
  type VariantColorsResolver,
} from "@mantine/core";

// Semantic colors cover legacy Mantine color names as well as new brand names.
// CSS variables keep portals (menus, modals, notifications) on the same theme.
const semanticColors: Record<string, [string, string, string]> = {
  brandBlue: ["action", "on-action", "link"],
  blue: ["action", "on-action", "link"],
  brandYellow: ["accent", "on-accent", "accent-text"],
  yellow: ["accent", "on-accent", "accent-text"],
  orange: ["warning-fill", "on-warning", "warning"],
  brandAi: ["ai-fill", "white", "ai"],
  violet: ["ai-fill", "white", "ai"],
  purple: ["ai-fill", "white", "ai"],
  red: ["danger-fill", "white", "danger"],
  green: ["success", "bg", "success"],
  teal: ["teal-fill", "on-teal", "teal"],
  brandGreen: ["success", "bg", "success"],
  cyan: ["go", "white", "go-text"],
  brandCyan: ["go", "white", "go-text"],
  gray: ["secondary", "text", "text"],
  brandNavy: ["secondary", "text", "text"],
  brandSand: ["secondary", "text", "text"],
};

const variantColorResolver: VariantColorsResolver = (input) => {
  const fallback = defaultVariantColorsResolver(input);
  const name =
    (input.color ?? input.theme.primaryColor).split(".")[0] ??
    input.theme.primaryColor;
  const semantic = semanticColors[name];
  if (!semantic) return fallback;
  const fill = `var(--c-${semantic[0]})`;
  const onFill = `var(--c-${semantic[1]})`;
  const text = `var(--c-${semantic[2]})`;
  const tint = `color-mix(in srgb, ${text} var(--control-tint), var(--c-surface))`;
  switch (input.variant) {
    case "filled":
      return {
        background: fill,
        hover:
          name === "brandBlue" || name === "blue"
            ? "var(--c-action-hover)"
            : fill,
        color: onFill,
        border: "transparent",
      };
    case "light":
      return {
        background: tint,
        hover: `color-mix(in srgb, ${text} var(--control-hover-tint), var(--c-surface))`,
        color: text,
        border: ["gray", "brandNavy", "brandSand"].includes(name)
          ? "1px solid var(--c-neutral-border)"
          : "transparent",
      };
    case "outline":
      return {
        background: "transparent",
        hover: tint,
        color: text,
        border: ["gray", "brandNavy", "brandSand"].includes(name)
          ? "1px solid var(--c-neutral-border)"
          : `1px solid ${text}`,
      };
    case "subtle":
    case "transparent":
      return {
        background: "transparent",
        hover: tint,
        color: text,
        border: "transparent",
      };
    case "default":
      return {
        background: "var(--c-secondary)",
        hover: "var(--c-raised)",
        color: "var(--c-text)",
        border: "1px solid var(--c-line-strong)",
      };
    default:
      return fallback;
  }
};

export const brandCssVariables: CSSVariablesResolver = () => {
  const common = {
    "--mantine-color-body": "var(--c-bg)",
    "--mantine-color-text": "var(--c-text)",
    "--mantine-color-dimmed": "var(--c-muted)",
    "--mantine-color-anchor": "var(--c-link)",
    "--mantine-color-default": "var(--c-surface)",
    "--mantine-color-default-hover": "var(--c-raised)",
    "--mantine-color-default-color": "var(--c-text)",
    "--mantine-color-default-border": "var(--c-line)",
    "--mantine-color-error": "var(--c-danger)",
    "--mantine-color-placeholder": "var(--c-muted)",
    "--mantine-color-disabled": "var(--c-disabled)",
    "--mantine-color-disabled-color": "var(--c-on-disabled)",
    "--mantine-primary-color-filled": "var(--c-action)",
    "--mantine-primary-color-filled-hover": "var(--c-action-hover)",
  };
  return { variables: {}, dark: common, light: {} };
};

export const brandTheme = createTheme({
  primaryColor: "brandBlue",
  primaryShade: 4,
  defaultRadius: "md",
  radius: {
    xs: "0.25rem",
    sm: "0.5rem",
    md: "0.75rem",
    lg: "1.25rem",
    xl: "1.5rem",
  },
  variantColorResolver,
  fontFamily: '"Golos Text", system-ui, sans-serif',
  fontFamilyMonospace: '"JetBrains Mono", monospace',
  headings: {
    fontFamily: 'Unbounded, "Golos Text", sans-serif',
    fontWeight: "800",
    sizes: {
      h1: { fontSize: "clamp(1.75rem, 4vw, 2.5rem)", lineHeight: "1.1" },
      h2: { fontSize: "clamp(1.5rem, 3vw, 1.875rem)", lineHeight: "1.21" },
      h3: { fontSize: "1.375rem", lineHeight: "1.3", fontWeight: "700" },
      h4: { fontSize: "1.125rem", lineHeight: "1.3", fontWeight: "700" },
      h5: { fontSize: "1rem", lineHeight: "1.3", fontWeight: "700" },
      h6: { fontSize: "0.875rem", lineHeight: "1.3", fontWeight: "700" },
    },
  },
  colors: {
    brandAi: [
      "#a99bff",
      "#a99bff",
      "#a99bff",
      "#a99bff",
      "#a99bff",
      "#6c57f5",
      "#6c57f5",
      "#6c57f5",
      "#6c57f5",
      "#6c57f5",
    ],
    brandBlue: [
      "#f0f7ff",
      "#e1efff",
      "#c7e2ff",
      "#9dccff",
      "#64aeff",
      "#2e90ff",
      "#197be5",
      "#1165be",
      "#0f5198",
      "#123f73",
    ],
    brandNavy: [
      "#eef3f9",
      "#d8e2ef",
      "#b3c5dc",
      "#86a2c3",
      "#5e82aa",
      "#3f6793",
      "#2c507b",
      "#19355f",
      "#132b4f",
      "#0d213e",
    ],
    brandSand: [
      "#fdfbf7",
      "#faf7f1",
      "#f6f2ea",
      "#f1ece3",
      "#e9e1d5",
      "#ddd2c1",
      "#cbbba4",
      "#ae987b",
      "#8b7458",
      "#6d5943",
    ],
    brandYellow: [
      "#fffbea",
      "#fff5c7",
      "#ffeb8a",
      "#ffdf57",
      "#ffd23f",
      "#f5b700",
      "#d89500",
      "#b57400",
      "#925a00",
      "#754600",
    ],
    brandCyan: [
      "#e8fbff",
      "#cef5fc",
      "#9ee8f4",
      "#65d6e9",
      "#2bc1dc",
      "#0aadcb",
      "#0792ad",
      "#08778e",
      "#0a6073",
      "#0b4e5e",
    ],
    brandGreen: [
      "#eefcf3",
      "#d5f7e1",
      "#a9edc3",
      "#78e0a2",
      "#4dd184",
      "#22b866",
      "#189951",
      "#127a40",
      "#0f6033",
      "#0b4a28",
    ],
  },
  components: {
    Button: Button.extend({
      defaultProps: { radius: "xl", fw: 600 },
      styles: (theme, props) => ({
        root: {
          "--button-active-bg": ["brandBlue", "blue"].includes(
            (props.color ?? theme.primaryColor).split(".")[0] ?? "",
          )
            ? "var(--c-action-pressed)"
            : "var(--button-bg)",
        },
      }),
    }),
    Badge: Badge.extend({ defaultProps: { radius: "xl", variant: "light" } }),
    Card: Card.extend({ defaultProps: { radius: "lg", padding: "lg" } }),
    Paper: Paper.extend({ defaultProps: { radius: "lg" } }),
    Accordion: Accordion.extend({ defaultProps: { radius: "lg" } }),
    TextInput: TextInput.extend({ defaultProps: { radius: "md" } }),
    Textarea: Textarea.extend({ defaultProps: { radius: "md" } }),
    NumberInput: NumberInput.extend({ defaultProps: { radius: "md" } }),
  },
});
