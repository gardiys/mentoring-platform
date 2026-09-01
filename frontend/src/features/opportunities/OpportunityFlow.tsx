import { Group, SimpleGrid, Stack, Text } from "@mantine/core";

interface OpportunityFlowProps {
  steps: Array<{
    title: string;
    description: string;
  }>;
}

export function OpportunityFlow({ steps }: OpportunityFlowProps) {
  return (
    <Stack gap="sm">
      <Text fw={700}>Как это работает</Text>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: steps.length }} spacing="sm">
        {steps.map((step, index) => (
          <Group
            key={step.title}
            className="opportunity-flow-step"
            align="flex-start"
            wrap="nowrap"
          >
            <span className="opportunity-flow-number" aria-hidden="true">
              {index + 1}
            </span>
            <div>
              <Text fw={700} size="sm">
                {step.title}
              </Text>
              <Text c="dimmed" size="xs">
                {step.description}
              </Text>
            </div>
          </Group>
        ))}
      </SimpleGrid>
    </Stack>
  );
}
