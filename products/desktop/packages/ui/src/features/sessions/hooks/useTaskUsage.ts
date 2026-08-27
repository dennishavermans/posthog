import type { TaskUsage } from "@posthog/api-client/posthog-client";
import { useAuthenticatedQuery } from "@posthog/ui/hooks/useAuthenticatedQuery";
import type { UseQueryResult } from "@tanstack/react-query";

const TASK_USAGE_REFRESH_MS = 60_000;

export function useTaskUsage(
  taskId: string | undefined,
  enabled: boolean,
): UseQueryResult<TaskUsage | null> {
  return useAuthenticatedQuery(
    ["task-usage", taskId],
    (client): Promise<TaskUsage | null> => {
      if (!taskId) throw new Error("Task usage is unavailable");
      return client.getTaskUsage(taskId);
    },
    {
      enabled: enabled && taskId !== undefined,
      staleTime: TASK_USAGE_REFRESH_MS,
      // A task's billing surface never changes, so stop polling once the API
      // says this one is not attributed to the PostHog Desktop credit pool.
      refetchInterval: (query) =>
        query.state.data === null ? false : TASK_USAGE_REFRESH_MS,
      refetchOnMount: "always",
    },
  );
}
