import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Container,
  Divider,
  Group,
  List,
  Loader,
  Paper,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { IconAlertCircle, IconMail, IconSparkles } from "@tabler/icons-react";

type EmailAnalysis = {
  summary: string;
  priority: "High" | "Medium" | "Low";
  category: string;
  recommendedActions: string[];
  deadlines: string[];
  suggestedReply: string;
};

function App() {
  const [emailText, setEmailText] = useState("");
  const [analysis, setAnalysis] = useState<EmailAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function analyzeEmail() {
    setLoading(true);
    setError("");
    setAnalysis(null);

    try {
      const response = await fetch("http://localhost:4000/analyze-email", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ emailText }),
      });

      if (!response.ok) {
        throw new Error("Failed to analyze email");
      }

      const data: EmailAnalysis = await response.json();
      setAnalysis(data);
    } catch {
      setError("Something went wrong analyzing this email.");
    } finally {
      setLoading(false);
    }
  }

  function getPriorityColor(priority: EmailAnalysis["priority"]) {
    if (priority === "High") return "red";
    if (priority === "Medium") return "yellow";
    return "green";
  }

  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        <div>
          <Group gap="xs">
            <IconMail size={32} />
            <Title>Inbox2Done</Title>
          </Group>

          <Text c="dimmed" mt="xs">
            Paste an email and get a summary, priority level, recommended
            actions, deadlines, and a suggested reply.
          </Text>
        </div>

        <Paper shadow="sm" radius="lg" p="lg" withBorder>
          <Stack>
            <Textarea
              label="Email text"
              placeholder="Paste the email here..."
              minRows={10}
              value={emailText}
              onChange={(event) => setEmailText(event.currentTarget.value)}
            />

            <Button
              leftSection={<IconSparkles size={18} />}
              onClick={analyzeEmail}
              disabled={!emailText.trim() || loading}
            >
              {loading ? "Analyzing..." : "Analyze Email"}
            </Button>
          </Stack>
        </Paper>

        {loading && (
          <Paper shadow="sm" radius="lg" p="lg" withBorder>
            <Group>
              <Loader size="sm" />
              <Text>Analyzing email...</Text>
            </Group>
          </Paper>
        )}

        {error && (
          <Alert color="red" icon={<IconAlertCircle size={18} />}>
            {error}
          </Alert>
        )}

        {analysis && (
          <Paper shadow="sm" radius="lg" p="lg" withBorder>
            <Stack>
              <Group justify="space-between">
                <Title order={2}>Analysis</Title>

                <Group>
                  <Badge color={getPriorityColor(analysis.priority)}>
                    {analysis.priority} Priority
                  </Badge>

                  <Badge variant="light">{analysis.category}</Badge>
                </Group>
              </Group>

              <Divider />

              <div>
                <Title order={4}>Summary</Title>
                <Text mt="xs">{analysis.summary}</Text>
              </div>

              <div>
                <Title order={4}>Recommended Actions</Title>
                <List mt="xs">
                  {analysis.recommendedActions.map((action) => (
                    <List.Item key={action}>{action}</List.Item>
                  ))}
                </List>
              </div>

              <div>
                <Title order={4}>Deadlines</Title>
                {analysis.deadlines.length > 0 ? (
                  <List mt="xs">
                    {analysis.deadlines.map((deadline) => (
                      <List.Item key={deadline}>{deadline}</List.Item>
                    ))}
                  </List>
                ) : (
                  <Text mt="xs" c="dimmed">
                    No deadlines found.
                  </Text>
                )}
              </div>

              {analysis.suggestedReply && (
                <div>
                  <Title order={4}>Suggested Reply</Title>

                  <Paper bg="gray.0" p="md" radius="md" mt="xs">
                    <Text style={{ whiteSpace: "pre-wrap" }}>
                      {analysis.suggestedReply}
                    </Text>
                  </Paper>

                  <Button
                    mt="sm"
                    variant="light"
                    onClick={() =>
                      navigator.clipboard.writeText(analysis.suggestedReply)
                    }
                  >
                    Copy Reply
                  </Button>
                </div>
              )}
            </Stack>
          </Paper>
        )}
      </Stack>
    </Container>
  );
}

export default App;