import { useRef, useState } from "react";

type Values = Record<string, string>;

function readDraft(key: string, limits: Readonly<Record<string, number>>) {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(key);
  } catch {
    return { values: {} as Values, available: false };
  }
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    const values: Values = {};
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      for (const [name, value] of Object.entries(parsed)) {
        if (
          Object.hasOwn(limits, name) &&
          typeof value === "string" &&
          value.length <= (limits[name] ?? 0)
        ) {
          values[name] = value;
        }
      }
    }
    return { values, available: true };
  } catch {
    return { values: {} as Values, available: true };
  }
}

export function useApplicationDraft(
  storageKey: string,
  initialValues: Values,
  limits: Readonly<Record<string, number>>,
) {
  const [initial] = useState(() => readDraft(storageKey, limits));
  const [values, setValues] = useState<Values>(() => ({
    ...initialValues,
    ...initial.values,
  }));
  const changes = useRef(initial.values);
  const current = useRef(values);
  const [available, setAvailable] = useState(initial.available);

  const setField = (name: string, value: string) => {
    changes.current = { ...changes.current, [name]: value };
    current.current = { ...current.current, [name]: value };
    setValues(current.current);
    // Save in the input handler: navigating away immediately must keep the last keypress.
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(changes.current));
      setAvailable(true);
    } catch {
      setAvailable(false);
    }
  };
  const reset = () => {
    changes.current = {};
    current.current = initialValues;
    setValues(initialValues);
    try {
      window.localStorage.removeItem(storageKey);
      setAvailable(true);
    } catch {
      setAvailable(false);
    }
  };
  return { values, setField, reset, available };
}
