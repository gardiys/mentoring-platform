import { Paper } from "@mantine/core";
import ReactMarkdown from "react-markdown";

export function GoTransitionProgramDescription({
  description,
}: {
  description: string;
}) {
  return (
    <Paper withBorder p={{ base: "md", sm: "xl" }} className="markdown-content">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {description}
      </ReactMarkdown>
    </Paper>
  );
}
