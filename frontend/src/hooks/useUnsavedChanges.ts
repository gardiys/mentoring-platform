import { useCallback, useEffect, useRef } from "react";
import { useBeforeUnload, useBlocker } from "react-router-dom";

const DEFAULT_MESSAGE =
  "На странице есть несохранённые изменения. Покинуть её и потерять черновик?";

export function useUnsavedChanges(
  isDirty: boolean,
  message = DEFAULT_MESSAGE,
): () => void {
  const allowNavigation = useRef(false);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty &&
      !allowNavigation.current &&
      `${currentLocation.pathname}${currentLocation.search}` !==
        `${nextLocation.pathname}${nextLocation.search}`,
  );

  useBeforeUnload(
    useCallback(
      (event) => {
        if (!isDirty || allowNavigation.current) return;
        event.preventDefault();
        event.returnValue = message;
      },
      [isDirty, message],
    ),
  );

  useEffect(() => {
    if (!isDirty) allowNavigation.current = false;
  }, [isDirty]);

  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm(message)) {
      allowNavigation.current = true;
      blocker.proceed();
    } else {
      blocker.reset();
    }
  }, [blocker, message]);

  return useCallback(() => {
    allowNavigation.current = true;
  }, []);
}
